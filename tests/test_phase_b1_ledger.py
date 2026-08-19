"""Phase B1 proofs for the exact-six ledger."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
from quant.models import HORIZONS, ExactSixBundle, HorizonForecast, SetupState


def bundle(cycle_id: str = "cycle-1") -> ExactSixBundle:
    return ExactSixBundle(
        cycle_id=cycle_id,
        symbol="COIN",
        cutoff_epoch=1_700_000_000.0,
        snapshot_hash=f"snapshot-{cycle_id}",
        policy_version="phase-b1",
        rows=[
            HorizonForecast(horizon=horizon, setup_state=SetupState.NO_SETUP)
            for horizon in HORIZONS
        ],
    )


class PhaseB1LedgerTests(unittest.TestCase):
    def test_empty_ledger(self) -> None:
        ledger = Ledger()

        self.assertEqual(ledger.count(), 0)
        self.assertIsNone(ledger.latest())

    def test_get_by_cycle_id_and_missing_get(self) -> None:
        ledger = Ledger()
        expected = ledger.commit(bundle())

        self.assertEqual(ledger.get("cycle-1"), expected)
        self.assertIsNone(ledger.get("missing"))

    def test_two_commits_preserve_order_and_latest(self) -> None:
        ledger = Ledger()
        first = ledger.commit(bundle("cycle-1"))
        second = ledger.commit(bundle("cycle-2"))

        self.assertEqual(ledger.count(), 2)
        self.assertEqual(ledger.get("cycle-1"), first)
        self.assertEqual(ledger.latest(), second)

    def test_duplicate_cycle_leaves_count_unchanged(self) -> None:
        ledger = Ledger()
        ledger.commit(bundle())

        with self.assertRaisesRegex(ValueError, "already committed"):
            ledger.commit(bundle())

        self.assertEqual(ledger.count(), 1)

    def test_mutated_wrong_row_count_is_rejected(self) -> None:
        ledger = Ledger()
        candidate = bundle()
        candidate.rows.pop()

        with self.assertRaisesRegex(ValueError, "exactly six"):
            ledger.commit(candidate)

        self.assertEqual(ledger.count(), 0)

    def test_mutated_wrong_horizon_order_is_rejected(self) -> None:
        ledger = Ledger()
        candidate = bundle()
        candidate.rows[0], candidate.rows[1] = candidate.rows[1], candidate.rows[0]

        with self.assertRaisesRegex(ValueError, "exact order"):
            ledger.commit(candidate)

        self.assertEqual(ledger.count(), 0)

    def test_original_bundle_mutation_cannot_alter_stored_evidence(self) -> None:
        ledger = Ledger()
        original = bundle()
        ledger.commit(original)
        original.rows[0].reason_codes.append("MUTATED")

        self.assertEqual(ledger.get("cycle-1").bundle.rows[0].reason_codes, [])

    def test_returned_records_cannot_alter_stored_evidence(self) -> None:
        ledger = Ledger()
        committed = ledger.commit(bundle())
        committed.bundle.rows[0].reason_codes.append("COMMIT_MUTATION")
        fetched = ledger.get("cycle-1")
        fetched.bundle.rows[0].reason_codes.append("GET_MUTATION")
        latest = ledger.latest()
        latest.bundle.rows[0].reason_codes.append("LATEST_MUTATION")

        self.assertEqual(ledger.get("cycle-1").bundle.rows[0].reason_codes, [])

    def test_forbidden_public_methods_are_absent(self) -> None:
        ledger = Ledger()

        for name in (
            "update",
            "delete",
            "resolve",
            "broker",
            "order",
            "account",
            "execute",
            "execution",
        ):
            self.assertFalse(hasattr(ledger, name), name)


if __name__ == "__main__":
    unittest.main()
