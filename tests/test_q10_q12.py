import math
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import ALPACA_LATEST_QUOTES_URL, LiveMarketState
from quant.q10_options_vol import (FORMULA_VERSION, HORIZON_SECONDS, MAX_SIGNAL_BPS,
                                   OptionObservation, OptionSurface,
                                   calculate_options_vol)
from quant.q11_regime import HORIZON_SECONDS as Q11_HORIZONS, calculate_regime
from quant.q12_event_session import EASTERN, HORIZON_SECONDS as Q12_HORIZONS, calculate_event_session
from quant.web import dashboard_data


def option(**changes):
    values = dict(contract_symbol="COINTEST", event_epoch=100, strike=200,
                  expiration_epoch=200, expiration="1970-01-02", premium=10,
                  implied_volatility=.5, delta=.4, gamma=.01, theta=-.02,
                  vega=.1, bid=9, ask=11)
    values.update(changes)
    return OptionObservation(**values)


def history(prices, *, spacing=30, start=0):
    return MidpointHistory(
        MidpointObservation(float(start + index * spacing), price)
        for index, price in enumerate(prices)
    )


def et_epoch(hour, minute, second=0):
    return datetime(2026, 8, 20, hour, minute, second, tzinfo=EASTERN).timestamp()


class OptionsVolTests(unittest.TestCase):
    def surface(self, *, call_ivs=(.6, .8), put_ivs=(.4, .6),
                call_deltas=(.6, -.8), put_deltas=(-.2, .4), event_epoch=100):
        calls = tuple(option(contract_symbol=f"CALL{i}", strike=200 + i,
                             event_epoch=event_epoch, expiration_epoch=event_epoch + 100,
                             implied_volatility=iv, delta=delta)
                      for i, (iv, delta) in enumerate(zip(call_ivs, call_deltas)))
        puts = tuple(option(contract_symbol=f"PUT{i}", strike=200 + i,
                            event_epoch=event_epoch, expiration_epoch=event_epoch + 100,
                            implied_volatility=iv, delta=delta)
                     for i, (iv, delta) in enumerate(zip(put_ivs, put_deltas)))
        return OptionSurface(event_epoch, "1970-01-02", calls, puts)

    def test_contract_accepts_valid_numerical_input_and_is_immutable(self):
        observation = option()
        self.assertEqual(observation.strike, 200)
        with self.assertRaises(AttributeError):
            observation.strike = 201

    def test_contract_rejects_invalid_values(self):
        invalid = (
            {"strike": 0}, {"expiration_epoch": 100}, {"premium": -1},
            {"implied_volatility": -1}, {"bid": -1}, {"ask": -1},
            {"gamma": float("inf")},
            {"event_epoch": float("nan")},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                option(**changes)

    def test_no_dataset_or_stock_substitution_produces_forecast(self):
        self.assertIsNone(calculate_options_vol())
        payload = dashboard_data()
        self.assertEqual(payload["quant_families"][9]["values"], [None] * 6)
        self.assertEqual(payload["options_data"], {
            "status": "UNAVAILABLE", "as_of_epoch": None,
            "expiration": None, "calls": [], "puts": [],
        })

    def test_deterministic_means_asymmetries_and_equal_weighting(self):
        result = calculate_options_vol(self.surface(), cutoff_epoch=100)
        call_iv, put_iv = (.6 + .8) / 2, (.4 + .6) / 2
        call_delta, put_delta = (.6 + .8) / 2, (.2 + .4) / 2
        iv_asymmetry = (call_iv - put_iv) / (call_iv + put_iv)
        delta_asymmetry = (call_delta - put_delta) / (call_delta + put_delta)
        expected_hour = 25 * (.5 * iv_asymmetry + .5 * delta_asymmetry)
        self.assertEqual(result.formula_version, FORMULA_VERSION)
        self.assertEqual(result.source_as_of_epoch, 100)
        self.assertEqual(FORMULA_VERSION, "coin-options-skew-delta-v2")
        self.assertAlmostEqual(result.forecast_bps[-1], expected_hour)
        self.assertGreater(iv_asymmetry, 0)
        self.assertGreater(delta_asymmetry, 0)

    def test_component_signs_and_zero_signal(self):
        call_iv_high = calculate_options_vol(
            self.surface(call_ivs=(.8, .8), put_ivs=(.4, .4),
                         call_deltas=(.5, .5), put_deltas=(-.5, -.5)), cutoff_epoch=100)
        put_iv_high = calculate_options_vol(
            self.surface(call_ivs=(.4, .4), put_ivs=(.8, .8),
                         call_deltas=(.5, .5), put_deltas=(-.5, -.5)), cutoff_epoch=100)
        call_delta_high = calculate_options_vol(
            self.surface(call_ivs=(.5, .5), put_ivs=(.5, .5),
                         call_deltas=(.8, .8), put_deltas=(-.4, -.4)), cutoff_epoch=100)
        put_delta_high = calculate_options_vol(
            self.surface(call_ivs=(.5, .5), put_ivs=(.5, .5),
                         call_deltas=(.4, .4), put_deltas=(-.8, -.8)), cutoff_epoch=100)
        equal = calculate_options_vol(
            self.surface(call_ivs=(.5, .5), put_ivs=(.5, .5),
                         call_deltas=(.4, -.6), put_deltas=(-.4, .6)), cutoff_epoch=100)
        self.assertGreater(call_iv_high.forecast_bps[-1], 0)
        self.assertLess(put_iv_high.forecast_bps[-1], 0)
        self.assertGreater(call_delta_high.forecast_bps[-1], 0)
        self.assertLess(put_delta_high.forecast_bps[-1], 0)
        self.assertEqual(equal.forecast_bps, (0, 0, 0, 0, 0, 0))

    def test_exact_linear_horizons_constant_and_bound(self):
        result = calculate_options_vol(self.surface(), cutoff_epoch=100)
        self.assertEqual(HORIZON_SECONDS, (30, 60, 300, 900, 1800, 3600))
        self.assertEqual(MAX_SIGNAL_BPS, 25.0)
        self.assertEqual(len(result.forecast_bps), 6)
        hour = result.forecast_bps[-1]
        self.assertEqual(result.forecast_bps,
                         tuple(hour * scale for scale in (1 / 120, 1 / 60, 1 / 12, 1 / 4, 1 / 2, 1)))
        self.assertLessEqual(abs(hour), 25)

    def test_minimum_observations_missing_and_nonfinite_are_rejected(self):
        cases = (
            self.surface(call_ivs=(.5,), call_deltas=(.5,)),
            self.surface(put_ivs=(.5,), put_deltas=(.5,)),
            self.surface(call_deltas=(.5,), call_ivs=(.5,)),
            self.surface(put_deltas=(.5,), put_ivs=(.5,)),
            self.surface(call_ivs=(None, .5)),
            self.surface(put_ivs=(None, .5)),
            self.surface(call_deltas=(None, .5)),
            self.surface(put_deltas=(None, .5)),
        )
        for surface in cases:
            with self.subTest(surface=surface):
                self.assertIsNone(calculate_options_vol(surface, cutoff_epoch=100))

    def test_cutoff_freshness_boundaries_and_no_external_dependencies(self):
        surface = self.surface(event_epoch=100)
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP forbidden")):
            self.assertIsNotNone(calculate_options_vol(surface, cutoff_epoch=100))
            self.assertIsNotNone(calculate_options_vol(surface, cutoff_epoch=130))
            self.assertIsNone(calculate_options_vol(surface, cutoff_epoch=130.000001))
            self.assertIsNone(calculate_options_vol(surface, cutoff_epoch=99.999999))

    def test_every_surface_constituent_must_be_causal_and_surface_time_is_earliest(self):
        causal = self.surface(event_epoch=100)
        future_call = option(
            contract_symbol="CALL-FUTURE", event_epoch=101,
            expiration_epoch=200, strike=202, implied_volatility=.6, delta=.6,
        )
        mixed = OptionSurface(
            100, causal.expiration, causal.calls + (future_call,), causal.puts,
        )
        self.assertIsNone(calculate_options_vol(mixed, cutoff_epoch=100))
        with self.assertRaisesRegex(ValueError, "earliest provider timestamp"):
            OptionSurface(101, causal.expiration, mixed.calls, mixed.puts)

        stale_put = option(
            contract_symbol="PUT-STALE", event_epoch=69,
            expiration_epoch=200, strike=199, implied_volatility=.6, delta=-.6,
        )
        stale = OptionSurface(
            69, causal.expiration, causal.calls, (stale_put,) + causal.puts,
        )
        self.assertIsNone(calculate_options_vol(stale, cutoff_epoch=100))

    def test_live_cycle_populates_q10_row_from_surface_and_keeps_panel_contract(self):
        state = LiveMarketState(clock=lambda: 101)
        surface = self.surface(event_epoch=100)
        state.accept_option_surface(surface, midpoint=200)
        self.assertTrue(state.accept_quote(bid=199, ask=201, event_epoch=100))
        snapshot = state.snapshot()
        payload = dashboard_data(snapshot=snapshot)
        self.assertEqual(payload["quant_families"][9]["values"],
                         list(snapshot.options_vol.forecast_bps))
        self.assertEqual(payload["options_data"]["calls"][0]["Strike"], 200)
        self.assertEqual(payload["options_data"]["calls"][0]["Gamma"], .01)

    def test_dashboard_options_read_model_is_nearest_five_per_side(self):
        calls = tuple(option(contract_symbol=f"CALL-{strike}", strike=strike,
                             expiration="1970-01-02")
                      for strike in (190, 195, 199, 201, 205))
        puts = tuple(option(contract_symbol=f"PUT-{strike}", strike=strike,
                            expiration="1970-01-02")
                     for strike in (190, 195, 199, 201, 205))
        surface = OptionSurface(100, "1970-01-02", calls, puts)
        state = LiveMarketState(clock=lambda: 100)
        state.accept_option_surface(surface, midpoint=200)
        self.assertTrue(state.accept_quote(bid=199, ask=201, event_epoch=100))

        options = dashboard_data(snapshot=state.snapshot())["options_data"]

        self.assertEqual(options["expiration"], "1970-01-02")
        self.assertEqual([row["Strike"] for row in options["calls"]], [199, 201, 195, 205, 190])
        self.assertEqual([row["Strike"] for row in options["puts"]], [199, 201, 195, 205, 190])
        self.assertEqual(len(options["calls"]), 5)
        self.assertEqual(len(options["puts"]), 5)
        self.assertTrue(all(row["Symbol"].startswith("CALL-") for row in options["calls"]))
        self.assertTrue(all(row["Symbol"].startswith("PUT-") for row in options["puts"]))
        expected_fields = {"Symbol", "Strike", "Expiration", "Premium", "IV", "Delta",
                           "Gamma", "Theta", "Vega", "Bid", "Ask", "Spread"}
        self.assertTrue(all(set(row) == expected_fields
                            for row in options["calls"] + options["puts"]))

    def test_dashboard_options_partial_and_duplicate_strikes_are_honest(self):
        calls = (
            option(contract_symbol="CALL-A", strike=199, premium=None,
                   implied_volatility=None, delta=None, gamma=None, theta=None, vega=None,
                   bid=None, ask=None),
            option(contract_symbol="CALL-B", strike=199),
            option(contract_symbol="CALL-C", strike=205),
        )
        puts = (option(contract_symbol="PUT-A", strike=198),)
        state = LiveMarketState()
        state.accept_option_surface(OptionSurface(100, "1970-01-02", calls, puts), midpoint=200)
        self.assertTrue(state.accept_quote(bid=199, ask=201, event_epoch=100))

        options = dashboard_data(snapshot=state.snapshot())["options_data"]

        self.assertEqual([row["Symbol"] for row in options["calls"]], ["CALL-A", "CALL-C"])
        self.assertEqual([row["Symbol"] for row in options["puts"]], ["PUT-A"])
        for field in ("Premium", "IV", "Delta", "Gamma", "Theta", "Vega", "Bid", "Ask", "Spread"):
            self.assertIsNone(options["calls"][0][field])

    def test_live_cycle_leaves_q10_row_blank_for_stale_surface(self):
        state = LiveMarketState(clock=lambda: 131)
        state.accept_option_surface(self.surface(event_epoch=100), midpoint=200)
        self.assertTrue(state.accept_quote(bid=199, ask=201, event_epoch=131))
        self.assertIsNone(state.snapshot().options_vol)
        self.assertEqual(dashboard_data(snapshot=state.snapshot())["quant_families"][9]["values"],
                         [None] * 6)


class RegimeTests(unittest.TestCase):
    def test_equation_sigma_alignment_attenuation_scales_and_immutability(self):
        returns = [0.001] * 30
        prices = [100.0]
        for value in returns:
            prices.append(prices[-1] * math.exp(value))
        data = history(prices)
        original = data.observations
        result = calculate_regime(data, cutoff_epoch=900)
        self.assertAlmostEqual(result.short_return, .002)
        self.assertAlmostEqual(result.long_return, .030)
        self.assertAlmostEqual(result.sigma, .001)
        self.assertEqual(result.trend_alignment, 1)
        self.assertAlmostEqual(result.volatility_attenuation, 1 / 1.1)
        self.assertEqual(Q11_HORIZONS, (30, 60, 300, 900, 1800, 3600))
        full = 10_000 * result.regime_return
        self.assertAlmostEqual(result.forecast_bps[0], full * 30 / 900)
        self.assertAlmostEqual(result.forecast_bps[1], full * 60 / 900)
        self.assertAlmostEqual(result.forecast_bps[2], full * 300 / 900)
        self.assertEqual(result.forecast_bps[3:], (full, full, full))
        self.assertEqual(data.observations, original)

    def test_negative_and_zero_alignment(self):
        prices = [100 * math.exp(.001 * i) for i in range(29)] + [120, 101]
        self.assertEqual(calculate_regime(history(prices), cutoff_epoch=900).trend_alignment, -1)
        flat = history([100.0] * 31)
        self.assertEqual(calculate_regime(flat, cutoff_epoch=900).trend_alignment, 0)

    def test_insufficient_and_future_observations(self):
        self.assertIsNone(calculate_regime(history([100 + i for i in range(19)]), cutoff_epoch=540))
        base = history([100 + i for i in range(31)])
        expected = calculate_regime(base, cutoff_epoch=900)
        future = MidpointHistory(base.observations + (MidpointObservation(901, 999),))
        self.assertEqual(calculate_regime(future, cutoff_epoch=900), expected)


class EventSessionTests(unittest.TestCase):
    def session_history(self, cutoff, *, future=False):
        observations = [MidpointObservation(cutoff - 300, 100), MidpointObservation(cutoff, 101)]
        if future:
            observations.append(MidpointObservation(cutoff + 1, 999))
        return MidpointHistory(observations)

    def test_explicit_session_boundaries_and_multipliers(self):
        cases = ((9, 29, 59, None), (9, 30, 0, 1.0), (10, 29, 59, 1.0),
                 (10, 30, 0, .5), (14, 29, 59, .5), (14, 30, 0, .75),
                 (15, 59, 59, .75), (16, 0, 0, None))
        for hour, minute, second, multiplier in cases:
            cutoff = et_epoch(hour, minute, second)
            result = calculate_event_session(self.session_history(cutoff), cutoff_epoch=cutoff)
            if multiplier is None:
                self.assertIsNone(result)
            else:
                self.assertEqual(result.session_multiplier, multiplier)

    def test_exact_causal_return_horizons_timezone_and_immutability(self):
        cutoff = et_epoch(10, 30)
        data = self.session_history(cutoff)
        original = data.observations
        result = calculate_event_session(data, cutoff_epoch=cutoff)
        expected_return = math.log(101 / 100)
        self.assertAlmostEqual(result.five_minute_return, expected_return)
        self.assertEqual(Q12_HORIZONS, (30, 60, 300, 900, 1800, 3600))
        full = 10_000 * .5 * expected_return
        self.assertAlmostEqual(result.forecast_bps[0], full * .1)
        self.assertAlmostEqual(result.forecast_bps[1], full * .2)
        self.assertEqual(result.forecast_bps[2:], (full, full, full, full))
        self.assertEqual(EASTERN.key, "America/New_York")
        self.assertEqual(data.observations, original)
        self.assertEqual(calculate_event_session(self.session_history(cutoff, future=True), cutoff_epoch=cutoff), result)
        self.assertIsNone(calculate_event_session(history([100], start=int(cutoff)), cutoff_epoch=cutoff))


class FinalFamiliesIntegrationTests(unittest.TestCase):
    def test_live_rows_and_frozen_external_and_evidence_behavior(self):
        cutoff = et_epoch(11, 0)
        state = LiveMarketState()
        for index in range(31):
            event = cutoff - 900 + 30 * index
            self.assertTrue(state.accept_quote(bid=100 + index, ask=100 + index, event_epoch=event))
        snapshot = state.snapshot()
        rows = dashboard_data(snapshot=snapshot)["quant_families"]
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[9]["values"], [None] * 6)
        self.assertTrue(all(value is not None for value in rows[10]["values"]))
        self.assertTrue(all(value is not None for value in rows[11]["values"]))
        self.assertIsNone(snapshot.options_vol)
        self.assertEqual(ALPACA_LATEST_QUOTES_URL,
                         "https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=COIN%2CQQQ")


if __name__ == "__main__":
    unittest.main()
