"""Phase B3 proofs for the append-only due-horizon resolver."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
from quant.resolver import ResolvedOutcome, Resolver
from quant.snapshot import from_price
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0


class PhaseB3ResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = Ledger()
        self.record = write_cycle(
            from_price("COIN", 150.0),
            self.ledger,
            cycle_id="cycle-1",
            cutoff_epoch=CUTOFF,
            committed_at_epoch=CUTOFF,
        )
        self.resolver = Resolver()

    def test_supplied_due_horizons_use_their_own_prices(self) -> None:
        outcomes = self.resolver.resolve_due(
            self.record,
            now_epoch=CUTOFF + 60,
            prices_by_horizon={"30S": 151.0, "1M": 152.0},
        )

        self.assertEqual([item.horizon for item in outcomes], ["30S", "1M"])
        self.assertEqual([item.outcome_price for item in outcomes], [151.0, 152.0])
        self.assertTrue(all(isinstance(item, ResolvedOutcome) for item in outcomes))

    def test_omitted_due_horizon_remains_unresolved(self) -> None:
        self.assertEqual(
            self.resolver.resolve_due(
                self.record,
                now_epoch=CUTOFF + 60,
                prices_by_horizon={"1M": 152.0},
            )[0].horizon,
            "1M",
        )
        self.assertIsNone(self.resolver.get("cycle-1", "30S"))

    def test_invalid_input_is_atomic(self) -> None:
        invalid_cases = (
            (CUTOFF + 30, {"UNKNOWN": 151.0}),
            (CUTOFF + 29, {"30S": 151.0}),
            (CUTOFF + 30, {"30S": 0.0}),
            (CUTOFF + 30, {"30S": math.nan}),
            (math.inf, {"30S": 151.0}),
        )
        for now_epoch, prices in invalid_cases:
            with self.subTest(now_epoch=now_epoch, prices=prices):
                with self.assertRaises(ValueError):
                    self.resolver.resolve_due(
                        self.record,
                        now_epoch=now_epoch,
                        prices_by_horizon=prices,
                    )
                self.assertEqual(self.resolver.count(), 0)

    def test_duplicate_is_rejected_before_other_writes(self) -> None:
        self.resolver.resolve_due(
            self.record,
            now_epoch=CUTOFF + 30,
            prices_by_horizon={"30S": 151.0},
        )
        before = self.resolver.all()

        with self.assertRaisesRegex(ValueError, "already resolved"):
            self.resolver.resolve_due(
                self.record,
                now_epoch=CUTOFF + 60,
                prices_by_horizon={"1M": 152.0, "30S": 999.0},
            )

        self.assertEqual(self.resolver.all(), before)

    def test_get_and_all_return_defensive_copies(self) -> None:
        self.resolver.resolve_due(
            self.record,
            now_epoch=CUTOFF + 30,
            prices_by_horizon={"30S": 151.0},
        )
        fetched = self.resolver.get("cycle-1", "30S")
        returned = self.resolver.all()
        returned.clear()

        self.assertEqual(fetched.horizon, "30S")
        self.assertIsNone(self.resolver.get("missing", "30S"))
        self.assertEqual(self.resolver.count(), 1)

    def test_original_forecast_and_ledger_remain_unchanged(self) -> None:
        record_before = deepcopy(self.record)
        ledger_before = self.ledger.get("cycle-1")

        self.resolver.resolve_due(
            self.record,
            now_epoch=CUTOFF + 30,
            prices_by_horizon={"30S": 151.0},
        )

        self.assertEqual(self.record, record_before)
        self.assertEqual(self.ledger.get("cycle-1"), ledger_before)


if __name__ == "__main__":
    unittest.main()
