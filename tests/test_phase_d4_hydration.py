"""Phase D4 proofs for exact-six stored-evidence hydration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import quant.hydration as hydration
from quant.hydration import hydrate_exact_six, store_exact_six
from quant.ledger import Ledger
from quant.snapshot import from_price
from quant.unified_quant import write_cycle


CUTOFF = 1_700_000_100.25


def record():
    return write_cycle(
        from_price(
            "COIN", 150.125, bid=150.0, ask=150.25,
            asof_epoch=CUTOFF,
        ),
        Ledger(),
        cycle_id="cycle-stored",
        cutoff_epoch=CUTOFF,
        committed_at_epoch=CUTOFF + 0.125,
        policy_version="stored-policy",
    )


class PhaseD4HydrationTests(unittest.TestCase):
    def test_numbers_round_trip_as_exact_stored_evidence(self) -> None:
        original = record()
        original.bundle.rows[0].probability = 0.625
        original.bundle.rows[0].direction = "UP"

        restored = hydrate_exact_six(store_exact_six(original), Ledger())

        self.assertEqual(restored, original)
        self.assertEqual(restored.committed_at_epoch, CUTOFF + 0.125)
        self.assertEqual(restored.bundle.rows[0].probability, 0.625)
        self.assertEqual(restored.bundle.rows[0].maturity_epoch, CUTOFF + 30)

    def test_hydration_commits_only_the_supplied_record(self) -> None:
        target = Ledger()

        restored = hydrate_exact_six(store_exact_six(record()), target)

        self.assertEqual(target.count(), 1)
        self.assertEqual(target.get("cycle-stored"), restored)

    def test_missing_or_extra_fields_are_not_inferred(self) -> None:
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation):
                stored = store_exact_six(record())
                if mutation == "missing":
                    del stored["bundle"]["rows"][0]["probability"]
                else:
                    stored["bundle"]["rows"][0]["score"] = 1

                with self.assertRaisesRegex(ValueError, "exact stored fields"):
                    hydrate_exact_six(stored, Ledger())

    def test_invalid_number_does_not_partially_commit(self) -> None:
        target = Ledger()
        stored = store_exact_six(record())
        stored["bundle"]["rows"][5]["maturity_epoch"] = float("nan")

        with self.assertRaisesRegex(ValueError, "must be finite"):
            hydrate_exact_six(stored, target)

        self.assertEqual(target.count(), 0)

    def test_stored_and_returned_values_are_detached(self) -> None:
        original = record()
        stored = store_exact_six(original)
        before = deepcopy(stored)
        restored = hydrate_exact_six(stored, Ledger())

        stored["bundle"]["rows"][0]["reason_codes"].append("MUTATED")
        restored.bundle.rows[1].reason_codes.append("MUTATED")

        self.assertEqual(before, store_exact_six(original))
        self.assertEqual(restored.bundle.rows[0].reason_codes, [])

    def test_existing_cycle_is_not_replaced(self) -> None:
        target = Ledger()
        stored = store_exact_six(record())
        hydrate_exact_six(stored, target)

        with self.assertRaisesRegex(ValueError, "already committed"):
            hydrate_exact_six(stored, target)

        self.assertEqual(target.count(), 1)

    def test_public_contract_is_exactly_d4(self) -> None:
        self.assertEqual(
            hydration.__all__, ["hydrate_exact_six", "store_exact_six"]
        )
        for forbidden in (
            "forecast", "predict", "infer", "score", "rank", "weight",
            "agent", "brain", "resolve", "outcome", "interpret",
        ):
            self.assertFalse(hasattr(hydration, forbidden), forbidden)


if __name__ == "__main__":
    unittest.main()
