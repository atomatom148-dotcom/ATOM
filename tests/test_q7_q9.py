import math
import unittest

from quant.history import MidpointHistory, MidpointObservation
from quant.live_market import ALPACA_LATEST_QUOTES_URL, LiveMarketState
from quant.q7_relative_value import TAU_SECONDS, calculate_relative_value
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
    def test_construction_constants_horizons_and_inputs_unchanged(self):
        coin, qqq = histories(20)
        original = coin.observations, qqq.observations
        result = calculate_relative_value(coin, qqq, cutoff_epoch=570)
        self.assertIsNotNone(result)
        relative = [
            math.log(c.midpoint / pc.midpoint) - math.log(q.midpoint / pq.midpoint)
            for (pc, pq), (c, q) in zip(
                zip(coin.observations, qqq.observations),
                zip(coin.observations[1:], qqq.observations[1:]),
            )
        ]
        mean = sum(relative) / len(relative)
        displacement = sum(value - mean for value in relative)
        self.assertAlmostEqual(result.relative_mean, mean)
        self.assertAlmostEqual(result.relative_displacement, displacement)
        self.assertEqual(TAU_SECONDS, 900)
        self.assertEqual(len(result.forecast_bps), 6)
        self.assertAlmostEqual(result.forecast_bps[0], -10_000 * (1 - math.exp(-30 / 900)) * displacement)
        self.assertEqual(original, (coin.observations, qqq.observations))

    def test_causal_stale_and_minimum_rules(self):
        coin, future = histories(20, q_offset=0.1)
        self.assertIsNone(calculate_relative_value(coin, future, cutoff_epoch=570))
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
