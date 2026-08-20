"""Phase D2 proofs for deterministic stale-evidence assessment."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.models import Snapshot
import quant.staleness as staleness
from quant.staleness import StalenessEvidence, assess_staleness


NOW = 1_700_000_100.0
MAX_AGE = 45.5


def snapshot(*, asof_epoch: float = NOW, fresh: bool = True) -> Snapshot:
    return Snapshot(
        symbol="COIN",
        asof_epoch=asof_epoch,
        last=150.0,
        fresh=fresh,
        reason_codes=["IGNORED_INTAKE_REASON"],
    )


class PhaseD2StalenessTests(unittest.TestCase):
    def assess(
        self,
        item: Snapshot,
        *,
        now_epoch: float = NOW,
        max_age_seconds: float = MAX_AGE,
    ) -> StalenessEvidence:
        return assess_staleness(
            item,
            now_epoch=now_epoch,
            max_age_seconds=max_age_seconds,
        )

    def test_age_zero_is_usable(self) -> None:
        self.assertEqual(
            self.assess(snapshot()),
            StalenessEvidence(True, 0.0, ()),
        )

    def test_exact_max_age_boundary_is_usable(self) -> None:
        self.assertEqual(
            self.assess(snapshot(asof_epoch=NOW - MAX_AGE)),
            StalenessEvidence(True, MAX_AGE, ()),
        )

    def test_caller_supplies_age_limit(self) -> None:
        item = snapshot(asof_epoch=NOW - 10)

        self.assertEqual(
            self.assess(item, max_age_seconds=9),
            StalenessEvidence(False, 10.0, ("SNAPSHOT_TOO_OLD",)),
        )
        self.assertEqual(
            self.assess(item, max_age_seconds=10),
            StalenessEvidence(True, 10.0, ()),
        )

    def test_staleness_does_not_depend_on_snapshot_price_usability(self) -> None:
        item = snapshot()
        item.last = None

        self.assertEqual(
            self.assess(item),
            StalenessEvidence(True, 0.0, ()),
        )

    def test_age_above_max_is_unusable_with_exact_age(self) -> None:
        self.assertEqual(
            self.assess(snapshot(asof_epoch=NOW - 45.75)),
            StalenessEvidence(False, 45.75, ("SNAPSHOT_TOO_OLD",)),
        )

    def test_snapshot_marked_stale_has_one_deterministic_reason(self) -> None:
        self.assertEqual(
            self.assess(snapshot(asof_epoch=NOW - 2, fresh=False)),
            StalenessEvidence(False, 2.0, ("SNAPSHOT_MARKED_STALE",)),
        )

    def test_future_timestamp_retains_negative_age(self) -> None:
        self.assertEqual(
            self.assess(snapshot(asof_epoch=NOW + 1.25)),
            StalenessEvidence(
                False, -1.25, ("SNAPSHOT_FROM_FUTURE",)
            ),
        )

    def test_invalid_now_epoch_is_rejected_before_arithmetic(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), True):
            with self.subTest(value=value):
                self.assertEqual(
                    self.assess(snapshot(), now_epoch=value),
                    StalenessEvidence(False, None, ("INVALID_NOW_EPOCH",)),
                )

    def test_invalid_max_age_is_rejected_before_arithmetic(self) -> None:
        values = (float("nan"), float("inf"), float("-inf"), True, -0.1)
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(
                    self.assess(snapshot(), max_age_seconds=value),
                    StalenessEvidence(
                        False, None, ("INVALID_MAX_AGE_SECONDS",)
                    ),
                )

    def test_invalid_asof_epoch_is_rejected_before_arithmetic(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), True):
            with self.subTest(value=value):
                self.assertEqual(
                    self.assess(snapshot(asof_epoch=value)),
                    StalenessEvidence(False, None, ("INVALID_ASOF_EPOCH",)),
                )

    def test_validation_order_is_deterministic(self) -> None:
        self.assertEqual(
            self.assess(
                snapshot(asof_epoch=float("nan")),
                now_epoch=False,
                max_age_seconds=-1,
            ),
            StalenessEvidence(False, None, ("INVALID_NOW_EPOCH",)),
        )
        self.assertEqual(
            self.assess(
                snapshot(asof_epoch=float("nan")),
                max_age_seconds=-1,
            ),
            StalenessEvidence(False, None, ("INVALID_MAX_AGE_SECONDS",)),
        )

    def test_assessment_does_not_mutate_snapshot(self) -> None:
        item = snapshot(asof_epoch=NOW - 46, fresh=False)
        before = deepcopy(item)

        self.assess(item)

        self.assertEqual(item, before)

    def test_public_surface_stays_limited_to_d2_evidence(self) -> None:
        forbidden = (
            "MAX_SNAPSHOT_AGE_SECONDS", "StalenessStatus", "prediction",
            "direction", "probability", "score", "adaptive_threshold",
            "forecast", "ledger", "resolver", "status", "persistence",
            "hydration", "worker", "ui", "broker", "execution",
        )
        for name in forbidden:
            self.assertFalse(hasattr(staleness, name), name)
            self.assertFalse(hasattr(StalenessEvidence, name), name)

        self.assertEqual(
            tuple(StalenessEvidence.__dataclass_fields__),
            ("usable", "age_seconds", "reason_codes"),
        )


if __name__ == "__main__":
    unittest.main()
