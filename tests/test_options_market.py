import json
import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from quant.live_market import LiveMarketState
from quant.options_market import (OPTIONS_POLL_INTERVAL, parse_alpaca_option_snapshot,
                                  poll_alpaca_options, select_coin_option_contract)
from quant.web import create_app, dashboard_data


CUTOFF = datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp()


def contract(symbol, expiration="2026-09-19", strike="200", kind="call", **changes):
    value = {"symbol": symbol, "underlying_symbol": "COIN", "expiration_date": expiration,
             "strike_price": strike, "type": kind, "status": "active"}
    value.update(changes)
    return value


def snapshot(**changes):
    value = {"latestQuote": {"bp": 9.25, "ap": 10.75, "t": "2026-08-20T14:30:01.123456Z"},
             "impliedVolatility": .44,
             "greeks": {"delta": .51, "gamma": .02, "theta": -.13, "vega": .28}}
    value.update(changes)
    return value


def request(app, path):
    status = {}
    body = b"".join(app({"PATH_INFO": path}, lambda value, headers: status.update(value=value)))
    return status["value"], json.loads(body) if path.endswith("dashboard") else body


class ParsingAndSelectionTests(unittest.TestCase):
    def test_exact_alpaca_response_fields_and_timestamp_are_preserved(self):
        item = parse_alpaca_option_snapshot(contract("COIN260919C00200000"), snapshot(), cutoff_epoch=CUTOFF)
        self.assertEqual((item.bid, item.ask, item.premium, item.spread), (9.25, 10.75, 10.0, 1.5))
        self.assertEqual((item.implied_volatility, item.delta, item.gamma, item.theta, item.vega),
                         (.44, .51, .02, -.13, .28))
        self.assertEqual(item.event_epoch, 1787236201.123456)

    def test_missing_values_remain_none_without_stock_substitution(self):
        item = parse_alpaca_option_snapshot(
            contract("COIN260919C00200000"), {"latestQuote": {"t": "2026-08-20T00:00:01Z"}},
            cutoff_epoch=CUTOFF)
        self.assertIsNone(item.bid); self.assertIsNone(item.ask)
        self.assertIsNone(item.premium); self.assertIsNone(item.spread)
        self.assertIsNone(item.implied_volatility); self.assertIsNone(item.delta)
        self.assertIsNone(item.gamma); self.assertIsNone(item.theta); self.assertIsNone(item.vega)

    def test_one_sided_or_crossed_quotes_do_not_derive_values(self):
        for quote in ({"bp": 1}, {"ap": 2}, {"bp": 3, "ap": 2}):
            with self.subTest(quote=quote):
                item = parse_alpaca_option_snapshot(contract("X"), {"latestQuote": quote}, cutoff_epoch=CUTOFF)
                self.assertIsNone(item.premium); self.assertIsNone(item.spread)

    def test_filters_coin_active_unexpired_and_prefers_calls(self):
        values = [contract("OTHER", underlying_symbol="QQQ"), contract("OLD", expiration="2026-08-19"),
                  contract("INACTIVE", status="inactive"), contract("PUT", kind="put"), contract("CALL")]
        self.assertEqual(select_coin_option_contract(values, midpoint=200, cutoff_epoch=CUTOFF)["symbol"], "CALL")

    def test_nearest_thirty_day_expiration_then_atm_and_ties(self):
        values = [contract("FAR", "2026-09-25", "200"), contract("HIGH", strike="205"),
                  contract("LOW-Z", strike="195"), contract("LOW-A", strike="195")]
        picks = [select_coin_option_contract(values, midpoint=200, cutoff_epoch=CUTOFF)["symbol"] for _ in range(10)]
        self.assertEqual(picks, ["LOW-A"] * 10)


class RuntimeTests(unittest.TestCase):
    def test_options_interval_is_exactly_ten_seconds(self):
        self.assertEqual(OPTIONS_POLL_INTERVAL, 10.0)

    def test_browser_requests_do_not_fetch_options(self):
        state = LiveMarketState()
        app = create_app(state=state)
        with patch("quant.options_market.fetch_coin_option_observation") as fetch:
            self.assertEqual(request(app, "/")[0], "200 OK")
            self.assertEqual(request(app, "/api/dashboard")[0], "200 OK")
            fetch.assert_not_called()

    def test_failed_poll_retains_option_and_independent_state_work_continues(self):
        state = LiveMarketState(clock=lambda: CUTOFF)
        state.accept_quote(bid=199, ask=201, event_epoch=CUTOFF - 1)
        original = parse_alpaca_option_snapshot(contract("KEEP"), snapshot(), cutoff_epoch=CUTOFF)
        state.accept_option_observation(original)
        stopped = threading.Event()
        def stop(_):
            stopped.set()
            raise RuntimeError("stop loop")
        with patch("quant.options_market.fetch_coin_option_observation", side_effect=OSError("transient")), \
             patch("quant.options_market.time.sleep", side_effect=stop):
            with self.assertRaises(RuntimeError):
                poll_alpaca_options(state)
        self.assertTrue(stopped.is_set())
        self.assertIs(state.snapshot().option_observation, original)
        self.assertTrue(state.accept_qqq_quote(bid=400, ask=402, event_epoch=CUTOFF))
        self.assertTrue(state.accept_quote(bid=200, ask=202, event_epoch=CUTOFF))
        self.assertIsNotNone(state.snapshot().momentum)
        self.assertIs(state.snapshot().option_observation, original)

    def test_dashboard_populates_truthfully_and_q10_stays_blank(self):
        state = LiveMarketState()
        item = parse_alpaca_option_snapshot(contract("DISPLAY"), snapshot(greeks={}), cutoff_epoch=CUTOFF)
        state.accept_option_observation(item)
        payload = dashboard_data(snapshot=state.snapshot())
        self.assertEqual(payload["options_data"]["Bid"], 9.25)
        self.assertEqual(payload["options_data"]["Expiration"], "2026-09-19")
        self.assertIsNone(payload["options_data"]["Delta"])
        self.assertEqual(payload["quant_families"][9]["values"], [None] * 6)


if __name__ == "__main__":
    unittest.main()
