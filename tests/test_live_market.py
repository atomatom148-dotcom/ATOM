import json
from dataclasses import FrozenInstanceError
from io import BytesIO
import os
import unittest
from unittest.mock import MagicMock, patch

from quant.live_market import (
    ALPACA_BTC_LATEST_QUOTE_URL, ALPACA_LATEST_QUOTES_URL,
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
                poll_alpaca_g2(state)

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(
            urlopen.call_args.args[0].full_url, ALPACA_BTC_LATEST_QUOTE_URL,
        )
        value = state.cross_asset_state()
        self.assertEqual(value.btc_price, 101.0)
        self.assertIsNone(value.ndx_price)
        self.assertIsNone(value.ndx_age_seconds)
        self.assertEqual(value.ndx_return_bps, (None,) * 6)

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
