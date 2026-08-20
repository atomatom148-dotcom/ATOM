from __future__ import annotations

import math
from pathlib import Path
import statistics
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.history import MidpointHistory, MidpointObservation
from quant.models import HORIZONS
from quant.q2_mean_reversion import calculate_mean_reversion


class MeanReversionTests(unittest.TestCase):
    @staticmethod
    def _expected(prices: tuple[float, ...], horizon: float) -> float:
        logs = tuple(map(math.log, prices))
        mean = statistics.fmean(logs)
        centered = tuple(value - mean for value in logs)
        phi = sum(a * b for a, b in zip(centered, centered[1:])) / sum(
            value * value for value in centered[:-1]
        )
        phi = min(max(phi, 0), 1)
        return 10_000 * (phi ** (horizon / 30) - 1) * centered[-1]

    def test_deterministic_known_sequence_and_six_horizons(self) -> None:
        prices = (100.0, 101.0, 102.0, 103.0)
        history = MidpointHistory(
            MidpointObservation(index * 30, price)
            for index, price in enumerate(prices)
        )
        result = calculate_mean_reversion(history, cutoff_epoch=90)

        self.assertEqual(len(result.forecast_bps), len(HORIZONS))
        self.assertAlmostEqual(result.forecast_bps[0], self._expected(prices, 30))
        self.assertEqual(result, calculate_mean_reversion(history, cutoff_epoch=90))
        self.assertLess(result.forecast_bps[0], 0)

    def test_below_mean_produces_positive_forecast(self) -> None:
        history = MidpointHistory(
            [
                MidpointObservation(0, 103),
                MidpointObservation(30, 102),
                MidpointObservation(60, 101),
                MidpointObservation(90, 100),
            ]
        )
        self.assertGreater(
            calculate_mean_reversion(history, cutoff_epoch=90).forecast_bps[0], 0
        )

    def test_insufficient_and_invalid_denominator(self) -> None:
        one = MidpointHistory([MidpointObservation(0, 100)])
        flat = MidpointHistory(
            [MidpointObservation(0, 100), MidpointObservation(30, 100)]
        )
        self.assertEqual(
            calculate_mean_reversion(one, cutoff_epoch=0).forecast_bps,
            (None,) * 6,
        )
        self.assertEqual(
            calculate_mean_reversion(flat, cutoff_epoch=30).forecast_bps,
            (None,) * 6,
        )

    def test_future_is_invisible_and_input_unchanged(self) -> None:
        observations = (
            MidpointObservation(0, 100),
            MidpointObservation(30, 101),
            MidpointObservation(60, 102),
            MidpointObservation(61, 500),
        )
        history = MidpointHistory(observations)
        result = calculate_mean_reversion(history, cutoff_epoch=60)
        baseline = calculate_mean_reversion(
            MidpointHistory(observations[:-1]), cutoff_epoch=60
        )
        self.assertEqual(result, baseline)
        self.assertEqual(history.observations, observations)


if __name__ == "__main__":
    unittest.main()
