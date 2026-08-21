import json
import unittest

from quant.live_market import (
    ALPACA_NDX_LATEST_BAR_URL, LiveMarketState, parse_alpaca_ndx_bar,
    parse_alpaca_timestamp,
)
from quant.web import create_app


def request_json(app):
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app({"PATH_INFO": "/api/dashboard"}, start_response))
    return json.loads(body)


class LiveMarketTests(unittest.TestCase):
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
        after = request_json(app)
        self.assertEqual(after["market"]["symbol"], 101.0)
        self.assertEqual(after["market"]["data_age"], 2.0)
        self.assertEqual(after["market"]["last_cycle"], 1001.0)
        self.assertTrue(all(value is None for family in after["quant_families"][:3] for value in family["values"]))
        self.assertTrue(all(family["values"] == [None] * 6 for family in after["quant_families"][3:]))
        self.assertTrue(all(values == [None] * 6 for values in after["final_numbers"].values()))
        self.assertEqual(after["options_data"], {"expiration": None, "calls": [], "puts": []})

    def test_alpaca_event_timestamp_parser(self):
        self.assertEqual(parse_alpaca_timestamp("1970-01-01T00:00:01Z"), 1.0)

    def test_alpaca_ndx_latest_bar_contract_preserves_price_and_event_time(self):
        self.assertEqual(
            ALPACA_NDX_LATEST_BAR_URL,
            "https://data.alpaca.markets/v1beta1/indices/bars/latest?symbols=NDX",
        )
        price, event_epoch = parse_alpaca_ndx_bar({
            "bars": {
                "NDX": {
                    "c": 23_812.125,
                    "h": 23_815.0,
                    "l": 23_800.0,
                    "o": 23_805.0,
                    "t": "2026-08-21T14:30:05.123456Z",
                },
            },
        })
        self.assertEqual(price, 23_812.125)
        self.assertEqual(
            event_epoch,
            parse_alpaca_timestamp("2026-08-21T14:30:05.123456Z"),
        )

    def test_malformed_or_unavailable_alpaca_ndx_bar_is_rejected(self):
        malformed = (
            None,
            {},
            {"bars": {}},
            {"bars": {"NDX": None}},
            {"bars": {"NDX": {"t": "2026-08-21T14:30:05Z"}}},
            {"bars": {"NDX": {"c": "bad", "t": "2026-08-21T14:30:05Z"}}},
            {"bars": {"NDX": {"c": 23_812.125, "t": "bad"}}},
        )
        for payload in malformed:
            with self.subTest(payload=payload), self.assertRaises(
                (KeyError, TypeError, ValueError),
            ):
                parse_alpaca_ndx_bar(payload)


if __name__ == "__main__":
    unittest.main()
