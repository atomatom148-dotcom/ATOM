"""End-to-end integrity proof for the complete, thin Phase B spine."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
from quant.resolver import Resolver
from quant.snapshot import from_price
from quant.status import build_status
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


class PhaseBSpineTests(unittest.TestCase):
    def write(self, ledger: Ledger, cycle_id: str, committed_at: float):
        return write_cycle(
            from_price("COIN", 150.0, asof_epoch=CUTOFF),
            ledger,
            cycle_id=cycle_id,
            cutoff_epoch=CUTOFF,
            committed_at_epoch=committed_at,
        )

    def test_commit_timing_range_is_enforced_atomically(self) -> None:
        ledger = Ledger()
        record = self.write(ledger, "valid", CUTOFF)
        self.assertEqual(record.committed_at_epoch, CUTOFF)
        self.assertEqual(ledger.count(), 1)

        for cycle_id, invalid in (
            ("before", CUTOFF - 1),
            ("at-maturity", CUTOFF + 30),
            ("after-maturity", CUTOFF + 31),
            ("nan", math.nan),
            ("positive-infinity", math.inf),
            ("negative-infinity", -math.inf),
        ):
            with self.subTest(committed_at_epoch=invalid):
                with self.assertRaises(ValueError):
                    self.write(ledger, cycle_id, invalid)
                self.assertEqual(ledger.count(), 1)
                self.assertIsNone(ledger.get(cycle_id))

    def test_resolution_identity_validation_and_status_are_truthful(self) -> None:
        ledger = Ledger()
        record = self.write(ledger, "cycle-1", CUTOFF)
        forecast_before = deepcopy(record)
        resolver = Resolver()

        first = resolver.resolve_due(
            record,
            now_epoch=CUTOFF + 30,
            prices_by_horizon={"30S": 151.0},
        )
        second = resolver.resolve_due(
            record,
            now_epoch=CUTOFF + 60,
            prices_by_horizon={"1M": 152.0},
        )

        self.assertEqual([item.horizon for item in first], ["30S"])
        self.assertEqual([item.horizon for item in second], ["1M"])
        self.assertEqual(resolver.count(), 2)
        identities = {
            (item.cycle_id, item.horizon, item.maturity_epoch)
            for item in resolver.all()
        }
        self.assertEqual(len(identities), 2)
        self.assertEqual(build_status(ledger, resolver).resolved_count, 2)
        self.assertEqual(record, forecast_before)

        before = resolver.all()
        for now_epoch, prices in (
            (CUTOFF + 60, {"30S": 999.0}),
            (CUTOFF + 60, {"UNKNOWN": 153.0}),
            (CUTOFF + 60, {"5M": 153.0}),
        ):
            with self.subTest(prices=prices):
                with self.assertRaises(ValueError):
                    resolver.resolve_due(
                        record,
                        now_epoch=now_epoch,
                        prices_by_horizon=prices,
                    )
                self.assertEqual(resolver.all(), before)

        self.assertEqual(
            resolver.resolve_due(
                record,
                now_epoch=CUTOFF + 300,
                prices_by_horizon={},
            ),
            [],
        )
        self.assertIsNone(resolver.get("cycle-1", "5M"))
        self.assertEqual(resolver.count(), 2)
        self.assertEqual(record, forecast_before)


if __name__ == "__main__":
    unittest.main()
