import json
import io
import threading
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from quant.live_market import LiveMarketState
from quant.options_market import (OPTIONS_POLL_INTERVAL, fetch_coin_option_surface,
                                  parse_alpaca_option_snapshot, poll_alpaca_options,
                                  select_coin_option_contract, select_coin_option_surface_contracts)
from quant.q10_options_vol import OptionSurface
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

    def test_surface_uses_one_nearest_future_expiration_and_filters_contracts(self):
        values = [contract("EXPIRED", "2026-08-20"), contract("WRONG", underlying_symbol="QQQ"),
                  contract("INACTIVE", status="inactive"), contract("BAD", strike="0")]
        for kind, marker in (("call", "C"), ("put", "P")):
            values.extend(contract(f"{marker}{strike:03}", "2026-09-19", str(strike), kind)
                          for strike in (180, 190, 195, 205, 210, 220))
            values.append(contract(f"{marker}FAR", "2026-09-25", "200", kind))
        expiration, calls, puts = select_coin_option_surface_contracts(
            values, midpoint=200, cutoff_epoch=CUTOFF)
        self.assertEqual(expiration.isoformat(), "2026-09-19")
        self.assertEqual([item["symbol"] for item in calls], ["C180", "C190", "C195", "C205", "C210"])
        self.assertEqual([item["symbol"] for item in puts], ["P180", "P190", "P195", "P205", "P210"])
        self.assertTrue(all(item["expiration_date"] == expiration.isoformat() for item in calls + puts))

    def test_surface_returns_only_available_real_contracts_with_lexical_ties(self):
        values = [contract("C-B", strike="195"), contract("C-A", strike="195"),
                  contract("P-ONE", strike="201", kind="put")]
        _, calls, puts = select_coin_option_surface_contracts(values, midpoint=200, cutoff_epoch=CUTOFF)
        self.assertEqual([item["symbol"] for item in calls], ["C-A", "C-B"])
        self.assertEqual([item["symbol"] for item in puts], ["P-ONE"])

    @patch.dict("os.environ", {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"})
    def test_bulk_snapshots_map_by_symbol_and_missing_snapshot_skips_one(self):
        contracts = [contract(f"C{x}", strike=str(x)) for x in range(198, 203)]
        contracts += [contract(f"P{x}", strike=str(x), kind="put") for x in range(198, 203)]
        snapshots = {item["symbol"]: snapshot() for item in contracts}
        snapshots.pop("C200")
        snapshots["P200"] = snapshot(impliedVolatility=None, greeks={"delta": None})
        pages = [{"option_contracts": contracts}, {"snapshots": snapshots}]

        class Response:
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *args): return None
        with patch("quant.options_market.urlopen", side_effect=[Response(page) for page in pages]) as get:
            with patch("quant.options_market.json.load", side_effect=lambda response: response.value):
                surface = fetch_coin_option_surface(midpoint=200, cutoff_epoch=CUTOFF)
        self.assertEqual(get.call_count, 2)  # one discovery page plus one bulk snapshot request
        snapshot_url = get.call_args_list[1].args[0].full_url
        self.assertEqual(urlparse(snapshot_url).path, "/v1beta1/options/snapshots/COIN")
        self.assertEqual(parse_qs(urlparse(snapshot_url).query), {"limit": ["1000"]})
        self.assertNotIn("symbols", snapshot_url)
        self.assertEqual(len(surface.calls), 4)
        self.assertEqual(len(surface.puts), 5)
        self.assertNotIn("C200", [item.contract_symbol for item in surface.calls])
        put = next(item for item in surface.puts if item.contract_symbol == "P200")
        self.assertIsNone(put.implied_volatility)
        self.assertIsNone(put.delta)
        self.assertEqual((put.bid, put.ask, put.premium, put.spread), (9.25, 10.75, 10.0, 1.5))


class RuntimeTests(unittest.TestCase):
    def test_options_interval_is_exactly_ten_seconds(self):
        self.assertEqual(OPTIONS_POLL_INTERVAL, 10.0)

    def test_browser_requests_do_not_fetch_options(self):
        state = LiveMarketState()
        app = create_app(state=state)
        with patch("quant.options_market.fetch_coin_option_surface") as fetch:
            self.assertEqual(request(app, "/")[0], "200 OK")
            self.assertEqual(request(app, "/api/dashboard")[0], "200 OK")
            fetch.assert_not_called()

    def test_failed_poll_retains_option_and_independent_state_work_continues(self):
        state = LiveMarketState(clock=lambda: CUTOFF)
        state.accept_quote(bid=199, ask=201, event_epoch=CUTOFF - 1)
        original = parse_alpaca_option_snapshot(contract("KEEP"), snapshot(), cutoff_epoch=CUTOFF)
        put = parse_alpaca_option_snapshot(contract("KEEP-P", kind="put"), snapshot(), cutoff_epoch=CUTOFF)
        original_surface = OptionSurface(CUTOFF, "2026-09-19", (original,), (put,))
        state.accept_option_surface(original_surface, midpoint=200)
        stopped = threading.Event()
        def stop(_):
            stopped.set()
            raise RuntimeError("stop loop")
        with patch("quant.options_market.fetch_coin_option_surface", side_effect=OSError("transient")), \
             patch("quant.options_market.time.sleep", side_effect=stop):
            with self.assertRaises(RuntimeError):
                poll_alpaca_options(state)
        self.assertTrue(stopped.is_set())
        self.assertIs(state.snapshot().option_observation, original)
        self.assertIs(state.snapshot().option_surface, original_surface)
        self.assertTrue(state.accept_qqq_quote(bid=400, ask=402, event_epoch=CUTOFF))
        self.assertTrue(state.accept_quote(bid=200, ask=202, event_epoch=CUTOFF))
        self.assertIsNotNone(state.snapshot().momentum)
        self.assertIs(state.snapshot().option_observation, original)
        self.assertIs(state.snapshot().option_surface, original_surface)

    @patch.dict("os.environ", {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"})
    def test_http_error_diagnostic_has_status_and_body_but_no_credentials(self):
        state = LiveMarketState(clock=lambda: CUTOFF)
        state.accept_quote(bid=199, ask=201, event_epoch=CUTOFF - 1)
        original = parse_alpaca_option_snapshot(contract("KEEP"), snapshot(), cutoff_epoch=CUTOFF)
        original_surface = OptionSurface(CUTOFF, "2026-09-19", (original,), ())
        state.accept_option_surface(original_surface, midpoint=200)
        error = HTTPError("https://key:secret@example.test", 400, "Bad Request",
                          {"Authorization": "key secret"},
                          io.BytesIO(b'{"message":"unsupported symbols; key secret"}'))
        output = io.StringIO()
        with patch("quant.options_market.fetch_coin_option_surface", side_effect=error), \
             patch("quant.options_market.time.sleep", side_effect=RuntimeError("stop")), \
             redirect_stdout(output):
            with self.assertRaises(RuntimeError):
                poll_alpaca_options(state)
        diagnostic = output.getvalue()
        self.assertIn('HTTP 400: {"message":"unsupported symbols; [REDACTED] [REDACTED]"}', diagnostic)
        self.assertNotIn("key", diagnostic)
        self.assertNotIn("secret", diagnostic)
        self.assertNotIn("Authorization", diagnostic)
        self.assertIs(state.snapshot().option_observation, original)
        self.assertIs(state.snapshot().option_surface, original_surface)

    def test_surface_and_representative_are_published_in_one_snapshot(self):
        state = LiveMarketState()
        high = parse_alpaca_option_snapshot(contract("HIGH", strike="205"), snapshot(), cutoff_epoch=CUTOFF)
        low_z = parse_alpaca_option_snapshot(contract("LOW-Z", strike="195"), snapshot(), cutoff_epoch=CUTOFF)
        low_a = parse_alpaca_option_snapshot(contract("LOW-A", strike="195"), snapshot(), cutoff_epoch=CUTOFF)
        put = parse_alpaca_option_snapshot(contract("PUT", strike="200", kind="put"), snapshot(), cutoff_epoch=CUTOFF)
        surface = OptionSurface(CUTOFF, "2026-09-19", (low_a, low_z, high), (put,))
        state.accept_option_surface(surface, midpoint=200)
        published = state.snapshot()
        self.assertIs(published.option_surface, surface)
        self.assertIs(published.option_observation, low_a)

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
