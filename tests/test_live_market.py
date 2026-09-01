import json
from dataclasses import FrozenInstanceError
from io import BytesIO
import os
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from quant.live_market import (
    ALPACA_BTC_STREAM_URL_TEMPLATE, ALPACA_CRYPTO_LOCATION_DEFAULT,
    ALPACA_LATEST_QUOTES_URL, BTC_HISTORY_MAX_OBSERVATIONS,
    BTC_PUBLISH_INTERVAL_SECONDS, BTC_RECONNECT_SECONDS,
    BTC_SOURCE_TIMEOUT_SECONDS, MAX_BTC_AGE_SECONDS,
    ALPACA_NDX_LATEST_VALUE_URL, MARKET_DISPLAY_FETCH_SECONDS, LiveMarketState,
    MASSIVE_NDX_SNAPSHOT_URL, alpaca_btc_stream_url, parse_alpaca_ndx_value,
    COIN_MARKET_PASSWORD_ENV, COIN_MARKET_USERNAME_ENV,
    SCHWAB_NDX_ENABLED_ENV, SCHWAB_NDX_QUOTE_URL,
    parse_alpaca_timestamp, parse_massive_ndx_snapshot, parse_schwab_ndx_quote,
    poll_alpaca, poll_alpaca_g2, poll_massive_ndx, poll_schwab_ndx,
    start_massive_ndx_poller,
)
from quant.web import create_app
from quant.history import MidpointObservation


def request_json(app):
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app({"PATH_INFO": "/api/dashboard"}, start_response))
    return json.loads(body)


def request_path_json(app, path):
    response = {}
    def start_response(status, _headers): response["status"] = status
    body = b"".join(app({"PATH_INFO": path}, start_response))
    return response["status"], json.loads(body)


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

    def test_owner_handoff_uses_durable_watermark_and_never_replays_overlap(self):
        ready = [False]
        anchor = MidpointObservation(2.0, 101.0)

        class CapturingOutbox:
            def __init__(self): self.items = []
            def remaining_capacity(self): return 256 - len(self.items)
            def put_nowait(self, item): self.items.append(item); return True

        outbox = CapturingOutbox()
        state = LiveMarketState(
            clock=lambda: 10.0, evidence_outbox=outbox,
            evidence_acceptance_ready=lambda: ready[0],
            evidence_handoff_anchor=lambda: anchor if ready[0] else None,
        )
        state.update_market_display(
            coin_midpoint=100.0, coin_event_epoch=1.0)
        self.assertTrue(state.accept_quote(
            bid=99.0, ask=101.0, event_epoch=1.0))
        self.assertTrue(state.accept_quote(
            bid=100.0, ask=102.0, event_epoch=2.0))
        self.assertEqual(outbox.items, [])
        self.assertIsNone(state.publication().market_display.coin_event_epoch)
        self.assertIsNone(state.publication().snapshot.history.latest)

        ready[0] = True
        state.update_market_display(
            coin_midpoint=102.0, coin_event_epoch=3.0)
        # The raw display remains frozen until the first owned V9/evidence cycle.
        self.assertIsNone(state.publication().market_display.coin_event_epoch)
        self.assertTrue(state.accept_quote(
            bid=101.0, ask=103.0, event_epoch=3.0))

        self.assertEqual(len(outbox.items), 1)
        self.assertEqual(outbox.items[0].previous_observation, anchor)
        self.assertEqual(outbox.items[0].current_observation.event_epoch, 3.0)
        self.assertEqual(state.publication().market_display.coin_event_epoch, 3.0)
        self.assertEqual(
            tuple(item.event_epoch for item in state.snapshot().history.observations),
            (2.0, 3.0),
        )

    def test_reacquired_owner_rebases_nonempty_history_to_new_durable_anchor(self):
        ready = [True]
        anchor = [MidpointObservation(9.0, 100.0)]

        class CapturingOutbox:
            def __init__(self): self.items = []
            def remaining_capacity(self): return 256 - len(self.items)
            def put_nowait(self, item): self.items.append(item); return True

        outbox = CapturingOutbox()
        state = LiveMarketState(
            clock=lambda: 20.0, evidence_outbox=outbox,
            evidence_acceptance_ready=lambda: ready[0],
            evidence_handoff_anchor=lambda: anchor[0] if ready[0] else None,
        )
        self.assertTrue(state.accept_quote(
            bid=100.0, ask=102.0, event_epoch=10.0))
        ready[0] = False
        for epoch in (11.0, 12.0, 13.0):
            self.assertTrue(state.accept_quote(
                bid=epoch + 90.0, ask=epoch + 92.0,
                event_epoch=epoch))

        # Another owner persisted through t=12 while this process was waiting.
        anchor[0] = MidpointObservation(12.0, 103.0)
        ready[0] = True
        self.assertTrue(state.accept_quote(
            bid=104.0, ask=106.0, event_epoch=14.0))

        brackets = [
            (item.previous_observation.event_epoch,
             item.current_observation.event_epoch)
            for item in outbox.items
        ]
        self.assertEqual(brackets, [(9.0, 10.0), (12.0, 13.0), (13.0, 14.0)])
        self.assertEqual(
            tuple(item.event_epoch for item in
                  state.input_snapshot().history.observations),
            (9.0, 10.0, 12.0, 13.0, 14.0),
        )

    def test_reacquisition_between_quotes_still_rebases_to_durable_anchor(self):
        ready = [True]
        generation = [1]
        anchor = [MidpointObservation(9.0, 100.0)]

        class CapturingOutbox:
            def __init__(self): self.items = []
            def remaining_capacity(self): return 256 - len(self.items)
            def put_nowait(self, item): self.items.append(item); return True

        outbox = CapturingOutbox()
        state = LiveMarketState(
            evidence_outbox=outbox,
            evidence_acceptance_ready=lambda: ready[0],
            evidence_handoff_anchor=lambda: anchor[0] if ready[0] else None,
            evidence_owner_generation=lambda: generation[0] if ready[0] else None,
        )
        self.assertTrue(state.accept_quote(
            bid=100.0, ask=102.0, event_epoch=10.0))

        # No quote observes this process's ownership-loss interval.
        ready[0] = False
        anchor[0] = MidpointObservation(12.0, 103.0)
        generation[0] = 2
        ready[0] = True
        self.assertTrue(state.accept_quote(
            bid=104.0, ask=106.0, event_epoch=13.0))

        self.assertEqual([
            (item.previous_observation.event_epoch,
             item.current_observation.event_epoch)
            for item in outbox.items
        ], [(9.0, 10.0), (12.0, 13.0)])
        self.assertEqual(
            tuple(item.event_epoch for item in
                  state.input_snapshot().history.observations),
            (9.0, 10.0, 12.0, 13.0),
        )
        self.assertEqual(dict(state.metrics.snapshot().counters)[
            "evidence_handoff.owner_rebase"], 1)

    def test_new_owner_generation_rebases_even_when_local_history_is_ahead(self):
        ready = [True]
        generation = [1]
        anchor = [MidpointObservation(9.0, 100.0)]

        class CapturingOutbox:
            def __init__(self): self.items = []
            def remaining_capacity(self): return 256 - len(self.items)
            def put_nowait(self, item): self.items.append(item); return True

        outbox = CapturingOutbox()
        state = LiveMarketState(
            evidence_outbox=outbox,
            evidence_acceptance_ready=lambda: ready[0],
            evidence_handoff_anchor=lambda: anchor[0] if ready[0] else None,
            evidence_owner_generation=lambda: generation[0] if ready[0] else None,
        )
        self.assertTrue(state.accept_quote(
            bid=104.0, ask=106.0, event_epoch=13.0))

        # Local t=13 is still unacknowledged when a different owner advances
        # only to t=12; no quote observes the loss interval in this process.
        ready[0] = False
        anchor[0] = MidpointObservation(12.0, 103.0)
        generation[0] = 2
        ready[0] = True
        self.assertTrue(state.accept_quote(
            bid=105.0, ask=107.0, event_epoch=14.0))

        self.assertEqual([
            (item.previous_observation.event_epoch,
             item.current_observation.event_epoch)
            for item in outbox.items
        ], [(9.0, 13.0), (12.0, 14.0)])
        self.assertEqual(
            tuple(item.event_epoch for item in
                  state.input_snapshot().history.observations),
            (9.0, 12.0, 14.0),
        )

    def test_shutdown_rebases_owned_tail_after_reacquisition(self):
        ready = [True]
        anchor = [MidpointObservation(9.0, 100.0)]

        class CapturingOutbox:
            def __init__(self): self.items = []
            def remaining_capacity(self): return 256 - len(self.items)
            def put_nowait(self, item): self.items.append(item); return True

        outbox = CapturingOutbox()
        state = LiveMarketState(
            evidence_outbox=outbox,
            evidence_acceptance_ready=lambda: ready[0],
            evidence_handoff_anchor=lambda: anchor[0] if ready[0] else None,
        )
        self.assertTrue(state.accept_quote(
            bid=100.0, ask=102.0, event_epoch=10.0))
        ready[0] = False
        for epoch in (11.0, 12.0, 13.0):
            self.assertTrue(state.accept_quote(
                bid=epoch + 90.0, ask=epoch + 92.0,
                event_epoch=epoch))
        anchor[0] = MidpointObservation(12.0, 103.0)
        ready[0] = True
        state.stop_accepting_quotes()

        tail = outbox.items[-1]
        self.assertEqual(tail.previous_observation.event_epoch, 12.0)
        self.assertEqual(tail.current_observation.event_epoch, 13.0)

    def test_shutdown_drains_owned_handoff_tail_but_discards_non_owner_overlap(self):
        ready = [False]
        anchor = MidpointObservation(2.0, 101.0)
        class CapturingOutbox:
            def __init__(self): self.items = []
            def remaining_capacity(self): return 256 - len(self.items)
            def put_nowait(self, item): self.items.append(item); return True
        outbox = CapturingOutbox()
        state = LiveMarketState(
            clock=lambda: 10.0, evidence_outbox=outbox,
            evidence_acceptance_ready=lambda: ready[0],
            evidence_handoff_anchor=lambda: anchor if ready[0] else None,
        )
        for epoch in (1.0, 2.0, 3.0):
            self.assertTrue(state.accept_quote(
                bid=99.0 + epoch, ask=101.0 + epoch, event_epoch=epoch))
        ready[0] = True
        state.stop_accepting_quotes()
        self.assertEqual(len(outbox.items), 1)
        self.assertEqual(outbox.items[0].previous_observation, anchor)
        self.assertEqual(outbox.items[0].current_observation.event_epoch, 3.0)

        waiting_outbox = CapturingOutbox()
        waiting = LiveMarketState(
            evidence_outbox=waiting_outbox,
            evidence_acceptance_ready=lambda: False,
        )
        self.assertTrue(waiting.accept_quote(
            bid=99.0, ask=101.0, event_epoch=1.0))
        waiting.stop_accepting_quotes()
        self.assertEqual(waiting_outbox.items, [])
        self.assertEqual(dict(waiting.metrics.snapshot().counters)[
            "evidence_handoff.non_owner_shutdown"], 1)

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
        self.assertEqual(after["options_data"], {
            "status": "UNAVAILABLE", "as_of_epoch": None,
            "expiration": None, "calls": [], "puts": [],
        })

    def test_btc_remains_visible_while_evidence_owner_is_waiting(self):
        state = LiveMarketState(
            clock=lambda: 1001.0,
            evidence_acceptance_ready=lambda: False,
        )
        self.assertTrue(state.accept_g2_price(
            asset="BTC", price=60_000.0, event_epoch=1000.0,
            max_age_seconds=MAX_BTC_AGE_SECONDS,
        ))
        state.metrics.set_status("btc_source_status", "LIVE")

        payload = request_json(create_app(state=state, clock=lambda: 1002.0))

        self.assertEqual(payload["market"]["btc"], 60_000.0)
        self.assertEqual(payload["market"]["btc_display"], 60_000.0)
        self.assertEqual(payload["market"]["btc_source_status"], "LIVE")
        self.assertIsNone(payload["market"]["symbol"])

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

    def test_g2_stream_authenticates_subscribes_and_preserves_provider_time(self):
        state = LiveMarketState(clock=lambda: 2.0)
        stop = threading.Event()

        class Stream:
            def __init__(self):
                self.sent = []; self.closed = False
                self.messages = [
                    '[{"T":"success","msg":"connected"}]',
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    ('[{"T":"q","S":"BTC/USD","bp":100.0,"bs":1.0,'
                     '"ap":102.0,"as":1.0,"t":"1970-01-01T00:00:01Z"}]'),
                ]
            def send(self, value): self.sent.append(json.loads(value))
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): self.closed = True

        stream = Stream()
        factory = MagicMock(return_value=stream)

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key",
            "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, clock=lambda: 2.0, monotonic=lambda: 10.0,
                stop_event=stop, websocket_factory=factory,
            )

        factory.assert_called_once_with(
            ALPACA_BTC_STREAM_URL_TEMPLATE.format(
                location=ALPACA_CRYPTO_LOCATION_DEFAULT),
            timeout=BTC_SOURCE_TIMEOUT_SECONDS,
        )
        self.assertEqual(factory.call_args.kwargs["timeout"],
                         BTC_SOURCE_TIMEOUT_SECONDS)
        self.assertEqual(stream.sent, [
            {"action": "auth", "key": "key", "secret": "secret"},
            {"action": "subscribe", "quotes": ["BTC/USD"]},
        ])
        self.assertTrue(stream.closed)
        value = state.cross_asset_state()
        self.assertEqual(value.btc_price, 101.0)
        self.assertEqual(state._btc_history.latest.event_epoch, 1.0)
        telemetry = state.metrics.snapshot()
        distributions = dict(telemetry.distributions)
        self.assertEqual(distributions["btc_quote_age_ms"].p50, 1000.0)
        self.assertEqual(distributions["btc_ingest_latency_ms"].p50, 0.0)
        self.assertEqual(dict(telemetry.statuses)["btc_source_status"], "LIVE")
        self.assertEqual(dict(telemetry.statuses)["btc_stream_location"],
                         ALPACA_CRYPTO_LOCATION_DEFAULT)
        self.assertIsNone(value.ndx_price)
        self.assertIsNone(value.ndx_age_seconds)
        self.assertEqual(value.ndx_return_bps, (None,) * 6)

    def test_repeated_stream_quote_remains_live_and_is_not_duplicated(self):
        state = LiveMarketState(clock=lambda: 2.0)
        stop = threading.Event()
        quote = ('[{"T":"q","S":"BTC/USD","bp":100.0,"ap":102.0,'
                 '"t":"1970-01-01T00:00:01Z"}]')

        class Stream:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    quote, quote,
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, clock=lambda: 2.0, monotonic=lambda: 0.0,
                stop_event=stop, websocket_factory=lambda *_args, **_kwargs: Stream(),
            )

        self.assertEqual(len(state._btc_history.observations), 1)
        self.assertEqual(
            dict(state.metrics.snapshot().statuses)["btc_source_status"], "LIVE",
        )

    def test_distinct_nanosecond_quotes_do_not_collapse_into_a_false_conflict(self):
        first = "2024-07-24T07:38:06.884904780Z"
        second = "2024-07-24T07:38:06.884904791Z"
        now = parse_alpaca_timestamp(second) + 1.0
        state = LiveMarketState(clock=lambda: now)
        stop = threading.Event()

        class Stream:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    json.dumps([
                        {"T": "q", "S": "BTC/USD", "bp": 100.0,
                         "ap": 102.0, "t": first},
                        {"T": "q", "S": "BTC/USD", "bp": 101.0,
                         "ap": 103.0, "t": second},
                    ]),
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, clock=lambda: now, monotonic=lambda: 0.0,
                stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: Stream(),
            )

        telemetry = state.metrics.snapshot()
        self.assertNotIn("btc_stream.timestamp_conflict",
                         dict(telemetry.counters))
        self.assertNotIn("btc_stream.control_error", dict(telemetry.counters))
        self.assertEqual(dict(telemetry.statuses)["btc_source_status"], "LIVE")
        self.assertEqual(len(state._btc_history.observations), 1)

    def test_no_data_after_subscription_keeps_exponential_backoff(self):
        state = LiveMarketState(clock=lambda: 0.0)

        class Stop:
            def __init__(self): self.waits = []
            def is_set(self): return False
            def wait(self, seconds):
                self.waits.append(seconds)
                return len(self.waits) == 3
        stop = Stop()

        class NoData:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    None,
                ]
            def send(self, _value): pass
            def recv(self): return self.messages.pop(0)
            def close(self): pass

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, interval=1.0, clock=lambda: 0.0,
                stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: NoData(),
            )

        self.assertEqual(stop.waits, [1.0, 2.0, 4.0])

    def test_quote_that_becomes_stale_at_atomic_acceptance_is_never_stored(self):
        now = [2.0]
        state = LiveMarketState(clock=lambda: now[0])
        original_accept = state.accept_g2_price
        stop = threading.Event()

        def delayed_accept(**kwargs):
            now[0] = 7.0
            return original_accept(**kwargs)
        state.accept_g2_price = delayed_accept

        class Stream:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    ('[{"T":"q","S":"BTC/USD","bp":100.0,'
                     '"ap":102.0,"t":"1970-01-01T00:00:01Z"}]'),
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, clock=lambda: now[0], stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: Stream(),
            )

        self.assertIsNone(state.btc_latest_observation())
        telemetry = state.metrics.snapshot()
        self.assertEqual(dict(telemetry.counters)[
            "btc_stream.quote_rejected"], 1)
        self.assertEqual(dict(telemetry.statuses)[
            "btc_source_failure_reason"], "QUOTE_REJECTED")

    def test_btc_connection_failure_retries_without_entering_coin_path(self):
        state = MagicMock(spec=LiveMarketState)
        state.metrics = LiveMarketState().metrics
        source = MagicMock(side_effect=TimeoutError("slow source"))
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False), patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_alpaca_g2(state, websocket_factory=source)

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
        }, clear=False), patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop")):
            def run_poller():
                try:
                    poll_alpaca_g2(state, websocket_factory=blocked_source)
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
        stop = threading.Event()

        class Stream:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    ('[{"T":"q","S":"BTC/USD","bp":100.0,"ap":102.0,'
                     '"t":"1970-01-01T00:01:30Z"}]'),
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, clock=lambda: 100.0, stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: Stream(),
            )

        value = state.cross_asset_state()
        self.assertEqual(value.btc_price, 99.0)
        self.assertEqual(state._btc_history.latest.event_epoch, 99.0)
        self.assertEqual(MAX_BTC_AGE_SECONDS, 5.0)
        self.assertEqual(BTC_RECONNECT_SECONDS, 1.0)
        self.assertEqual(
            dict(state.metrics.snapshot().statuses)["btc_source_status"],
            "UNAVAILABLE",
        )

    def test_btc_stream_watchdog_and_connection_limit_recovery(self):
        state = LiveMarketState(clock=lambda: 10.0)
        stop = threading.Event()

        class Limited:
            def send(self, _value): pass
            def recv(self):
                return '[{"T":"error","code":406,"msg":"connection limit exceeded"}]'
            def close(self): pass
        class Recovered:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    ('[{"T":"q","S":"BTC/USD","bp":100.0,"ap":102.0,'
                     '"t":"1970-01-01T00:00:09Z"}]'),
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass

        factory = MagicMock(side_effect=(Limited(), Recovered()))
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, interval=0.0, clock=lambda: 10.0,
                monotonic=lambda: 0.0, stop_event=stop,
                websocket_factory=factory,
            )

        telemetry = state.metrics.snapshot()
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(dict(telemetry.counters)["btc_stream.connection_limit"], 1)
        self.assertEqual(dict(telemetry.statuses)["btc_source_status"], "LIVE")

    def test_btc_stream_watchdog_fails_closed_after_five_silent_seconds(self):
        state = LiveMarketState(clock=lambda: 0.0)
        stop = threading.Event()

        class WebSocketTimeoutException(Exception): pass
        class Silent:
            def __init__(self): self.calls = 0
            def send(self, _value): pass
            def recv(self):
                self.calls += 1
                if self.calls == 2:
                    stop.set()
                raise WebSocketTimeoutException("no provider event")
            def close(self): pass

        clock = iter((0.0, 4.9, 5.0)).__next__
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, clock=clock, stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: Silent(),
            )

        telemetry = state.metrics.snapshot()
        self.assertEqual(
            dict(telemetry.counters)["btc_stream.watchdog_unavailable"], 1)
        self.assertEqual(
            dict(telemetry.statuses)["btc_source_status"], "UNAVAILABLE")

    def test_btc_stream_location_is_allowlisted(self):
        self.assertEqual(ALPACA_CRYPTO_LOCATION_DEFAULT, "us-1")
        with patch.dict(os.environ, {"ALPACA_CRYPTO_LOCATION": "invalid"}):
            with self.assertRaisesRegex(ValueError, "allowlisted"):
                alpaca_btc_stream_url()

    def test_btc_api_status_and_ui_value_are_derived_from_provider_age(self):
        state = LiveMarketState(clock=lambda: 1.0)
        self.assertTrue(state.accept_g2_price(
            asset="BTC", price=101.0, event_epoch=1.0))
        state.metrics.set_status("btc_source_status", "LIVE")
        state.metrics.set_status("btc_stream_location", "us")
        app = create_app(state=state, clock=lambda: 10.0)

        for path in ("/api/live", "/api/dashboard"):
            status, payload = request_path_json(app, path)
            self.assertEqual(status, "200 OK")
            market = payload["market"]
            self.assertEqual(market["btc"], 101.0)
            self.assertEqual(market["btc_event_epoch"], 1.0)
            self.assertEqual(market["btc_data_age"], 9.0)
            self.assertEqual(market["btc_source_status"], "UNAVAILABLE")
            self.assertIsNone(market["btc_display"])
            self.assertEqual(market["btc_stream_location"], "us")

        html = b"".join(create_app(
            state=state, clock=lambda: 10.0)(
                {"PATH_INFO": "/"}, lambda _status, _headers: None)).decode()
        self.assertIn('data-dashboard-field="market.btc"></div>', html)

    def test_malformed_traffic_cannot_mask_stale_stream_and_reconnects(self):
        state = LiveMarketState(clock=lambda: now[0])
        stop = threading.Event()
        now = [0.0]

        class StaleTraffic:
            def __init__(self):
                self.messages = [
                    (0.0, '[{"T":"success","msg":"authenticated"}]'),
                    (0.0, '[{"T":"subscription","quotes":["BTC/USD"]}]'),
                    (5.1, "not-json"),
                ]
                self.closed = False
            def send(self, _value): pass
            def recv(self):
                now[0], value = self.messages.pop(0)
                return value
            def close(self): self.closed = True

        class Fresh:
            def __init__(self):
                self.messages = [
                    (6.0, '[{"T":"success","msg":"authenticated"}]'),
                    (6.0, '[{"T":"subscription","quotes":["BTC/USD"]}]'),
                    (6.5, ('[{"T":"q","S":"BTC/USD","bp":100.0,'
                           '"ap":102.0,"t":"1970-01-01T00:00:06Z"}]')),
                ]
            def send(self, _value): pass
            def recv(self):
                now[0], value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass

        stale, fresh = StaleTraffic(), Fresh()
        factory = MagicMock(side_effect=(stale, fresh))
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, interval=0.0, clock=lambda: now[0],
                monotonic=lambda: 0.0, stop_event=stop,
                websocket_factory=factory,
            )

        telemetry = state.metrics.snapshot()
        self.assertTrue(stale.closed)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(dict(telemetry.counters)[
            "btc_stream.watchdog_reconnect"], 1)
        self.assertEqual(dict(telemetry.statuses)["btc_source_status"], "LIVE")
        self.assertEqual(state.btc_latest_observation().event_epoch, 6.0)

    def test_stream_burst_is_coalesced_and_history_has_a_hard_cap(self):
        state = LiveMarketState(clock=lambda: 20.0)
        stop = threading.Event()
        quotes = ",".join(
            ('{"T":"q","S":"BTC/USD","bp":100.0,"ap":102.0,'
             f'"t":"1970-01-01T00:00:{16.0 + index * .01:05.2f}Z"}}')
            for index in range(400)
        )

        class Burst:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    "[" + quotes + "]",
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass

        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, clock=lambda: 20.0, monotonic=lambda: 0.0,
                stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: Burst(),
            )
        self.assertLessEqual(len(state._btc_history.observations), 17)
        self.assertEqual(BTC_PUBLISH_INTERVAL_SECONDS, .25)
        self.assertEqual(BTC_HISTORY_MAX_OBSERVATIONS, 14_401)

        with patch("quant.live_market.BTC_HISTORY_MAX_OBSERVATIONS", 4):
            bounded = LiveMarketState(clock=lambda: 20.0)
            for index in range(10):
                self.assertTrue(bounded.accept_g2_price(
                    asset="BTC", price=100.0 + index,
                    event_epoch=10.0 + index))
            self.assertEqual(len(bounded._btc_history.observations), 4)

    def test_wrong_subscription_and_missing_credentials_fail_closed(self):
        state = LiveMarketState(clock=lambda: 1.0)
        stop = threading.Event()
        class WrongSubscription:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":[]}]',
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: WrongSubscription())
        counters = dict(state.metrics.snapshot().counters)
        self.assertEqual(counters["btc_stream.subscription_invalid"], 1)
        self.assertIsNone(state.btc_latest_observation())

        missing = LiveMarketState()
        with patch.dict(os.environ, {}, clear=True):
            poll_alpaca_g2(
                missing, websocket_factory=lambda *_args, **_kwargs: None)
        telemetry = missing.metrics.snapshot()
        self.assertEqual(dict(telemetry.counters)[
            "btc_stream.configuration_failure"], 1)
        self.assertEqual(dict(telemetry.statuses)["btc_source_status"],
                         "UNAVAILABLE")

    def test_alpaca_timestamp_and_boolean_quote_validation_are_fail_closed(self):
        for invalid in (1, True, "1970-01-01T00:00:01"):
            with self.subTest(value=invalid), self.assertRaises(
                    (TypeError, ValueError)):
                parse_alpaca_timestamp(invalid)

        state = LiveMarketState(clock=lambda: 2.0)
        stop = threading.Event()
        class BooleanQuote:
            def __init__(self):
                self.messages = [
                    '[{"T":"success","msg":"authenticated"}]',
                    '[{"T":"subscription","quotes":["BTC/USD"]}]',
                    ('[{"T":"q","S":"BTC/USD","bp":true,"ap":2.0,'
                     '"t":"1970-01-01T00:00:01Z"}]'),
                ]
            def send(self, _value): pass
            def recv(self):
                value = self.messages.pop(0)
                if not self.messages: stop.set()
                return value
            def close(self): pass
        with patch.dict(os.environ, {
            "ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret",
        }, clear=False):
            poll_alpaca_g2(
                state, stop_event=stop,
                websocket_factory=lambda *_args, **_kwargs: BooleanQuote())
        self.assertEqual(dict(state.metrics.snapshot().counters)[
            "btc_stream.quote_rejected"], 1)

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

    def test_schwab_ndx_wrapper_preserves_read_only_quote_and_provider_time(self):
        price, event_epoch = parse_schwab_ndx_quote({
            "ok": True,
            "mode": "READ ONLY",
            "symbol": "$NDX",
            "data": {
                "$NDX": {
                    "symbol": "$NDX",
                    "quote": {
                        "lastPrice": 23_812.125,
                        "tradeTime": 100_000,
                        "mark": 23_813.0,
                        "quoteTime": 101_000,
                    },
                },
            },
        }, received_at_epoch=102.0)

        self.assertEqual(price, 23_812.125)
        self.assertEqual(event_epoch, 100.0)

        for payload in (
            {},
            {"ok": True, "mode": "WRITE", "symbol": "$NDX", "data": {}},
            {"ok": True, "mode": "READ ONLY", "symbol": "COIN", "data": {}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises((TypeError, ValueError)):
                    parse_schwab_ndx_quote(payload, received_at_epoch=102.0)

    def test_schwab_ndx_poller_uses_coin_service_and_accepts_only_fresh_data(self):
        state = LiveMarketState(clock=lambda: 101.0)
        response = BytesIO(json.dumps({
            "ok": True,
            "mode": "READ ONLY",
            "symbol": "$NDX",
            "data": {
                "$NDX": {
                    "symbol": "$NDX",
                    "quote": {
                        "lastPrice": 23_812.125,
                        "tradeTime": 100_000,
                        "quoteTime": 100_500,
                    },
                },
            },
        }).encode())

        with patch.dict(os.environ, {
            COIN_MARKET_USERNAME_ENV: "atom-reader",
            COIN_MARKET_PASSWORD_ENV: "secret",
        }), patch(
            "quant.live_market.urlopen", return_value=response,
        ) as urlopen, patch(
            "quant.live_market.time.time", return_value=101.0,
        ), patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_schwab_ndx(state)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, SCHWAB_NDX_QUOTE_URL)
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(
            request.get_header("Authorization"),
            "Basic YXRvbS1yZWFkZXI6c2VjcmV0",
        )
        self.assertEqual(state.cross_asset_state().ndx_price, 23_812.125)

    def test_schwab_ndx_poller_expires_stale_value_to_unavailable(self):
        state = LiveMarketState(clock=lambda: 101.0)
        self.assertTrue(state.accept_g2_price(
            asset="NDX", price=23_812.125, event_epoch=90.0,
        ))
        response = BytesIO(json.dumps({
            "ok": True,
            "mode": "READ ONLY",
            "symbol": "$NDX",
            "data": {
                "$NDX": {
                    "symbol": "$NDX",
                    "quote": {
                        "lastPrice": 23_812.125,
                        "tradeTime": 90_000,
                        "quoteTime": 90_000,
                    },
                },
            },
        }).encode())

        with patch.dict(os.environ, {
            COIN_MARKET_USERNAME_ENV: "atom-reader",
            COIN_MARKET_PASSWORD_ENV: "secret",
        }), patch(
            "quant.live_market.urlopen", return_value=response,
        ), patch(
            "quant.live_market.time.time", return_value=101.0,
        ), patch(
            "quant.live_market.time.sleep", side_effect=RuntimeError("stop"),
        ), patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                poll_schwab_ndx(state)

        value = state.cross_asset_state()
        self.assertIsNone(value.ndx_price)
        self.assertIsNone(value.ndx_age_seconds)
        self.assertEqual(value.ndx_return_bps, (None,) * 6)

    def test_schwab_ndx_defensive_no_op_paths(self):
        with self.assertRaises(TypeError):
            parse_schwab_ndx_quote([], received_at_epoch=102.0)

        state = LiveMarketState(clock=lambda: 101.0)
        self.assertFalse(state.expire_ndx_if_stale(now_epoch=True))
        self.assertFalse(state.expire_ndx_if_stale(now_epoch=101.0))
        self.assertTrue(state.accept_g2_price(
            asset="NDX", price=23_812.125, event_epoch=100.0,
        ))
        self.assertFalse(state.expire_ndx_if_stale(now_epoch=101.0))

    def test_stale_ndx_cannot_survive_a_blocked_request_or_coin_cycle(self):
        now = [101.0]
        entered_handler = threading.Event()
        release_handler = threading.Event()

        def handler(*_args):
            entered_handler.set()
            self.assertTrue(release_handler.wait(timeout=2))
            return None

        state = LiveMarketState(
            clock=lambda: now[0], v9_cycle_handler=handler,
        )
        self.assertTrue(state.accept_g2_price(
            asset="NDX", price=23_812.125, event_epoch=100.0,
        ))
        ingress = threading.Thread(target=lambda: state.accept_quote(
            bid=99.0, ask=101.0, event_epoch=101.0,
        ))
        ingress.start()
        self.assertTrue(entered_handler.wait(timeout=1))

        now[0] = 102.0
        self.assertTrue(state.accept_g2_price(
            asset="NDX", price=23_813.0, event_epoch=102.0,
        ))
        during = state.publication().cross_asset_state
        self.assertIsNone(during.coin_price)
        self.assertEqual(during.ndx_price, 23_813.0)
        self.assertEqual(during.as_of_epoch, 102.0)
        self.assertEqual(during.ndx_age_seconds, 0.0)

        with patch.dict(os.environ, {SCHWAB_NDX_ENABLED_ENV: "true"}):
            now[0] = 113.0
            self.assertIsNone(state.publication().cross_asset_state.ndx_price)
            release_handler.set()
            ingress.join(timeout=2)
            self.assertFalse(ingress.is_alive())
            self.assertIsNone(state.publication().cross_asset_state.ndx_price)

    def test_ndx_source_switch_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "quant.live_market.threading.Thread",
        ) as thread_type:
            start_massive_ndx_poller(LiveMarketState())
        self.assertIs(thread_type.call_args.kwargs["target"], poll_massive_ndx)

        with patch.dict(os.environ, {SCHWAB_NDX_ENABLED_ENV: "true"}), patch(
            "quant.live_market.threading.Thread",
        ) as thread_type:
            start_massive_ndx_poller(LiveMarketState())
        self.assertIs(thread_type.call_args.kwargs["target"], poll_schwab_ndx)

        for value in ("1", "yes", "on"):
            with self.subTest(value=value), patch.dict(
                os.environ, {SCHWAB_NDX_ENABLED_ENV: value}, clear=True,
            ), patch("quant.live_market.threading.Thread") as thread_type:
                start_massive_ndx_poller(LiveMarketState())
            self.assertIs(
                thread_type.call_args.kwargs["target"], poll_massive_ndx,
            )


if __name__ == "__main__":
    unittest.main()
