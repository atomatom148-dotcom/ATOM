import math
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import ALPACA_LATEST_QUOTES_URL, LiveMarketState
from quant.q10_options_vol import OptionObservation, calculate_options_vol
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
        self.assertIsNone(calculate_options_vol((option(),)))
        payload = dashboard_data()
        self.assertEqual(payload["quant_families"][9]["values"], [None] * 6)
        self.assertTrue(all(value is None for value in payload["options_data"].values()))


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
