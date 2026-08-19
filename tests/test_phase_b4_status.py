"""Phase B4 proofs for minimal truthful quant status."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
from quant.resolver import resolve_due
from quant.snapshot import from_price
import quant.status as status
from quant.status import QuantStatus, build_status
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


def commit(ledger: Ledger, cycle_id: str, cutoff_epoch: float = CUTOFF):
    return write_cycle(
        from_price("COIN", 150.0),
        ledger,
        cycle_id=cycle_id,
        cutoff_epoch=cutoff_epoch,
    )


class PhaseB4StatusTests(unittest.TestCase):
    def test_empty_ledger_and_no_outcomes(self) -> None:
        self.assertEqual(
            build_status(Ledger(), []),
            QuantStatus(False, 0, None, 0, False),
        )

    def test_one_committed_cycle_and_no_outcomes(self) -> None:
        ledger = Ledger()
        commit(ledger, "cycle-1")

        self.assertEqual(
            build_status(ledger, []),
            QuantStatus(True, 1, "cycle-1", 0, False),
        )

    def test_one_actual_resolved_outcome(self) -> None:
        ledger = Ledger()
        record = commit(ledger, "cycle-1")
        outcomes = resolve_due(
            record,
            now_epoch=CUTOFF + 30,
            outcome_price=151.25,
        )

        self.assertEqual(
            build_status(ledger, outcomes),
            QuantStatus(True, 1, "cycle-1", 1, True),
        )

    def test_six_actual_resolved_outcomes(self) -> None:
        ledger = Ledger()
        record = commit(ledger, "cycle-1")
        outcomes = resolve_due(
            record,
            now_epoch=CUTOFF + 3600,
            outcome_price=151.25,
        )

        self.assertEqual(
            build_status(ledger, outcomes),
            QuantStatus(True, 1, "cycle-1", 6, True),
        )

    def test_multiple_cycles_report_exact_count_and_latest_cycle_id(self) -> None:
        ledger = Ledger()
        commit(ledger, "cycle-1")
        commit(ledger, "cycle-2", CUTOFF + 1)
        commit(ledger, "cycle-3", CUTOFF + 2)

        result = build_status(ledger, [])

        self.assertEqual(result.ledger_count, 3)
        self.assertEqual(result.latest_cycle_id, "cycle-3")

    def test_build_status_does_not_mutate_ledger_or_outcomes(self) -> None:
        ledger = Ledger()
        record = commit(ledger, "cycle-1")
        outcomes = resolve_due(
            record,
            now_epoch=CUTOFF + 60,
            outcome_price=151.25,
        )
        ledger_before = ledger.get("cycle-1")
        outcomes_before = deepcopy(outcomes)

        build_status(ledger, outcomes)

        self.assertEqual(ledger.count(), 1)
        self.assertEqual(ledger.get("cycle-1"), ledger_before)
        self.assertEqual(outcomes, outcomes_before)

    def test_forbidden_surfaces_are_absent(self) -> None:
        for name in (
            "ready",
            "healthy",
            "certified",
            "predictive_score",
            "probability",
            "worker",
            "broker",
            "execution",
            "persistence",
            "http",
            "ui",
        ):
            self.assertFalse(hasattr(QuantStatus, name), name)
            self.assertFalse(hasattr(status, name), name)


if __name__ == "__main__":
    unittest.main()
