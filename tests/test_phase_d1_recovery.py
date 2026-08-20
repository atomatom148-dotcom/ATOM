"""Phase D1 proofs for honest restart-loss assessment."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
import quant.recovery as recovery
from quant.recovery import RecoveryStatus, assess_recovery
from quant.resolver import Resolver
from quant.snapshot import from_price
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


def commit(ledger: Ledger, cycle_id: str = "cycle-1"):
    return write_cycle(
        from_price("COIN", 150.0),
        ledger,
        cycle_id=cycle_id,
        cutoff_epoch=CUTOFF,
        committed_at_epoch=CUTOFF,
    )


class PhaseD1RecoveryTests(unittest.TestCase):
    def test_empty_ledger_and_resolver_are_recoverable(self) -> None:
        self.assertEqual(
            assess_recovery(Ledger(), Resolver()),
            RecoveryStatus(
                ledger_records=0,
                resolved_outcomes=0,
                recoverable=True,
                reason_codes=(),
            ),
        )

    def test_committed_ledger_reports_exact_count_and_loss_reason(self) -> None:
        ledger = Ledger()
        commit(ledger, "cycle-1")
        commit(ledger, "cycle-2")

        self.assertEqual(
            assess_recovery(ledger, Resolver()),
            RecoveryStatus(
                ledger_records=2,
                resolved_outcomes=0,
                recoverable=False,
                reason_codes=("VOLATILE_LEDGER_NOT_DURABLE",),
            ),
        )

    def test_actual_resolve_reports_exact_counts_and_ordered_reasons(self) -> None:
        ledger = Ledger()
        record = commit(ledger)
        resolver = Resolver()
        resolver.resolve_due(
            record,
            now_epoch=CUTOFF + 30,
            prices_by_horizon={"30S": 151.0},
        )

        self.assertEqual(
            assess_recovery(ledger, resolver),
            RecoveryStatus(
                ledger_records=1,
                resolved_outcomes=1,
                recoverable=False,
                reason_codes=(
                    "VOLATILE_LEDGER_NOT_DURABLE",
                    "VOLATILE_RESOLVER_NOT_DURABLE",
                ),
            ),
        )

    def test_assessment_does_not_mutate_ledger_or_resolver(self) -> None:
        ledger = Ledger()
        record = commit(ledger)
        resolver = Resolver()
        resolver.resolve_due(
            record,
            now_epoch=CUTOFF + 30,
            prices_by_horizon={"30S": 151.0},
        )
        ledger_before = deepcopy(ledger.get("cycle-1"))
        outcomes_before = resolver.all()

        assess_recovery(ledger, resolver)

        self.assertEqual(ledger.count(), 1)
        self.assertEqual(ledger.get("cycle-1"), ledger_before)
        self.assertEqual(resolver.count(), 1)
        self.assertEqual(resolver.all(), outcomes_before)

    def test_forbidden_surfaces_are_absent(self) -> None:
        forbidden = (
            "RecoveredState", "recover_state", "reconstruct", "replay",
            "hydrate", "durability", "persistence", "file", "database",
            "supabase", "render", "worker", "ready", "predictive_ready",
            "certified", "http", "api", "ui", "broker", "execution",
            "stale", "blocked_model",
        )
        for name in forbidden:
            self.assertFalse(hasattr(recovery, name), name)
            self.assertFalse(hasattr(RecoveryStatus, name), name)

        self.assertEqual(
            tuple(RecoveryStatus.__dataclass_fields__),
            (
                "ledger_records",
                "resolved_outcomes",
                "recoverable",
                "reason_codes",
            ),
        )


if __name__ == "__main__":
    unittest.main()
