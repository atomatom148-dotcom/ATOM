"""Phase D2 proofs for deterministic stale-evidence protection."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.snapshot import from_price
from quant.staleness import (
    MAX_SNAPSHOT_AGE_SECONDS,
    StalenessStatus,
    assess_staleness,
)


NOW = 1_700_000_100.0


class PhaseD2StalenessTests(unittest.TestCase):
    def test_recent_evidence_is_usable(self) -> None:
        snapshot = from_price("COIN", 150.0, asof_epoch=NOW - 30)

        self.assertEqual(
            assess_staleness(snapshot, now_epoch=NOW),
            StalenessStatus(30.0, False, True, ()),
        )

    def test_threshold_is_inclusive_and_fixed(self) -> None:
        snapshot = from_price(
            "COIN", 150.0, asof_epoch=NOW - MAX_SNAPSHOT_AGE_SECONDS
        )

        self.assertTrue(assess_staleness(snapshot, now_epoch=NOW).usable)
        self.assertEqual(MAX_SNAPSHOT_AGE_SECONDS, 60.0)

    def test_old_evidence_is_stale_and_unusable(self) -> None:
        snapshot = from_price("COIN", 150.0, asof_epoch=NOW - 61)

        self.assertEqual(
            assess_staleness(snapshot, now_epoch=NOW),
            StalenessStatus(61.0, True, False, ("STALE_SNAPSHOT",)),
        )

    def test_existing_non_fresh_evidence_remains_unusable(self) -> None:
        snapshot = from_price(
            "COIN",
            150.0,
            fresh=False,
            asof_epoch=NOW,
            reason_codes=["FEED_DELAY"],
        )

        self.assertEqual(
            assess_staleness(snapshot, now_epoch=NOW),
            StalenessStatus(0.0, False, False, ("FEED_DELAY",)),
        )

    def test_future_evidence_is_rejected(self) -> None:
        snapshot = from_price("COIN", 150.0, asof_epoch=NOW + 1)

        self.assertEqual(
            assess_staleness(snapshot, now_epoch=NOW),
            StalenessStatus(-1.0, False, False, ("SNAPSHOT_FROM_FUTURE",)),
        )

    def test_assessment_does_not_mutate_snapshot(self) -> None:
        snapshot = from_price("COIN", 150.0, asof_epoch=NOW - 61)
        before = deepcopy(snapshot)

        assess_staleness(snapshot, now_epoch=NOW)

        self.assertEqual(snapshot, before)


if __name__ == "__main__":
    unittest.main()
