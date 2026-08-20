"""Contract proofs for immutable historical numerical midpoint input."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.history import MidpointHistory, MidpointObservation


class MidpointHistoryTests(unittest.TestCase):
    def test_valid_chronological_observations_are_accepted(self) -> None:
        observations = [MidpointObservation(10.0, 100.0), MidpointObservation(20.0, 101.0)]
        history = MidpointHistory(observations)

        self.assertEqual(history.count, 2)
        self.assertEqual(history.latest, observations[-1])
        self.assertEqual(history.observations, tuple(observations))

    def test_nonfinite_timestamps_are_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "event_epoch"):
                MidpointObservation(value, 100.0)

    def test_nonfinite_zero_and_negative_midpoints_are_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf, 0.0, -1.0):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "midpoint"):
                MidpointObservation(10.0, value)

    def test_duplicate_timestamps_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly chronological"):
            MidpointHistory([MidpointObservation(10.0, 100.0), MidpointObservation(10.0, 101.0)])

    def test_out_of_order_observations_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly chronological"):
            MidpointHistory([MidpointObservation(20.0, 101.0), MidpointObservation(10.0, 100.0)])

    def test_cutoff_cannot_expose_future_observations(self) -> None:
        history = MidpointHistory(
            [MidpointObservation(10.0, 100.0), MidpointObservation(20.0, 101.0)]
        )

        self.assertEqual(history.within(cutoff=15.0, lookback=100.0), history.observations[:1])

    def test_lookback_returns_only_mathematically_eligible_observations(self) -> None:
        history = MidpointHistory(
            [
                MidpointObservation(10.0, 100.0),
                MidpointObservation(15.0, 101.0),
                MidpointObservation(20.0, 102.0),
            ]
        )

        self.assertEqual(history.within(cutoff=20.0, lookback=5.0), history.observations[1:])

    def test_missing_intervals_remain_missing_without_fill_or_interpolation(self) -> None:
        history = MidpointHistory(
            [MidpointObservation(10.0, 100.0), MidpointObservation(30.0, 110.0)]
        )

        self.assertEqual(history.within(cutoff=25.0, lookback=10.0), ())
        self.assertEqual(history.count, 2)

    def test_supplied_input_is_not_mutated_or_retained(self) -> None:
        supplied = [MidpointObservation(10.0, 100.0)]
        history = MidpointHistory(supplied)
        supplied.append(MidpointObservation(20.0, 101.0))

        self.assertEqual(history.count, 1)
        self.assertIsInstance(history.observations, tuple)


if __name__ == "__main__":
    unittest.main()
