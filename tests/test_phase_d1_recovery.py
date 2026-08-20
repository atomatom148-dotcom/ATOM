"""Phase D1 proofs for restart recovery from existing evidence."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quant.recovery as recovery
from quant.ledger import Ledger
from quant.recovery import recover_state
from quant.resolver import ResolvedOutcome, Resolver
from quant.snapshot import from_price
from quant.status import QuantStatus, build_status
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


def evidence():
    ledger = Ledger()
    resolver = Resolver()
    first = write_cycle(
        from_price("COIN", 150.0), ledger, cycle_id="cycle-1",
        cutoff_epoch=CUTOFF, committed_at_epoch=CUTOFF,
    )
    write_cycle(
        from_price("COIN", 151.0), ledger, cycle_id="cycle-2",
        cutoff_epoch=CUTOFF + 1, committed_at_epoch=CUTOFF + 1,
    )
    resolver.resolve_due(
        first, now_epoch=CUTOFF + 60,
        prices_by_horizon={"30S": 152.0, "1M": 153.0},
    )
    return [ledger.get("cycle-1"), ledger.get("cycle-2")], resolver.all()


class PhaseD1RecoveryTests(unittest.TestCase):
    def test_restart_recovers_truthful_phase_b_state(self) -> None:
        records, outcomes = evidence()

        state = recover_state(records, outcomes)

        self.assertEqual(state.ledger.count(), 2)
        self.assertEqual(state.ledger.latest(), records[1])
        self.assertEqual(state.resolver.all(), outcomes)
        self.assertEqual(
            build_status(state.ledger, state.resolver),
            QuantStatus(True, 2, "cycle-2", 2, True),
        )

    def test_empty_restart_stays_truthfully_empty(self) -> None:
        state = recover_state([], [])

        self.assertEqual(
            build_status(state.ledger, state.resolver),
            QuantStatus(False, 0, None, 0, False),
        )

    def test_recovery_does_not_mutate_or_alias_evidence(self) -> None:
        records, outcomes = evidence()
        before = deepcopy((records, outcomes))

        state = recover_state(records, outcomes)
        self.assertEqual((records, outcomes), before)
        records[0].bundle.rows[0].reason_codes.append("MUTATED")
        outcomes.clear()

        self.assertEqual(state.ledger.count(), 2)
        self.assertEqual(state.resolver.count(), 2)
        self.assertNotIn(
            "MUTATED",
            state.ledger.get("cycle-1").bundle.rows[0].reason_codes,
        )

    def test_invalid_evidence_returns_no_partial_state(self) -> None:
        records, outcomes = evidence()
        invalid = outcomes + [
            ResolvedOutcome(
                cycle_id="missing", horizon="30S",
                maturity_epoch=CUTOFF + 30,
                resolved_at_epoch=CUTOFF + 60, outcome_price=154.0,
            )
        ]

        with self.assertRaisesRegex(ValueError, "unknown cycle"):
            recover_state(records, invalid)

    def test_maturity_identity_must_match_committed_row(self) -> None:
        records, outcomes = evidence()
        outcome = outcomes[0]
        outcomes[0] = ResolvedOutcome(
            outcome.cycle_id, outcome.horizon, outcome.maturity_epoch + 1,
            outcome.resolved_at_epoch, outcome.outcome_price,
        )

        with self.assertRaisesRegex(ValueError, "committed horizon"):
            recover_state(records, outcomes)

    def test_d1_has_no_persistence_or_later_phase_surface(self) -> None:
        for name in (
            "save", "load", "serialize", "deserialize", "database", "file",
            "stale", "blocked_model", "hydrate", "broker", "execute",
        ):
            self.assertFalse(hasattr(recovery, name), name)


if __name__ == "__main__":
    unittest.main()
