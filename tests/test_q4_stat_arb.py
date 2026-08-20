import math
import unittest

from quant.history import MidpointHistory, MidpointObservation
from quant.q4_stat_arb import calculate_stat_arb


def histories(residuals, q_values=None, *, q_offset=0.0):
    q_values = q_values or [4.0 + index * 0.001 for index in range(len(residuals))]
    times = [float(index * 10) for index in range(len(residuals))]
    coin = MidpointHistory(MidpointObservation(t, math.exp(1.0 + 1.5*q + e)) for t, q, e in zip(times, q_values, residuals))
    qqq = MidpointHistory(MidpointObservation(t + q_offset, math.exp(q)) for t, q in zip(times, q_values))
    return coin, qqq


class StatArbTests(unittest.TestCase):
    def test_deterministic_ols_residual_ar_and_six_forecasts(self):
        residuals = [0.002 * math.sin(index) for index in range(20)]
        coin, qqq = histories(residuals)
        first = calculate_stat_arb(coin, qqq, cutoff_epoch=190)
        second = calculate_stat_arb(coin, qqq, cutoff_epoch=190)
        self.assertEqual(first, second)
        self.assertIsNotNone(first)
        self.assertEqual(len(first.forecast_bps), 6)
        self.assertAlmostEqual(first.median_spacing, 10.0)
        fitted = math.log(coin.observations[-1].midpoint) - first.alpha - first.beta * math.log(qqq.observations[-1].midpoint)
        self.assertAlmostEqual(first.current_residual, fitted)
        expected_phi = sum(a*b for a, b in zip(
            [math.log(c.midpoint)-first.alpha-first.beta*math.log(q.midpoint) for c,q in zip(coin.observations, qqq.observations)][:-1],
            [math.log(c.midpoint)-first.alpha-first.beta*math.log(q.midpoint) for c,q in zip(coin.observations, qqq.observations)][1:])) / sum(x*x for x in [math.log(c.midpoint)-first.alpha-first.beta*math.log(q.midpoint) for c,q in zip(coin.observations, qqq.observations)][:-1])
        self.assertAlmostEqual(first.phi, max(0.0, min(1.0, expected_phi)))

    def test_residual_reversion_signs(self):
        base = [0.001*(-0.8)**index for index in range(19)]
        for last, sign in ((0.01, -1), (-0.01, 1)):
            coin, qqq = histories(base + [last])
            result = calculate_stat_arb(coin, qqq, cutoff_epoch=190)
            self.assertIsNotNone(result)
            self.assertLess(result.phi, 1)
            self.assertEqual(math.copysign(1, result.forecast_bps[0]), sign)

    def test_minimum_future_stale_and_zero_denominator(self):
        coin, qqq = histories([0.001*math.sin(i) for i in range(19)])
        self.assertIsNone(calculate_stat_arb(coin, qqq, cutoff_epoch=180))
        coin, future = histories([0.001*math.sin(i) for i in range(20)], q_offset=0.1)
        self.assertIsNone(calculate_stat_arb(coin, future, cutoff_epoch=190))
        coin, stale = histories([0.001*math.sin(i) for i in range(20)], q_offset=-6.0)
        self.assertIsNone(calculate_stat_arb(coin, stale, cutoff_epoch=190))
        coin, flat = histories([0.001*math.sin(i) for i in range(20)], [4.0]*20)
        self.assertIsNone(calculate_stat_arb(coin, flat, cutoff_epoch=190))

    def test_invalid_ar_denominator_and_inputs_unchanged(self):
        observations = tuple(MidpointObservation(i * 10, 100.0 + i) for i in range(20))
        coin, qqq = MidpointHistory(observations), MidpointHistory(observations)
        original = (coin.observations, qqq.observations)
        self.assertIsNone(calculate_stat_arb(coin, qqq, cutoff_epoch=190))
        self.assertEqual(original, (coin.observations, qqq.observations))


if __name__ == '__main__':
    unittest.main()
