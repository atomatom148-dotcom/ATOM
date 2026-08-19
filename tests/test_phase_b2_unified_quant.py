"""Phase B2 proofs for the minimal Unified Quant writer."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.models import HORIZONS, SetupState
from quant.snapshot import from_price, missing_example, stale_example
from quant.unified_quant import UnifiedQuant


class PhaseB2UnifiedQuantTests(unittest.TestCase):
    def test_usable_snapshot_writes_exact_six_honest_non_trades(self) -> None:
        snapshot = from_price("COIN", 150.0, asof_epoch=1_700_000_000.0)
        bundle = UnifiedQuant().write(snapshot, cycle_id="cycle-1")

        self.assertEqual(tuple(row.horizon for row in bundle.rows), HORIZONS)
        self.assertEqual(bundle.cutoff_epoch, snapshot.asof_epoch)
        self.assertEqual(
            [row.maturity_epoch - row.cutoff_epoch for row in bundle.rows],
            [30, 60, 300, 900, 1800, 3600],
        )
        for row in bundle.rows:
            self.assertEqual(row.setup_state, SetupState.NO_SETUP)
            self.assertIsNone(row.direction)
            self.assertIsNone(row.probability)
            self.assertEqual(row.reason_codes, [])

    def test_unusable_snapshots_write_unavailable_without_invention(self) -> None:
        for snapshot, expected_reason in (
            (missing_example(), "MISSING_LAST"),
            (stale_example(), "STALE_CORE"),
        ):
            with self.subTest(reason=expected_reason):
                bundle = UnifiedQuant().write(snapshot, cycle_id=expected_reason)
                for row in bundle.rows:
                    self.assertEqual(row.setup_state, SetupState.UNAVAILABLE)
                    self.assertEqual(row.reason_codes, [expected_reason])
                    self.assertIsNone(row.direction)
                    self.assertIsNone(row.probability)

    def test_unusable_snapshot_without_a_reason_gets_an_honest_reason(self) -> None:
        snapshot = from_price("COIN", None, asof_epoch=1_700_000_000.0)

        bundle = UnifiedQuant().write(snapshot, cycle_id="cycle-1")

        self.assertEqual(
            [row.reason_codes for row in bundle.rows],
            [["UNUSABLE_SNAPSHOT"]] * 6,
        )

    def test_hash_is_stable_and_changes_with_snapshot_evidence(self) -> None:
        writer = UnifiedQuant()
        first = from_price("COIN", 150.0, asof_epoch=1_700_000_000.0)
        same = from_price("COIN", 150.0, asof_epoch=1_700_000_000.0)
        changed = from_price("COIN", 151.0, asof_epoch=1_700_000_000.0)

        first_hash = writer.write(first, cycle_id="first").snapshot_hash
        self.assertEqual(
            first_hash, writer.write(same, cycle_id="same").snapshot_hash
        )
        self.assertNotEqual(
            first_hash, writer.write(changed, cycle_id="changed").snapshot_hash
        )

    def test_forbidden_forecast_and_execution_surfaces_are_absent(self) -> None:
        writer = UnifiedQuant()

        for name in ("direction_brain", "broker", "order", "execute", "resolve"):
            self.assertFalse(hasattr(writer, name), name)


if __name__ == "__main__":
    unittest.main()
