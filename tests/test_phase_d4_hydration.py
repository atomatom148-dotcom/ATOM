"""Phase D4 proofs for exact restoration of existing evidence objects."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quant.hydration as hydration
from quant.hydration import HydratedState, hydrate_exact_six
from quant.ledger import Ledger, LedgerRecord
from quant.models import ExactSixBundle, HORIZONS, HorizonForecast, SetupState
from quant.resolver import ResolvedOutcome, Resolver


CUTOFF = 1_700_000_100.25
SECONDS = (30, 60, 300, 900, 1800, 3600)


def record(
    cycle_id: str = "cycle-1",
    *,
    cutoff: float = CUTOFF,
    committed_at: float | None = None,
) -> LedgerRecord:
    return LedgerRecord(
        bundle=ExactSixBundle(
            cycle_id=cycle_id,
            symbol="COIN",
            cutoff_epoch=cutoff,
            snapshot_hash=f"snapshot-{cycle_id}",
            policy_version="stored-policy",
            rows=[
                HorizonForecast(
                    horizon=horizon,
                    setup_state=(
                        SetupState.QUALIFIED
                        if index == 0
                        else SetupState.NO_SETUP
                    ),
                    direction="UP" if index == 0 else None,
                    probability=0.625 if index == 0 else None,
                    reason_codes=[f"STORED-{index}"],
                    cutoff_epoch=cutoff,
                    maturity_epoch=cutoff + seconds,
                )
                for index, (horizon, seconds) in enumerate(
                    zip(HORIZONS, SECONDS)
                )
            ],
        ),
        committed_at_epoch=(
            cutoff + 0.125 if committed_at is None else committed_at
        ),
    )


def outcome(
    item: LedgerRecord,
    horizon: str,
    *,
    price: float,
    resolved_at: float,
    maturity: float | None = None,
) -> ResolvedOutcome:
    row = next(row for row in item.bundle.rows if row.horizon == horizon)
    return ResolvedOutcome(
        cycle_id=item.bundle.cycle_id,
        horizon=horizon,
        maturity_epoch=row.maturity_epoch if maturity is None else maturity,
        resolved_at_epoch=resolved_at,
        outcome_price=price,
    )


class PhaseD4HydrationTests(unittest.TestCase):
    def test_empty_evidence_returns_fresh_empty_stores(self) -> None:
        first = hydrate_exact_six(records=(), outcomes=())
        second = hydrate_exact_six(records=(), outcomes=())

        self.assertIsInstance(first, HydratedState)
        self.assertIsInstance(first.ledger, Ledger)
        self.assertIsInstance(first.resolver, Resolver)
        self.assertEqual((first.ledger_records, first.resolved_outcomes), (0, 0))
        self.assertIsNot(first.ledger, second.ledger)
        self.assertIsNot(first.resolver, second.resolver)

    def test_one_record_restores_every_value_exactly(self) -> None:
        supplied = record()

        state = hydrate_exact_six(records=(supplied,), outcomes=())

        self.assertEqual(state.ledger.get("cycle-1"), supplied)
        self.assertEqual(state.ledger_records, 1)
        self.assertEqual(state.resolved_outcomes, 0)

    def test_multiple_records_preserve_supplied_ledger_order(self) -> None:
        supplied = (record("cycle-2"), record("cycle-1"))

        state = hydrate_exact_six(records=supplied, outcomes=())

        self.assertEqual(state.ledger.count(), 2)
        self.assertEqual(state.ledger.latest(), supplied[-1])

    def test_outcomes_restore_exact_values_and_omissions_stay_unresolved(self) -> None:
        supplied_record = record()
        supplied_outcomes = (
            outcome(
                supplied_record,
                "1M",
                price=151.75,
                resolved_at=CUTOFF + 61.5,
            ),
            outcome(
                supplied_record,
                "30S",
                price=150.875,
                resolved_at=CUTOFF + 30.25,
            ),
        )

        state = hydrate_exact_six(
            records=(supplied_record,), outcomes=supplied_outcomes
        )

        self.assertEqual(state.resolver.all(), list(reversed(supplied_outcomes)))
        self.assertEqual(state.resolved_outcomes, 2)
        for horizon in HORIZONS[2:]:
            self.assertIsNone(state.resolver.get("cycle-1", horizon))

    def test_unknown_cycle_outcome_is_rejected(self) -> None:
        supplied = record()
        unknown = deepcopy(outcome(
            supplied, "30S", price=151.0, resolved_at=CUTOFF + 30
        ))
        object.__setattr__(unknown, "cycle_id", "unknown")

        with self.assertRaisesRegex(ValueError, "unknown cycle"):
            hydrate_exact_six(records=(supplied,), outcomes=(unknown,))

    def test_horizon_or_maturity_mismatch_is_rejected(self) -> None:
        supplied = record()
        cases = (
            ResolvedOutcome(
                "cycle-1", "2M", CUTOFF + 60, CUTOFF + 60, 151.0
            ),
            outcome(
                supplied,
                "30S",
                price=151.0,
                resolved_at=CUTOFF + 31,
                maturity=CUTOFF + 31,
            ),
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "must match"):
                    hydrate_exact_six(records=(supplied,), outcomes=(invalid,))

    def test_duplicate_cycle_is_rejected_by_ledger(self) -> None:
        supplied = record()

        with self.assertRaisesRegex(ValueError, "already committed"):
            hydrate_exact_six(records=(supplied, supplied), outcomes=())

    def test_duplicate_or_conflicting_outcome_identity_is_rejected(self) -> None:
        supplied = record()
        first = outcome(
            supplied, "30S", price=151.0, resolved_at=CUTOFF + 31
        )
        cases = (
            first,
            outcome(
                supplied, "30S", price=152.0, resolved_at=CUTOFF + 32
            ),
        )
        for second in cases:
            with self.subTest(second=second):
                with self.assertRaisesRegex(ValueError, "already resolved"):
                    hydrate_exact_six(
                        records=(supplied,), outcomes=(first, second)
                    )

    def test_invalid_commit_timing_is_rejected_by_ledger_law(self) -> None:
        invalid = record(committed_at=CUTOFF + 30)

        with self.assertRaisesRegex(ValueError, "before first horizon"):
            hydrate_exact_six(records=(invalid,), outcomes=())

    def test_invalid_outcome_price_or_time_is_rejected_by_resolver_law(self) -> None:
        supplied = record()
        cases = (
            outcome(
                supplied, "30S", price=-1.0, resolved_at=CUTOFF + 30
            ),
            outcome(
                supplied, "30S", price=151.0, resolved_at=CUTOFF + 29
            ),
            outcome(
                supplied, "30S", price=151.0, resolved_at=float("nan")
            ),
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    hydrate_exact_six(
                        records=(supplied,), outcomes=(invalid,)
                    )

    def test_inputs_are_unchanged_and_returned_stores_do_not_alias(self) -> None:
        supplied_record = record()
        supplied_outcome = outcome(
            supplied_record, "30S", price=151.0, resolved_at=CUTOFF + 31
        )
        before = deepcopy((supplied_record, supplied_outcome))

        state = hydrate_exact_six(
            records=(supplied_record,), outcomes=(supplied_outcome,)
        )
        supplied_record.bundle.rows[0].reason_codes.append("CALLER_MUTATION")
        fetched = state.ledger.get("cycle-1")
        fetched.bundle.rows[1].reason_codes.append("RETURN_MUTATION")

        self.assertEqual(before[1], supplied_outcome)
        self.assertEqual(before[0].bundle.rows[1:], supplied_record.bundle.rows[1:])
        self.assertEqual(
            state.ledger.get("cycle-1").bundle.rows[0].reason_codes,
            ["STORED-0"],
        )
        self.assertEqual(
            state.ledger.get("cycle-1").bundle.rows[1].reason_codes,
            ["STORED-1"],
        )
        self.assertIsNot(state.resolver.get("cycle-1", "30S"), supplied_outcome)

    def test_public_surface_is_exactly_d4(self) -> None:
        self.assertEqual(
            tuple(HydratedState.__dataclass_fields__),
            ("ledger", "resolver", "ledger_records", "resolved_outcomes"),
        )
        self.assertEqual(
            hydration.__all__, ["HydratedState", "hydrate_exact_six"]
        )
        for forbidden in (
            "store_exact_six", "UnifiedQuant", "write_cycle", "forecast",
            "generation", "inference", "score", "rank", "weight",
            "adaptive", "ai", "brain", "agent", "supabase", "render",
            "database", "file", "worker", "ui", "broker", "execution",
        ):
            self.assertFalse(hasattr(hydration, forbidden), forbidden)


if __name__ == "__main__":
    unittest.main()
