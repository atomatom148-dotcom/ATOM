"""End-to-end proof of the complete, deliberately thin Phase B spine."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
from quant.resolver import Resolver
from quant.snapshot import from_price
from quant.status import QuantStatus, build_status
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


class PhaseBSpineTests(unittest.TestCase):
    def test_snapshot_commit_resolve_status_is_truthful_and_append_only(self) -> None:
        ledger = Ledger()
        resolver = Resolver()
        record = write_cycle(
            from_price("COIN", 150.0, asof_epoch=CUTOFF),
            ledger,
            cycle_id="cycle-1",
            cutoff_epoch=CUTOFF,
            committed_at_epoch=CUTOFF,
        )

        self.assertEqual(record.committed_at_epoch, CUTOFF)
        self.assertTrue(
            all(
                record.committed_at_epoch < row.maturity_epoch
                for row in record.bundle.rows
            )
        )
        self.assertEqual(
            build_status(ledger, resolver),
            QuantStatus(True, 1, "cycle-1", 0, False),
        )

        resolver.resolve_due(
            record, now_epoch=CUTOFF + 30, outcome_price=151.25
        )
        resolver.resolve_due(
            record, now_epoch=CUTOFF + 30, outcome_price=999.0
        )

        self.assertEqual(resolver.count(), 1)
        self.assertEqual(resolver.outcomes()[0].outcome_price, 151.25)
        self.assertEqual(
            build_status(ledger, resolver),
            QuantStatus(True, 1, "cycle-1", 1, True),
        )


if __name__ == "__main__":
    unittest.main()
