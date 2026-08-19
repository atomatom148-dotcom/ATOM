"""Phase B3 proofs for the minimal due-horizon resolver."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
from quant.resolver import due_horizons
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
        )

    def test_nothing_is_due_before_the_first_maturity(self) -> None:
        self.assertEqual(due_horizons(self.record, CUTOFF + 29), [])

    def test_maturity_boundary_is_due_and_order_is_preserved(self) -> None:
        self.assertEqual(due_horizons(self.record, CUTOFF + 30), ["30S"])
        self.assertEqual(
            due_horizons(self.record, CUTOFF + 900),
            ["30S", "1M", "5M", "15M"],
        )

    def test_all_six_horizons_are_due_at_the_last_maturity(self) -> None:
        self.assertEqual(
            due_horizons(self.record, CUTOFF + 3600),
            ["30S", "1M", "5M", "15M", "30M", "1H"],
        )

    def test_selection_does_not_mutate_committed_evidence(self) -> None:
        before = self.ledger.get("cycle-1")

        due_horizons(self.record, CUTOFF + 3600)

        self.assertEqual(self.ledger.count(), 1)
        self.assertEqual(self.ledger.get("cycle-1"), before)


if __name__ == "__main__":
    unittest.main()
