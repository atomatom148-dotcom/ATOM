from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.history import MidpointHistory, MidpointObservation
from quant.models import HORIZONS
from quant.q1_momentum import calculate_momentum


class MomentumTests(unittest.TestCase):
    def test_quant_modules_have_no_commit_owner_dependencies(self) -> None:
        quant_directory = Path(__file__).resolve().parents[1] / "quant"
        for name in ("q1_momentum.py", "q2_mean_reversion.py", "q3_volatility.py"):
            source = (quant_directory / name).read_text(encoding="utf-8").lower()
            with self.subTest(module=name):
                self.assertNotIn("ledger", source)
                self.assertNotIn("resolver", source)
                self.assertNotIn("commit", source)

    def test_known_prices_and_all_signs(self) -> None:
        history = MidpointHistory(
            [
                MidpointObservation(0, 100),
                MidpointObservation(1800, 110),
                MidpointObservation(3300, 100),
                MidpointObservation(3540, 120),
                MidpointObservation(3570, 100),
                MidpointObservation(3600, 110),
            ]
        )
        result = calculate_momentum(history, cutoff_epoch=3600)

        self.assertEqual(len(result.forecast_bps), len(HORIZONS))
        self.assertAlmostEqual(result.forecast_bps[0], 10_000 * math.log(1.1))
        self.assertGreater(result.forecast_bps[0], 0)
        self.assertLess(result.forecast_bps[1], 0)
        self.assertGreater(result.forecast_bps[2], 0)
        self.assertEqual(result.forecast_bps[3], 0.0)
        self.assertEqual(result.forecast_bps[4], 0.0)

    def test_insufficient_history_is_none(self) -> None:
        result = calculate_momentum(
            MidpointHistory([MidpointObservation(100, 10)]), cutoff_epoch=100
        )
        self.assertEqual(result.forecast_bps, (None,) * 6)

    def test_future_is_invisible_and_missing_intervals_are_not_interpolated(self) -> None:
        observations = (
            MidpointObservation(0, 100),
            MidpointObservation(69, 105),
            MidpointObservation(100, 110),
            MidpointObservation(101, 999),
        )
        history = MidpointHistory(observations)
        result = calculate_momentum(history, cutoff_epoch=100)

        self.assertAlmostEqual(result.forecast_bps[0], 10_000 * math.log(110 / 105))
        self.assertAlmostEqual(result.forecast_bps[1], 10_000 * math.log(110 / 100))
        self.assertIsNone(result.forecast_bps[2])
        self.assertEqual(history.observations, observations)

    def test_zero_momentum(self) -> None:
        history = MidpointHistory(
            [MidpointObservation(0, 100), MidpointObservation(3600, 100)]
        )
        self.assertEqual(
            calculate_momentum(history, cutoff_epoch=3600).forecast_bps,
            (0.0,) * 6,
        )


if __name__ == "__main__":
    unittest.main()
