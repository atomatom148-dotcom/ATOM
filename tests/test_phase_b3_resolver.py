"""Phase B3 proofs for the minimal due-horizon resolver."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
import quant.resolver as resolver
from quant.resolver import ResolvedOutcome, resolve_due
from quant.snapshot import from_price
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.0
OUTCOME_PRICE = 151.25


class PhaseB3ResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = Ledger()
        self.record = write_cycle(
            from_price("COIN", 150.0),
            self.ledger,
            cycle_id="cycle-1",
            cutoff_epoch=CUTOFF,
        )

    def resolve(self, now_epoch: float) -> list[ResolvedOutcome]:
        return resolve_due(
            self.record,
            now_epoch=now_epoch,
            outcome_price=OUTCOME_PRICE,
        )

    def test_before_30s_returns_nothing(self) -> None:
        self.assertEqual(self.resolve(CUTOFF + 29), [])

    def test_exactly_30s_returns_only_30s(self) -> None:
        self.assertEqual(
            [outcome.horizon for outcome in self.resolve(CUTOFF + 30)],
            ["30S"],
        )

    def test_exactly_60s_returns_30s_then_1m(self) -> None:
        self.assertEqual(
            [outcome.horizon for outcome in self.resolve(CUTOFF + 60)],
            ["30S", "1M"],
        )

    def test_after_1h_returns_all_six_in_frozen_order(self) -> None:
        self.assertEqual(
            [outcome.horizon for outcome in self.resolve(CUTOFF + 3601)],
            ["30S", "1M", "5M", "15M", "30M", "1H"],
        )

    def test_identity_and_resolution_evidence_are_preserved(self) -> None:
        now_epoch = CUTOFF + 60
        outcomes = self.resolve(now_epoch)

        self.assertTrue(all(isinstance(item, ResolvedOutcome) for item in outcomes))
        self.assertEqual([item.cycle_id for item in outcomes], ["cycle-1"] * 2)
        self.assertEqual(
            [item.maturity_epoch for item in outcomes],
            [row.maturity_epoch for row in self.record.bundle.rows[:2]],
        )
        self.assertEqual([item.resolved_at_epoch for item in outcomes], [now_epoch] * 2)
        self.assertEqual([item.outcome_price for item in outcomes], [OUTCOME_PRICE] * 2)

    def test_original_forecast_and_ledger_remain_unchanged(self) -> None:
        record_before = deepcopy(self.record)
        ledger_before = self.ledger.get("cycle-1")

        self.resolve(CUTOFF + 3601)

        self.assertEqual(self.record, record_before)
        self.assertEqual(self.ledger.count(), 1)
        self.assertEqual(self.ledger.get("cycle-1"), ledger_before)

    def test_invalid_outcome_prices_are_rejected_before_resolving(self) -> None:
        for invalid in (0.0, -1.0, math.nan, math.inf, -math.inf):
            with self.subTest(outcome_price=invalid):
                with self.assertRaisesRegex(ValueError, "positive and finite"):
                    resolve_due(
                        self.record,
                        now_epoch=CUTOFF + 29,
                        outcome_price=invalid,
                    )

    def test_forbidden_surfaces_are_absent(self) -> None:
        for name in (
            "direction",
            "probability",
            "score",
            "pnl",
            "classification",
            "persist",
            "deduplicate",
            "status",
            "broker",
            "order",
            "execute",
            "execution",
        ):
            self.assertFalse(hasattr(ResolvedOutcome, name), name)
            self.assertFalse(hasattr(resolver, name), name)


if __name__ == "__main__":
    unittest.main()
