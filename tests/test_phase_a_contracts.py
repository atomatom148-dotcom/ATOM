"""Phase A contract proofs for the deliberately thin quant package."""

from __future__ import annotations

import unittest

from quant.models import (
    HORIZONS,
    ExactSixBundle,
    HorizonForecast,
    SetupState,
)
from quant.snapshot import missing_example


def forecast(horizon: str) -> HorizonForecast:
    return HorizonForecast(horizon=horizon, setup_state=SetupState.NO_SETUP)


def bundle(rows: list[HorizonForecast]) -> ExactSixBundle:
    return ExactSixBundle(
        cycle_id="phase-a-proof",
        symbol="COIN",
        cutoff_epoch=1_700_000_000.0,
        snapshot_hash="snapshot-proof",
        policy_version="phase-a",
        rows=rows,
    )


class PhaseAContractTests(unittest.TestCase):
    def test_horizons_are_exact_and_ordered(self) -> None:
        self.assertEqual(HORIZONS, ("30S", "1M", "5M", "15M", "30M", "1H"))

    def test_setup_states_are_short_and_complete(self) -> None:
        self.assertEqual(
            {state.value for state in SetupState},
            {"QUALIFIED", "BLOCKED", "UNAVAILABLE", "NO_SETUP"},
        )

    def test_exact_six_bundle_accepts_the_contract(self) -> None:
        rows = [forecast(horizon) for horizon in HORIZONS]

        self.assertEqual(bundle(rows).rows, rows)

    def test_exact_six_bundle_rejects_the_wrong_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 6 rows"):
            bundle([forecast(horizon) for horizon in HORIZONS[:-1]])

    def test_exact_six_bundle_rejects_the_wrong_order(self) -> None:
        reordered = (HORIZONS[1], HORIZONS[0], *HORIZONS[2:])

        with self.assertRaisesRegex(ValueError, "horizons must be"):
            bundle([forecast(horizon) for horizon in reordered])

    def test_missing_market_evidence_stays_missing(self) -> None:
        snapshot = missing_example()

        self.assertIsNone(snapshot.last)
        self.assertIsNone(snapshot.bar_close)
        self.assertFalse(snapshot.is_usable())
        self.assertEqual(snapshot.reason_codes, ["MISSING_LAST"])

    def test_non_trade_forecast_does_not_invent_a_probability(self) -> None:
        row = forecast("30S").to_dict()

        self.assertIsNone(row["direction"])
        self.assertIsNone(row["probability"])


if __name__ == "__main__":
    unittest.main()
