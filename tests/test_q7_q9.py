import math
import unittest

from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import ALPACA_LATEST_QUOTES_URL, LiveMarketState
from quant.q7_relative_value import (
    FORMULA_VERSION as Q7_FORMULA_VERSION,
    HORIZON_SECONDS as Q7_HORIZON_SECONDS,
    TAU_SECONDS,
    calculate_relative_value,
)
from quant.q8_cross_asset import calculate_cross_asset
from quant.q9_factor import calculate_factor
from quant.web import dashboard_data


def histories(count=31, *, spacing=30, q_offset=0, q_returns=None, coin_returns=None):
    q_returns = q_returns or [0.001 + 0.0001 * math.sin(i) for i in range(count - 1)]
    coin_returns = coin_returns or [0.0002 + 1.5 * value for value in q_returns]
    q_prices, coin_prices = [100.0], [200.0]
    for q_return, coin_return in zip(q_returns, coin_returns):
        q_prices.append(q_prices[-1] * math.exp(q_return))
        coin_prices.append(coin_prices[-1] * math.exp(coin_return))
    coin = MidpointHistory(
        MidpointObservation(float(i * spacing), price) for i, price in enumerate(coin_prices)
    )
    qqq = MidpointHistory(
        MidpointObservation(float(i * spacing + q_offset), price) for i, price in enumerate(q_prices)
    )
    return coin, qqq


class RelativeValueTests(unittest.TestCase):
    def test_positive_displacement_reverts_negative_and_excludes_current(self):
        q_returns = [0.001] * 19
        relative_returns = [0.002] * 18 + [0.006]
        coin_returns = [q + relative for q, relative in zip(q_returns, relative_returns)]
        coin, qqq = histories(20, q_returns=q_returns, coin_returns=coin_returns)
        original = coin.observations, qqq.observations
        result = calculate_relative_value(coin, qqq, cutoff_epoch=570)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.historical_relative_mean, 0.002)
        self.assertAlmostEqual(result.current_relative_return, 0.006)
        self.assertAlmostEqual(result.relative_displacement, 0.004)
        self.assertGreater(result.relative_displacement, 0)
        self.assertTrue(all(value < 0 for value in result.forecast_bps))
        self.assertEqual(TAU_SECONDS, 900)
        self.assertEqual(Q7_FORMULA_VERSION, "coin-qqq-relative-return-v2")
        self.assertEqual(Q7_HORIZON_SECONDS, (30, 60, 300, 900, 1800, 3600))
        self.assertEqual(len(result.forecast_bps), len(Q7_HORIZON_SECONDS))
        expected = -10_000 * (1 - math.exp(-30 / 900)) * result.relative_displacement
        self.assertAlmostEqual(result.forecast_bps[0], expected)
        self.assertEqual(original, (coin.observations, qqq.observations))

    def test_negative_displacement_reverts_positive(self):
        q_returns = [0.001] * 19
        relative_returns = [-0.002] * 18 + [-0.006]
        coin_returns = [q + relative for q, relative in zip(q_returns, relative_returns)]
        coin, qqq = histories(20, q_returns=q_returns, coin_returns=coin_returns)
        result = calculate_relative_value(coin, qqq, cutoff_epoch=570)
        self.assertLess(result.relative_displacement, 0)
        self.assertTrue(all(value > 0 for value in result.forecast_bps))

    def test_baseline_match_has_zero_displacement_and_forecasts(self):
        # Identical COIN and QQQ returns produce exact zero relative returns.
        returns = [0.001] * 19
        coin, qqq = histories(20, q_returns=returns, coin_returns=returns)
        result = calculate_relative_value(coin, qqq, cutoff_epoch=570)
        self.assertEqual(result.current_relative_return, result.historical_relative_mean)
        self.assertEqual(result.relative_displacement, 0)
        self.assertEqual(result.forecast_bps, (0.0,) * 6)

    def test_causal_stale_and_minimum_rules(self):
        coin, qqq = histories(20)
        baseline = calculate_relative_value(coin, qqq, cutoff_epoch=570)
        future = MidpointHistory(qqq.observations + (MidpointObservation(571, 999.0),))
        self.assertEqual(
            calculate_relative_value(coin, future, cutoff_epoch=570), baseline
        )
        coin, stale = histories(20, q_offset=-6)
        self.assertIsNone(calculate_relative_value(coin, stale, cutoff_epoch=570))
        coin, qqq = histories(19)
        self.assertIsNone(calculate_relative_value(coin, qqq, cutoff_epoch=540))
        self.assertIsNone(calculate_relative_value(coin, qqq, cutoff_epoch=float("nan")))


class CrossAssetTests(unittest.TestCase):
    def test_fixed_coefficients_sign_scaling_and_immutability(self):
        q_returns = [0.001 + i * 0.00001 for i in range(32)]
        # At 30-second spacing, y_t = 2*x_(t-30); both fixed lags remain estimable.
        coin_returns = [0.0] + [2 * value for value in q_returns[:-1]]
        coin, qqq = histories(33, q_returns=q_returns, coin_returns=coin_returns)
        original = coin.observations, qqq.observations
        result = calculate_cross_asset(coin, qqq, cutoff_epoch=960)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.beta_30, 2.0)
        self.assertTrue(math.isfinite(result.beta_60))
        self.assertGreater(result.forecast_bps[0], 0)
        self.assertAlmostEqual(result.forecast_bps[0] * 2, result.forecast_bps[1])
        self.assertTrue(all(value == result.forecast_bps[1] for value in result.forecast_bps[1:]))
        self.assertEqual(original, (coin.observations, qqq.observations))

    def test_negative_current_signal_and_failure_rules(self):
        q_returns = [0.001 + i * 0.00001 for i in range(31)] + [-0.001]
        coin_returns = [0.0] + [2 * value for value in q_returns[:-1]]
        coin, qqq = histories(33, q_returns=q_returns, coin_returns=coin_returns)
        self.assertLess(calculate_cross_asset(coin, qqq, cutoff_epoch=960).forecast_bps[0], 0)
        short_coin, short_qqq = histories(30)
        self.assertIsNone(calculate_cross_asset(short_coin, short_qqq, cutoff_epoch=870))
        flat = [0.0] * 32
        coin, qqq = histories(33, q_returns=flat, coin_returns=flat)
        self.assertIsNone(calculate_cross_asset(coin, qqq, cutoff_epoch=960))
        coin, future = histories(33, q_offset=0.1)
        self.assertIsNone(calculate_cross_asset(coin, future, cutoff_epoch=960))


class FactorTests(unittest.TestCase):
    def test_ols_coefficients_sign_scaling_and_immutability(self):
        coin, qqq = histories(31)
        original = coin.observations, qqq.observations
        result = calculate_factor(coin, qqq, cutoff_epoch=900)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.alpha, 0.0002)
        self.assertAlmostEqual(result.beta, 1.5)
        self.assertGreater(result.forecast_bps[0], 0)
        self.assertAlmostEqual(result.forecast_bps[0] * 2, result.forecast_bps[1])
        self.assertTrue(all(value == result.forecast_bps[1] for value in result.forecast_bps[1:]))
        self.assertEqual(original, (coin.observations, qqq.observations))

    def test_negative_stale_minimum_and_denominator_rules(self):
        q_returns = [0.001 + 0.0001 * math.sin(i) for i in range(29)] + [-0.01]
        coin_returns = [-0.0002 + value for value in q_returns]
        coin, qqq = histories(31, q_returns=q_returns, coin_returns=coin_returns)
        self.assertLess(calculate_factor(coin, qqq, cutoff_epoch=900).forecast_bps[0], 0)
        coin, stale = histories(31, q_offset=-6)
        self.assertIsNone(calculate_factor(coin, stale, cutoff_epoch=900))
        coin, qqq = histories(30)
        self.assertIsNone(calculate_factor(coin, qqq, cutoff_epoch=870))
        coin, qqq = histories(31, q_returns=[0.0] * 30, coin_returns=[0.001] * 30)
        self.assertIsNone(calculate_factor(coin, qqq, cutoff_epoch=900))


class Q7Q9LiveIntegrationTests(unittest.TestCase):
    def test_existing_histories_populate_three_existing_rows(self):
        state = LiveMarketState(clock=lambda: 9999.0)
        for i in range(61):
            event = float(i * 30)
            qqq = 100 * math.exp(0.001 * i + 0.00001 * i * i)
            coin = 200 * math.exp(0.0002 * i + 1.5 * (0.001 * i + 0.00001 * i * i))
            self.assertTrue(state.accept_qqq_quote(bid=qqq, ask=qqq, event_epoch=event))
            self.assertTrue(state.accept_quote(bid=coin, ask=coin, event_epoch=event))
        snapshot = state.snapshot()
        self.assertIsNotNone(snapshot.relative_value)
        self.assertIsNotNone(snapshot.cross_asset)
        self.assertIsNotNone(snapshot.factor)
        rows = dashboard_data(snapshot=snapshot)["quant_families"]
        self.assertTrue(all(value is not None for row in rows[6:9] for value in row["values"]))
        self.assertEqual(ALPACA_LATEST_QUOTES_URL.count("quotes/latest"), 1)


if __name__ == "__main__":
    unittest.main()
