"""Phase D5 certification of deterministic D1-D4 evidence operations."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.blocking import assess_blocking
from quant.hydration import hydrate_exact_six
from quant.ledger import Ledger, LedgerRecord
from quant.models import (
    ExactSixBundle,
    HORIZONS,
    HorizonForecast,
    SetupState,
    Snapshot,
)
from quant.recovery import assess_recovery
from quant.resolver import ResolvedOutcome, Resolver
from quant.staleness import assess_staleness
from quant.structure import evaluate_structure
from quant.vol_friction import evaluate_vol_friction


CUTOFF = 1_700_000_100.25
SECONDS = (30, 60, 300, 900, 1800, 3600)


def stored_record() -> LedgerRecord:
    return LedgerRecord(
        bundle=ExactSixBundle(
            cycle_id="cycle-certified",
            symbol="COIN",
            cutoff_epoch=CUTOFF,
            snapshot_hash="snapshot-certified",
            policy_version="stored-policy",
            rows=[
                HorizonForecast(
                    horizon=horizon,
                    setup_state=SetupState.NO_SETUP,
                    reason_codes=["STORED"],
                    cutoff_epoch=CUTOFF,
                    maturity_epoch=CUTOFF + seconds,
                )
                for horizon, seconds in zip(HORIZONS, SECONDS)
            ],
        ),
        committed_at_epoch=CUTOFF + 0.125,
    )


def stored_outcomes(record: LedgerRecord) -> tuple[ResolvedOutcome, ...]:
    return (
        ResolvedOutcome(
            record.bundle.cycle_id,
            "30S",
            CUTOFF + 30,
            CUTOFF + 30.5,
            150.875,
        ),
        ResolvedOutcome(
            record.bundle.cycle_id,
            "1M",
            CUTOFF + 60,
            CUTOFF + 60.75,
            151.25,
        ),
    )


def numerical_evidence() -> tuple[float | int | None, ...]:
    """Run D1-D4 and expose only their existing numerical evidence."""

    record = stored_record()
    outcomes = stored_outcomes(record)
    hydrated = hydrate_exact_six(records=(record,), outcomes=outcomes)
    recovery = assess_recovery(hydrated.ledger, hydrated.resolver)

    snapshot = Snapshot(
        symbol="COIN",
        asof_epoch=CUTOFF - 12.5,
        last=150.5,
        bid=150.25,
        ask=150.75,
        bar_close=149.75,
        fresh=True,
    )
    staleness = assess_staleness(
        snapshot,
        now_epoch=CUTOFF,
        max_age_seconds=30.0,
    )
    vol_friction = evaluate_vol_friction(snapshot)
    structure = evaluate_structure(snapshot)
    assess_blocking(
        staleness=staleness,
        vol_friction=vol_friction,
        structure=structure,
    )

    restored = hydrated.ledger.get(record.bundle.cycle_id)
    restored_outcomes = hydrated.resolver.all()
    assert restored is not None
    return (
        recovery.ledger_records,
        recovery.resolved_outcomes,
        staleness.age_seconds,
        vol_friction.range_pct,
        vol_friction.spread_pct,
        vol_friction.net_range_pct,
        structure.distance_from_close_pct,
        structure.midpoint,
        structure.distance_from_mid_pct,
        structure.location_in_quote,
        hydrated.ledger_records,
        hydrated.resolved_outcomes,
        restored.committed_at_epoch,
        restored.bundle.cutoff_epoch,
        *(row.maturity_epoch for row in restored.bundle.rows),
        *(outcome.outcome_price for outcome in restored_outcomes),
        *(outcome.resolved_at_epoch for outcome in restored_outcomes),
    )


class PhaseD5CertificationTests(unittest.TestCase):
    def test_d1_d4_numerical_evidence_is_exact_and_deterministic(self) -> None:
        expected = (
            1,
            2,
            12.5,
            0.75 / 150.5,
            0.5 / 150.5,
            (0.75 / 150.5) - (0.5 / 150.5),
            0.75 / 150.5,
            150.5,
            0.0,
            0.5,
            1,
            2,
            CUTOFF + 0.125,
            CUTOFF,
            *(CUTOFF + seconds for seconds in SECONDS),
            150.875,
            151.25,
            CUTOFF + 30.5,
            CUTOFF + 60.75,
        )

        first = numerical_evidence()
        second = numerical_evidence()

        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        self.assertEqual(first, second)
        self.assertTrue(
            all(
                value is None or type(value) in (int, float)
                for value in first
            )
        )

    def test_certification_does_not_mutate_supplied_evidence(self) -> None:
        record = stored_record()
        outcomes = stored_outcomes(record)
        before = deepcopy((record, outcomes))

        first = hydrate_exact_six(records=(record,), outcomes=outcomes)
        second = hydrate_exact_six(records=(record,), outcomes=outcomes)

        self.assertEqual((record, outcomes), before)
        self.assertEqual(first.ledger.get("cycle-certified"), before[0])
        self.assertEqual(second.ledger.get("cycle-certified"), before[0])
        self.assertEqual(first.resolver.all(), second.resolver.all())

    def test_certification_adds_no_runtime_authority(self) -> None:
        import quant

        self.assertFalse(hasattr(quant, "certification"))
        self.assertFalse(hasattr(quant, "certify"))
        self.assertFalse(hasattr(quant, "score"))
        self.assertFalse(hasattr(quant, "rank"))
        self.assertFalse(hasattr(quant, "predict"))


if __name__ == "__main__":
    unittest.main()
