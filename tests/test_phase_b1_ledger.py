"""Phase B1 proofs for the process-local exact-six ledger."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import ExactSixLedger, LedgerCommitError
from quant.models import HORIZONS, ExactSixBundle, HorizonForecast, SetupState


CUTOFF = 1_700_000_000.0


def bundle(cycle_id: str = "cycle-1") -> ExactSixBundle:
    rows = [
        HorizonForecast(
            horizon=horizon,
            setup_state=SetupState.NO_SETUP,
            cutoff_epoch=CUTOFF,
            maturity_epoch=CUTOFF + offset,
        )
        for horizon, offset in zip(HORIZONS, (30, 60, 300, 900, 1800, 3600))
    ]
    return ExactSixBundle(
        cycle_id=cycle_id,
        symbol="COIN",
        cutoff_epoch=CUTOFF,
        snapshot_hash="snapshot-proof",
        policy_version="phase-b1",
        rows=rows,
    )


class PhaseB1LedgerTests(unittest.TestCase):
    def test_commits_one_exact_six_bundle_atomically(self) -> None:
        ledger = ExactSixLedger()
        receipt = ledger.commit(bundle(), committed_at_epoch=CUTOFF + 1)

        self.assertEqual(len(ledger), 1)
        self.assertEqual(receipt.cycle_id, "cycle-1")
        self.assertEqual(tuple(row.horizon for row in receipt.bundle.rows), HORIZONS)

    def test_rejects_a_commit_at_or_after_maturity_without_partial_write(self) -> None:
        ledger = ExactSixLedger()

        with self.assertRaisesRegex(LedgerCommitError, "before horizon maturity"):
            ledger.commit(bundle(), committed_at_epoch=CUTOFF + 30)

        self.assertEqual(len(ledger), 0)

    def test_committed_cycle_cannot_be_overwritten(self) -> None:
        ledger = ExactSixLedger()
        ledger.commit(bundle(), committed_at_epoch=CUTOFF + 1)

        with self.assertRaisesRegex(LedgerCommitError, "already committed"):
            ledger.commit(bundle(), committed_at_epoch=CUTOFF + 2)

        self.assertEqual(len(ledger), 1)

    def test_committed_history_is_isolated_from_caller_mutation(self) -> None:
        ledger = ExactSixLedger()
        source = bundle()
        ledger.commit(source, committed_at_epoch=CUTOFF + 1)
        source.rows[0].reason_codes.append("REWRITTEN")

        read = ledger.get(source.cycle_id)
        self.assertEqual(read.bundle.rows[0].reason_codes, [])

        read.bundle.rows[0].reason_codes.append("ALSO_REWRITTEN")
        self.assertEqual(ledger.get(source.cycle_id).bundle.rows[0].reason_codes, [])

    def test_all_row_cutoffs_must_match_cycle_cutoff(self) -> None:
        ledger = ExactSixLedger()
        candidate = bundle()
        candidate.rows[-1].cutoff_epoch += 1

        with self.assertRaisesRegex(LedgerCommitError, "cutoff"):
            ledger.commit(candidate, committed_at_epoch=CUTOFF + 1)

        self.assertEqual(len(ledger), 0)


if __name__ == "__main__":
    unittest.main()
