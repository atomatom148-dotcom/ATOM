from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.history import MidpointHistory, MidpointObservation
from quant.models import HORIZONS
from quant.q3_volatility import calculate_volatility


class VolatilityTests(unittest.TestCase):
    def test_deterministic_realized_volatility_and_six_horizons(self) -> None:
        observations = (
            MidpointObservation(0, 100),
            MidpointObservation(30, 110),
            MidpointObservation(60, 99),
        )
        history = MidpointHistory(observations)
        result = calculate_volatility(history, cutoff_epoch=60)
        expected = 10_000 * math.sqrt(math.log(1.1) ** 2 + math.log(0.9) ** 2)

        self.assertEqual(len(result.volatility_bps), len(HORIZONS))
        self.assertTrue(all(value == result.volatility_bps[0] for value in result.volatility_bps))
        self.assertAlmostEqual(result.volatility_bps[0], expected)
        self.assertGreaterEqual(result.volatility_bps[0], 0)
        self.assertFalse(hasattr(result, "forecast_bps"))
        self.assertEqual(history.observations, observations)

    def test_zero_returns_have_zero_volatility(self) -> None:
        history = MidpointHistory(
            [MidpointObservation(0, 100), MidpointObservation(30, 100)]
        )
        self.assertEqual(
            calculate_volatility(history, cutoff_epoch=30).volatility_bps,
            (0.0,) * 6,
        )

    def test_insufficient_history_is_none(self) -> None:
        result = calculate_volatility(
            MidpointHistory([MidpointObservation(0, 100)]), cutoff_epoch=0
        )
        self.assertEqual(result.volatility_bps, (None,) * 6)

    def test_future_is_invisible(self) -> None:
        visible = (
            MidpointObservation(0, 100),
            MidpointObservation(30, 101),
        )
        with_future = MidpointHistory(
            visible + (MidpointObservation(31, 1000),)
        )
        self.assertEqual(
            calculate_volatility(with_future, cutoff_epoch=30),
            calculate_volatility(MidpointHistory(visible), cutoff_epoch=30),
        )


if __name__ == "__main__":
    unittest.main()
