"""Phase B2 proofs for the minimal Unified Quant writer."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger, LedgerRecord
from quant.models import HORIZONS, SetupState
from quant.snapshot import from_price, missing_example, stale_example
import quant.unified_quant as unified_quant
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


class PhaseB2UnifiedQuantTests(unittest.TestCase):
    def test_usable_snapshot_writes_exact_six_honest_non_trades(self) -> None:
        snapshot = from_price("COIN", 150.0, asof_epoch=1_700_000_000.0)
        ledger = Ledger()
        record = write_cycle(
            snapshot,
            ledger,
            cycle_id="cycle-1",
            cutoff_epoch=CUTOFF,
            committed_at_epoch=CUTOFF,
        )
        bundle = record.bundle

        self.assertIsInstance(record, LedgerRecord)
        self.assertEqual(ledger.count(), 1)
        self.assertEqual(record, ledger.get("cycle-1"))
        self.assertEqual(tuple(row.horizon for row in bundle.rows), HORIZONS)
        self.assertEqual(bundle.cutoff_epoch, CUTOFF)
        self.assertEqual([row.cutoff_epoch for row in bundle.rows], [CUTOFF] * 6)
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
                record = write_cycle(
                    snapshot,
                    Ledger(),
                    cycle_id=expected_reason,
                    cutoff_epoch=CUTOFF,
                    committed_at_epoch=CUTOFF,
                )
                bundle = record.bundle
                for row in bundle.rows:
                    self.assertEqual(row.setup_state, SetupState.UNAVAILABLE)
                    self.assertEqual(row.reason_codes, [expected_reason])
                    self.assertIsNone(row.direction)
                    self.assertIsNone(row.probability)

    def test_unusable_snapshot_without_a_reason_gets_an_honest_reason(self) -> None:
        snapshot = from_price("COIN", None, asof_epoch=1_700_000_000.0)

        bundle = write_cycle(
            snapshot,
            Ledger(),
            cycle_id="cycle-1",
            cutoff_epoch=CUTOFF,
            committed_at_epoch=CUTOFF,
        ).bundle

        self.assertEqual(
            [row.reason_codes for row in bundle.rows],
            [["UNUSABLE_SNAPSHOT"]] * 6,
        )

    def test_hash_is_stable_and_changes_with_snapshot_evidence(self) -> None:
        first = from_price("COIN", 150.0, asof_epoch=1_700_000_000.0)
        same = from_price("COIN", 150.0, asof_epoch=1_700_000_000.0)
        changed = from_price("COIN", 151.0, asof_epoch=1_700_000_000.0)

        first_hash = write_cycle(
            first,
            Ledger(),
            cycle_id="first",
            cutoff_epoch=CUTOFF,
            committed_at_epoch=CUTOFF,
        ).bundle.snapshot_hash
        self.assertEqual(
            first_hash,
            write_cycle(
                same,
                Ledger(),
                cycle_id="same",
                cutoff_epoch=CUTOFF,
                committed_at_epoch=CUTOFF,
            ).bundle.snapshot_hash,
        )
        self.assertNotEqual(
            first_hash,
            write_cycle(
                changed,
                Ledger(),
                cycle_id="changed",
                cutoff_epoch=CUTOFF,
                committed_at_epoch=CUTOFF,
            ).bundle.snapshot_hash,
        )

    def test_duplicate_cycle_is_rejected_without_changing_ledger(self) -> None:
        ledger = Ledger()
        snapshot = from_price("COIN", 150.0)
        write_cycle(snapshot, ledger, cycle_id="cycle-1", cutoff_epoch=CUTOFF, committed_at_epoch=CUTOFF)

        with self.assertRaisesRegex(ValueError, "already committed"):
            write_cycle(snapshot, ledger, cycle_id="cycle-1", cutoff_epoch=CUTOFF, committed_at_epoch=CUTOFF)

        self.assertEqual(ledger.count(), 1)

    def test_forbidden_forecast_and_execution_surfaces_are_absent(self) -> None:
        for name in ("direction_brain", "broker", "order", "execute", "resolve"):
            self.assertFalse(hasattr(unified_quant, name), name)


if __name__ == "__main__":
    unittest.main()
