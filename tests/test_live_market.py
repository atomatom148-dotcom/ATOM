import json
from dataclasses import FrozenInstanceError
from io import BytesIO
import os
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from quant.live_market import (
    ALPACA_BTC_LATEST_QUOTE_URL, ALPACA_LATEST_QUOTES_URL, BTC_FETCH_SECONDS,
    BTC_SOURCE_TIMEOUT_SECONDS, MAX_BTC_AGE_SECONDS,
    ALPACA_NDX_LATEST_VALUE_URL, MARKET_DISPLAY_FETCH_SECONDS, LiveMarketState,
    MASSIVE_NDX_SNAPSHOT_URL, parse_alpaca_ndx_value, parse_alpaca_timestamp,
    parse_massive_ndx_snapshot, poll_alpaca, poll_alpaca_g2, poll_massive_ndx,
)
from quant.web import create_app


def request_json(app):
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app({"PATH_INFO": "/api/dashboard"}, start_response))
    return json.loads(body)


class LiveMarketTests(unittest.TestCase):
    def test_concurrent_coin_quotes_enqueue_in_assigned_sequence_order(self):
        first_in_v4 = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        evidence_store = MagicMock()

        class CapturingOutbox:
            def __init__(self):
                self.items = []
            def put_nowait(self, item):
                self.items.append(item)
                return True

        outbox = CapturingOutbox()
        def handler(_snapshot, _previous, current):
            if current.event_epoch == 1.0:
                first_in_v4.set()  # sequence 1 has already been assigned
                self.assertTrue(release_first.wait(timeout=2))
            return None

        state = LiveMarketState(
            clock=lambda: 10.0, evidence_store=evidence_store,
            evidence_outbox=outbox, v9_cycle_handler=handler,
        )
        results = []
        first = threading.Thread(target=lambda: results.append(
            state.accept_quote(bid=99.0, ask=101.0, event_epoch=1.0)))
        def accept_second():
            second_started.set()
            results.append(state.accept_quote(
                bid=100.0, ask=102.0, event_epoch=2.0))
        second = threading.Thread(target=accept_second)

        first.start()
        self.assertTrue(first_in_v4.wait(timeout=2))
        second.start()
        self.assertTrue(second_started.wait(timeout=2))
        # The second caller is attempting ingress, but cannot overtake sequence 1.
        self.assertEqual(outbox.items, [])
        release_first.set()
        first.join(timeout=2); second.join(timeout=2)

        self.assertEqual(results.count(True), 2)
        self.assertEqual([item.sequence for item in outbox.items], [1, 2])
        self.assertEqual(dict(state.metrics.snapshot().counters).get(
            "EVIDENCE_SEQUENCE_GAP", 0), 0)
        evidence_store.record_cycle_and_resolve.assert_not_called()

    def test_stop_accepting_quotes_is_an_outbox_handoff_barrier(self):
        entered_handler = threading.Event()
        release_handler = threading.Event()

        class CapturingOutbox:
            def __init__(self): self.items = []
            def put_nowait(self, item):
                self.items.append(item)
                return True

        outbox = CapturingOutbox()
        def handler(*_args):
            entered_handler.set()
            self.assertTrue(release_handler.wait(timeout=2))
            return None

        state = LiveMarketState(
            clock=lambda: 10.0, evidence_outbox=outbox,
            v9_cycle_handler=handler,
        )
        accepted = []
        ingress = threading.Thread(target=lambda: accepted.append(
            state.accept_quote(bid=99.0, ask=101.0, event_epoch=1.0)))
        ingress.start()
        self.assertTrue(entered_handler.wait(timeout=1))

        stopped = threading.Event()
        stopper = threading.Thread(target=lambda: (
            state.stop_accepting_quotes(), stopped.set()))
        stopper.start()
        self.assertFalse(stopped.wait(timeout=.02))
        release_handler.set()
        ingress.join(timeout=2); stopper.join(timeout=2)

        self.assertEqual(accepted, [True])
        self.assertEqual(len(outbox.items), 1)
        self.assertTrue(stopped.is_set())
        self.assertFalse(state.accept_quote(
            bid=100.0, ask=102.0, event_epoch=2.0))
        self.assertEqual(len(outbox.items), 1)

    def test_market_display_accepts_only_newer_provider_values_and_is_frozen(self):
        state = LiveMarketState()
        self.assertEqual(MARKET_DISPLAY_FETCH_SECONDS, 0.25)
        self.assertTrue(state.update_market_display(
            coin_midpoint=100.01, coin_event_epoch=10.0,
            qqq_midpoint=500.01, qqq_event_epoch=20.0,
        ))
        self.assertFalse(state.update_market_display(
            coin_midpoint=999.0, coin_event_epoch=10.0,
            qqq_midpoint=999.0, qqq_event_epoch=19.0,
        ))
        display = state.market_display()
        self.assertEqual(display.coin_midpoint, 100.01)
        self.assertEqual(display.qqq_midpoint, 500.01)
        with self.assertRaises(FrozenInstanceError):
            display.coin_midpoint = 1.0

    def test_combined_alpaca_poll_updates_display_each_fetch_but_quant_once_per_second(self):
        payloads = iter((
            {"quotes": {
                "COIN": {"bp": 100.00, "ap": 100.00, "bs": 1, "as": 1,
                         "t": "1970-01-01T00:00:10Z"},
                "QQQ": {"bp": 500.00, "ap": 500.00,
                        "t": "1970-01-01T00:00:10Z"},
            }},
            {"quotes": {
                "COIN": {"bp": 100.01, "ap": 100.01, "bs": 1, "as": 1,
                         "t": "1970-01-01T00:00:10.250000Z"},
                "QQQ": {"bp": 500.01, "ap": 500.01,
                        "t": "1970-01-01T00:00:10.250000Z"},
            }},
        ))
        state = MagicMock(spec=LiveMarketState)

        def response(*args, **kwargs):
            return BytesIO(json.dumps(next(payloads)).encode())

        with patch.dict(os.environ, {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}), \
                patch("quant.live_market.urlopen", side_effect=response) as urlopen, \
                patch("quant.live_market.time.sleep", side_effect=[None, RuntimeError("stop")]):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_alpaca(state, monotonic=iter((0.0, 0.25)).__next__)

        self.assertEqual(urlopen.call_count, 2)
        self.assertTrue(all(call.args[0].full_url == ALPACA_LATEST_QUOTES_URL
                            for call in urlopen.call_args_list))
        self.assertEqual(state.update_market_display.call_count, 2)
        self.assertEqual(state.accept_quote.call_count, 1)
        self.assertEqual(state.accept_qqq_quote.call_count, 1)
        self.assertEqual(
            state.update_market_display.call_args_list[1].kwargs["coin_midpoint"],
            100.01,
        )

    def test_valid_quote_creates_midpoint_and_preserves_timestamp(self):
        state = LiveMarketState(clock=lambda: 101.0)
        self.assertTrue(state.accept_quote(bid=99.0, ask=101.0, event_epoch=100.25))
        observation = state.snapshot().history.latest
        self.assertEqual(observation.midpoint, 100.0)
        self.assertEqual(observation.event_epoch, 100.25)

    def test_invalid_quotes_are_rejected(self):
        state = LiveMarketState()
        for bid, ask in ((0, 1), (1, 0), (2, 1), (-1, 1), (1, float("nan"))):
            self.assertFalse(state.accept_quote(bid=bid, ask=ask, event_epoch=1.0))
        self.assertEqual(state.snapshot().history.count, 0)

    def test_late_or_future_observation_cannot_leak_backward(self):
        state = LiveMarketState()
        self.assertTrue(state.accept_quote(bid=100, ask=102, event_epoch=20.0))
        self.assertFalse(state.accept_quote(bid=200, ask=202, event_epoch=10.0))
        self.assertEqual(state.snapshot().history.latest.midpoint, 101.0)

    def test_history_is_chronological_and_q1_q3_use_it(self):
        state = LiveMarketState(clock=lambda: 9999.0)
        for second in range(0, 3601, 30):
            self.assertTrue(
                state.accept_quote(
                    bid=100.0 + second / 100.0,
                    ask=102.0 + second / 100.0,
                    event_epoch=float(second),
                )
            )
        snapshot = state.snapshot()
        epochs = [item.event_epoch for item in snapshot.history.observations]
        self.assertEqual(epochs, sorted(epochs))
        self.assertTrue(all(value is not None for value in snapshot.momentum.forecast_bps))
        self.assertTrue(all(value is not None for value in snapshot.mean_reversion.forecast_bps))
        self.assertTrue(all(value is not None for value in snapshot.volatility.volatility_bps))

    def test_dashboard_updates_with_no_fake_unimplemented_values(self):
        state = LiveMarketState(clock=lambda: 1001.0)
        app = create_app(state=state, clock=lambda: 1002.0)
        before = request_json(app)
        self.assertIsNone(before["market"]["symbol"])

        state.accept_quote(bid=100.0, ask=102.0, event_epoch=1000.0)
        state.accept_g2_price(asset="BTC", price=60_000.0, event_epoch=1000.0)
        state.accept_g2_price(asset="NDX", price=23_812.125, event_epoch=1000.0)
        after = request_json(app)
        self.assertEqual(after["market"]["symbol"], 101.0)
        self.assertEqual(after["market"]["btc"], 60_000.0)
        self.assertEqual(after["market"]["ndx"], 23_812.125)
        self.assertEqual(after["market"]["data_age"], 2.0)
        self.assertEqual(after["market"]["last_cycle"], 1001.0)
        self.assertTrue(all(value is None for family in after["quant_families"][:3] for value in family["values"]))
        self.assertTrue(all(family["values"] == [None] * 6 for family in after["quant_families"][3:]))
        self.assertTrue(all(values == [None] * 6 for values in after["final_numbers"].values()))
        self.assertEqual(after["options_data"], {"expiration": None, "calls": [], "puts": []})

    def test_alpaca_event_timestamp_parser(self):
        self.assertEqual(parse_alpaca_timestamp("1970-01-01T00:00:01Z"), 1.0)

    def test_alpaca_ndx_latest_value_contract_preserves_value_and_event_time(self):
        self.assertEqual(
            ALPACA_NDX_LATEST_VALUE_URL,
            "https://data.alpaca.markets/v1beta1/indices/latest/values?index_symbols=NDX",
        )
        price, event_epoch = parse_alpaca_ndx_value({
            "values": {
                "NDX": {
                    "v": 23_812.125,
                    "t": "2026-08-21T14:30:05.123456Z",
                },
            },
        })
        self.assertEqual(price, 23_812.125)
        self.assertEqual(
            event_epoch,
            parse_alpaca_timestamp("2026-08-21T14:30:05.123456Z"),
        )

    def test_malformed_or_unavailable_alpaca_ndx_value_is_rejected(self):
        malformed = (
            None,
            {},
            {"values": {}},
            {"values": {"NDX": None}},
            {"values": {"NDX": {"t": "2026-08-21T14:30:05Z"}}},
            {"values": {"NDX": {"v": "23812.125", "t": "2026-08-21T14:30:05Z"}}},
            {"values": {"NDX": {"v": 23_812.125, "t": "bad"}}},
        )
        for payload in malformed:
            with self.subTest(payload=payload), self.assertRaises(
                (KeyError, TypeError, ValueError),
            ):
                parse_alpaca_ndx_value(payload)

    def test_massive_ndx_snapshot_preserves_real_time_value_and_event_time(self):
        self.assertEqual(
            MASSIVE_NDX_SNAPSHOT_URL,
            "https://api.massive.com/v3/snapshot/indices?ticker=I%3ANDX",
        )
        price, event_epoch = parse_massive_ndx_snapshot({
            "results": [{
                "ticker": "I:NDX",
                "timeframe": "REAL-TIME",
                "value": 23_812.125,
                "last_updated": 100_250_000_000,
            }],
        })
        self.assertEqual(price, 23_812.125)
        self.assertEqual(event_epoch, 100.25)

    def test_massive_ndx_snapshot_rejects_delayed_or_malformed_data(self):
        malformed = (
            None,
            {},
            {"results": []},
            {"results": [{"ticker": "I:SPX"}]},
            {"results": [{
                "ticker": "I:NDX", "timeframe": "DELAYED",
                "value": 23_812.125, "last_updated": 100_000_000_000,
            }]},
            {"results": [{
                "ticker": "I:NDX", "timeframe": "REAL-TIME",
                "value": "23812.125", "last_updated": 100_000_000_000,
            }]},
        )
        for payload in malformed:
            with self.subTest(payload=payload), self.assertRaises(
                    (TypeError, ValueError)):
                parse_massive_ndx_snapshot(payload)

    def test_future_ndx_provider_timestamp_is_not_synchronized(self):
        state = LiveMarketState(clock=lambda: 100.0)
        self.assertFalse(
            state.accept_g2_price(asset="NDX", price=23_812.125, event_epoch=100.001)
        )
        value = state.cross_asset_state()
        self.assertIsNone(value.ndx_price)
        self.assertIsNone(value.ndx_age_seconds)

    def test_g2_poller_requests_only_btc_and_leaves_ndx_missing(self):
        state = LiveMarketState(clock=lambda: 2.0)
        response = BytesIO(json.dumps({
            "quotes": {
                "BTC/USD": {
                    "bp": 100.0,
                    "ap": 102.0,
                    "t": "1970-01-01T00:00:01Z",
                },
            },
        }).encode())

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key",
            "ALPACA_SECRET_KEY": "secret",
        }), patch(
            "quant.live_market.urlopen", return_value=response,
        ) as urlopen, patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_alpaca_g2(state, clock=lambda: 2.0,
                               monotonic=iter((10.0, 10.002)).__next__)

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.kwargs["timeout"],
                         BTC_SOURCE_TIMEOUT_SECONDS)
        self.assertEqual(
            urlopen.call_args.args[0].full_url, ALPACA_BTC_LATEST_QUOTE_URL,
        )
        value = state.cross_asset_state()
        self.assertEqual(value.btc_price, 101.0)
        telemetry = state.metrics.snapshot()
        distributions = dict(telemetry.distributions)
        self.assertEqual(distributions["btc_quote_age_ms"].p50, 1000.0)
        self.assertAlmostEqual(distributions["btc_ingest_latency_ms"].p50, 2.0)
        self.assertEqual(dict(telemetry.statuses)["btc_source_status"], "LIVE")
        self.assertIsNone(value.ndx_price)
        self.assertIsNone(value.ndx_age_seconds)
        self.assertEqual(value.ndx_return_bps, (None,) * 6)

    def test_repeated_latest_btc_quote_remains_live_and_is_not_duplicated(self):
        state = LiveMarketState(clock=lambda: 2.0)
        payload = json.dumps({"quotes": {"BTC/USD": {
            "bp": 100.0, "ap": 102.0, "t": "1970-01-01T00:00:01Z",
        }}}).encode()
        responses = [BytesIO(payload), BytesIO(payload)]

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }), patch(
            "quant.live_market.urlopen", side_effect=responses,
        ) as urlopen, patch(
            "quant.live_market.time.sleep", side_effect=(None, RuntimeError("stop")),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_alpaca_g2(state, clock=lambda: 2.0)

        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(len(state._btc_history.observations), 1)
        self.assertEqual(
            dict(state.metrics.snapshot().statuses)["btc_source_status"], "LIVE",
        )

    def test_btc_failure_is_single_attempt_and_cannot_enter_coin_path(self):
        state = MagicMock(spec=LiveMarketState)
        state.metrics = LiveMarketState().metrics
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }), patch(
            "quant.live_market.urlopen", side_effect=TimeoutError("slow source"),
        ) as source, patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_alpaca_g2(state)

        source.assert_called_once()
        self.assertEqual(source.call_args.kwargs["timeout"],
                         BTC_SOURCE_TIMEOUT_SECONDS)
        state.accept_quote.assert_not_called()
        state.accept_qqq_quote.assert_not_called()
        state.accept_g2_price.assert_not_called()
        self.assertEqual(
            dict(state.metrics.snapshot().statuses)["btc_source_status"],
            "UNAVAILABLE",
        )

    def test_blocked_btc_source_does_not_block_coin_or_live_response(self):
        state = LiveMarketState(clock=lambda: 101.0)
        source_entered = threading.Event()
        release_source = threading.Event()

        def blocked_source(*_args, **_kwargs):
            source_entered.set()
            self.assertTrue(release_source.wait(timeout=2))
            raise TimeoutError("bounded BTC timeout")

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }), patch(
            "quant.live_market.urlopen", side_effect=blocked_source,
        ), patch("quant.live_market.time.sleep", side_effect=RuntimeError("stop")):
            def run_poller():
                try:
                    poll_alpaca_g2(state)
                except RuntimeError as error:
                    self.assertEqual(str(error), "stop")

            worker = threading.Thread(target=run_poller)
            worker.start()
            self.assertTrue(source_entered.wait(timeout=1))
            self.assertTrue(state.accept_quote(
                bid=99.0, ask=101.0, event_epoch=100.0))
            response = request_json(create_app(state=state, clock=lambda: 101.0))
            self.assertEqual(response["market"]["symbol"], 100.0)
            release_source.set()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())

    def test_stale_btc_is_excluded_without_replacing_last_valid_timestamp(self):
        state = LiveMarketState(clock=lambda: 100.0)
        self.assertTrue(state.accept_g2_price(
            asset="BTC", price=99.0, event_epoch=99.0))
        response = BytesIO(json.dumps({"quotes": {"BTC/USD": {
            "bp": 100.0, "ap": 102.0, "t": "1970-01-01T00:01:30Z",
        }}}).encode())
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }), patch(
            "quant.live_market.urlopen", return_value=response,
        ), patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_alpaca_g2(state, clock=lambda: 100.0)

        value = state.cross_asset_state()
        self.assertEqual(value.btc_price, 99.0)
        self.assertEqual(state._btc_history.latest.event_epoch, 99.0)
        self.assertEqual(MAX_BTC_AGE_SECONDS, 5.0)
        self.assertEqual(BTC_FETCH_SECONDS, 0.25)
        self.assertEqual(
            dict(state.metrics.snapshot().statuses)["btc_source_status"],
            "UNAVAILABLE",
        )

    def test_massive_ndx_poller_stops_after_one_forbidden_response(self):
        state = LiveMarketState(clock=lambda: 101.0)
        forbidden = HTTPError(
            MASSIVE_NDX_SNAPSHOT_URL, 403, "Forbidden", {}, None,
        )

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "key"}), patch(
            "quant.live_market.urlopen", side_effect=forbidden,
        ) as urlopen, patch(
            "quant.live_market.time.sleep",
        ) as sleep, patch(
            "builtins.print",
        ) as print_message:
            poll_massive_ndx(state)

        urlopen.assert_called_once()
        sleep.assert_not_called()
        print_message.assert_called_once_with(
            "Massive NDX access is forbidden/unavailable", flush=True,
        )
        self.assertIsNone(state.cross_asset_state().ndx_price)

    def test_massive_ndx_poller_retries_non_forbidden_http_failure(self):
        state = LiveMarketState(clock=lambda: 101.0)
        transient = HTTPError(
            MASSIVE_NDX_SNAPSHOT_URL, 503, "Unavailable", {}, None,
        )

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "key"}), patch(
            "quant.live_market.urlopen", side_effect=transient,
        ) as urlopen, patch(
            "quant.live_market.time.sleep", side_effect=[None, RuntimeError("stop")],
        ), patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_massive_ndx(state)

        self.assertEqual(urlopen.call_count, 2)
        self.assertIsNone(state.cross_asset_state().ndx_price)

    def test_massive_ndx_poller_uses_bearer_key_and_accepts_only_fresh_data(self):
        state = LiveMarketState(clock=lambda: 101.0)
        response = BytesIO(json.dumps({
            "results": [{
                "ticker": "I:NDX",
                "timeframe": "REAL-TIME",
                "value": 23_812.125,
                "last_updated": 100_000_000_000,
            }],
        }).encode())

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "key"}), patch(
            "quant.live_market.urlopen", return_value=response,
        ) as urlopen, patch(
            "quant.live_market.time.time", return_value=101.0,
        ), patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_massive_ndx(state)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, MASSIVE_NDX_SNAPSHOT_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer key")
        self.assertEqual(state.cross_asset_state().ndx_price, 23_812.125)

    def test_massive_ndx_poller_rejects_ten_second_old_data(self):
        state = LiveMarketState(clock=lambda: 110.0)
        response = BytesIO(json.dumps({
            "results": [{
                "ticker": "I:NDX",
                "timeframe": "REAL-TIME",
                "value": 23_812.125,
                "last_updated": 100_000_000_000,
            }],
        }).encode())

        with patch.dict(os.environ, {"MASSIVE_API_KEY": "key"}), patch(
            "quant.live_market.urlopen", return_value=response,
        ), patch(
            "quant.live_market.time.time", return_value=110.0,
        ), patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_massive_ndx(state)

        self.assertIsNone(state.cross_asset_state().ndx_price)


if __name__ == "__main__":
    unittest.main()