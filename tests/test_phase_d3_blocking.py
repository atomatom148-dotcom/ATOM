"""Phase D3 proofs for deterministic blocked-evidence assessment."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quant.blocking as blocking
from quant.blocking import BlockedEvidence, assess_blocked
from quant.ledger import Ledger
from quant.models import SetupState
from quant.snapshot import from_price
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


def bundle():
    ledger = Ledger()
    return write_cycle(
        from_price("COIN", 150.0),
        ledger,
        cycle_id="cycle-1",
        cutoff_epoch=CUTOFF,
        committed_at_epoch=CUTOFF,
    ).bundle


class PhaseD3BlockingTests(unittest.TestCase):
    def test_no_explicit_block_is_not_blocked(self) -> None:
        item = bundle()

        self.assertEqual(
            assess_blocked(item),
            BlockedEvidence(False, (), ()),
        )

    def test_explicit_blocked_rows_are_reported_in_horizon_order(self) -> None:
        item = bundle()
        item.rows[1].setup_state = SetupState.BLOCKED
        item.rows[1].reason_codes = ["FRICTION_BLOCK"]
        item.rows[4].setup_state = SetupState.BLOCKED
        item.rows[4].reason_codes = ["STRUCTURE_BLOCK", "MANUAL_BLOCK"]

        self.assertEqual(
            assess_blocked(item),
            BlockedEvidence(
                True,
                ("1M", "30M"),
                ("FRICTION_BLOCK", "STRUCTURE_BLOCK", "MANUAL_BLOCK"),
            ),
        )

    def test_only_blocked_rows_supply_reasons(self) -> None:
        item = bundle()
        item.rows[0].reason_codes = ["NO_SETUP_CONTEXT"]
        item.rows[1].setup_state = SetupState.UNAVAILABLE
        item.rows[1].reason_codes = ["MISSING_INPUT"]
        item.rows[2].setup_state = SetupState.BLOCKED
        item.rows[2].reason_codes = []

        self.assertEqual(
            assess_blocked(item),
            BlockedEvidence(True, ("5M",), ()),
        )

    def test_existing_reason_order_and_duplicates_are_authoritative(self) -> None:
        item = bundle()
        item.rows[0].setup_state = SetupState.BLOCKED
        item.rows[0].reason_codes = ["EXPLICIT", "EXPLICIT"]
        item.rows[1].setup_state = SetupState.BLOCKED
        item.rows[1].reason_codes = ["EXPLICIT"]

        self.assertEqual(
            assess_blocked(item).reason_codes,
            ("EXPLICIT", "EXPLICIT", "EXPLICIT"),
        )

    def test_assessment_does_not_mutate_bundle(self) -> None:
        item = bundle()
        item.rows[3].setup_state = SetupState.BLOCKED
        item.rows[3].reason_codes = ["EXPLICIT_BLOCK"]
        before = deepcopy(item)

        assess_blocked(item)

        self.assertEqual(item, before)

    def test_invalid_exact_six_evidence_is_rejected(self) -> None:
        item = bundle()
        item.rows[0].cutoff_epoch += 1

        with self.assertRaisesRegex(ValueError, "row cutoff"):
            assess_blocked(item)

    def test_public_surface_stays_limited_to_d3_assessment(self) -> None:
        forbidden = (
            "prediction", "direction", "probability", "score", "rank",
            "weight", "threshold", "adaptive", "forecast", "writer",
            "ledger", "resolver", "status", "persistence", "hydration",
            "worker", "ui", "broker", "execution",
        )
        for name in forbidden:
            self.assertFalse(hasattr(blocking, name), name)
            self.assertFalse(hasattr(BlockedEvidence, name), name)

        self.assertEqual(
            tuple(BlockedEvidence.__dataclass_fields__),
            ("blocked", "blocked_horizons", "reason_codes"),
        )


if __name__ == "__main__":
    unittest.main()
