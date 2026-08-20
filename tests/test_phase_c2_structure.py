"""Phase C2 proofs for descriptive structure evidence."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.models import Snapshot
import quant.structure as structure
from quant.structure import StructureEvidence, evaluate_structure


def snapshot(**overrides: object) -> Snapshot:
    values = {
        "symbol": "COIN",
        "asof_epoch": 1_700_000_000.0,
        "last": 102.0,
        "bid": 101.0,
        "ask": 103.0,
        "bar_close": 100.0,
        "source": "test",
        "fresh": True,
        "reason_codes": ["SOURCE_EVIDENCE"],
    }
    values.update(overrides)
    return Snapshot(**values)


class PhaseC2StructureTests(unittest.TestCase):
    def test_describes_above_below_and_at_bar_close(self) -> None:
        above = evaluate_structure(snapshot())
        below = evaluate_structure(snapshot(last=98.0))
        at_close = evaluate_structure(snapshot(last=100.0))

        self.assertEqual(
            above,
            StructureEvidence(True, 0.02, "ABOVE_BAR_CLOSE", ()),
        )
        self.assertEqual(below.displacement_pct, -0.02)
        self.assertEqual(below.relation, "BELOW_BAR_CLOSE")
        self.assertEqual(at_close.displacement_pct, 0.0)
        self.assertEqual(at_close.relation, "AT_BAR_CLOSE")

    def test_missing_and_invalid_evidence_remains_unavailable(self) -> None:
        for field in ("last", "bar_close"):
            with self.subTest(field=field, kind="missing"):
                evidence = evaluate_structure(snapshot(**{field: None}))
                self.assertEqual(
                    evidence.reason_codes, (f"MISSING_{field.upper()}",)
                )
                self.assertFalse(evidence.usable)
                self.assertIsNone(evidence.displacement_pct)
                self.assertIsNone(evidence.relation)

            for value in (0.0, -1.0, math.nan, math.inf, -math.inf, True):
                with self.subTest(field=field, value=value):
                    evidence = evaluate_structure(snapshot(**{field: value}))
                    self.assertEqual(
                        evidence.reason_codes, (f"INVALID_{field.upper()}",)
                    )
                    self.assertFalse(evidence.usable)

    def test_reasons_have_deterministic_order(self) -> None:
        evidence = evaluate_structure(
            snapshot(fresh=False, last=None, bar_close=math.nan)
        )

        self.assertEqual(
            evidence.reason_codes,
            ("STALE_SNAPSHOT", "MISSING_LAST", "INVALID_BAR_CLOSE"),
        )

    def test_unrelated_quote_fields_do_not_change_structure(self) -> None:
        expected = evaluate_structure(snapshot())

        self.assertEqual(
            evaluate_structure(snapshot(bid=None, ask=None)), expected
        )

    def test_snapshot_is_not_mutated(self) -> None:
        original = snapshot()
        before = deepcopy(original)

        evaluate_structure(original)

        self.assertEqual(original, before)

    def test_surface_is_descriptive_only(self) -> None:
        forbidden = (
            "SetupState",
            "direction",
            "probability",
            "score",
            "target",
            "stop",
            "pnl",
            "write_cycle",
            "ledger",
            "resolver",
            "status",
            "broker",
            "execute",
        )
        for name in forbidden:
            self.assertFalse(hasattr(structure, name), name)

        self.assertEqual(
            tuple(StructureEvidence.__dataclass_fields__),
            ("usable", "displacement_pct", "relation", "reason_codes"),
        )


if __name__ == "__main__":
    unittest.main()
