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
        "bid": 100.0,
        "ask": 104.0,
        "bar_close": 96.0,
        "source": "test",
        "fresh": True,
        "reason_codes": ["SOURCE_EVIDENCE"],
    }
    values.update(overrides)
    return Snapshot(**values)


class PhaseC2StructureTests(unittest.TestCase):
    def test_exact_valid_calculations(self) -> None:
        evidence = evaluate_structure(snapshot(last=102.0, bid=100.0, ask=106.0))

        self.assertEqual(evidence.midpoint, 103.0)
        self.assertEqual(evidence.distance_from_close_pct, 6.0 / 102.0)
        self.assertEqual(evidence.distance_from_mid_pct, -1.0 / 102.0)
        self.assertEqual(evidence.location_in_quote, 2.0 / 6.0)
        self.assertEqual(evidence.reason_codes, ())
        self.assertTrue(evidence.usable)

    def test_location_outside_quote_is_not_clamped(self) -> None:
        above = evaluate_structure(snapshot(last=106.0, bid=100.0, ask=104.0))
        below = evaluate_structure(snapshot(last=98.0, bid=100.0, ask=104.0))

        self.assertEqual(above.location_in_quote, 1.5)
        self.assertEqual(below.location_in_quote, -0.5)

    def test_zero_width_quote_remains_usable(self) -> None:
        evidence = evaluate_structure(snapshot(last=102.0, bid=101.0, ask=101.0))

        self.assertTrue(evidence.usable)
        self.assertEqual(evidence.midpoint, 101.0)
        self.assertEqual(evidence.distance_from_mid_pct, 1.0 / 102.0)
        self.assertIsNone(evidence.location_in_quote)
        self.assertEqual(evidence.reason_codes, ("ZERO_QUOTE_WIDTH",))

    def test_missing_or_invalid_close_is_optional(self) -> None:
        for value in (None, 0.0, -1.0, math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value):
                evidence = evaluate_structure(snapshot(bar_close=value))
                self.assertTrue(evidence.usable)
                self.assertIsNone(evidence.distance_from_close_pct)
                self.assertEqual(evidence.midpoint, 102.0)
                self.assertEqual(evidence.distance_from_mid_pct, 0.0)
                self.assertEqual(evidence.location_in_quote, 0.5)
                self.assertEqual(evidence.reason_codes, ("CLOSE_UNAVAILABLE",))

    def test_required_quote_validation(self) -> None:
        for field in ("last", "bid", "ask"):
            with self.subTest(field=field, kind="missing"):
                evidence = evaluate_structure(snapshot(**{field: None}))
                self._assert_unusable(evidence, (f"MISSING_{field.upper()}",))

            for value in (0.0, -1.0, math.nan, math.inf, -math.inf, True):
                with self.subTest(field=field, value=value):
                    evidence = evaluate_structure(snapshot(**{field: value}))
                    self._assert_unusable(
                        evidence, (f"INVALID_{field.upper()}",)
                    )

    def test_stale_and_reversed_quotes_are_unusable(self) -> None:
        self._assert_unusable(
            evaluate_structure(snapshot(fresh=False)), ("STALE_SNAPSHOT",)
        )
        self._assert_unusable(
            evaluate_structure(snapshot(bid=105.0, ask=104.0)),
            ("ASK_BELOW_BID",),
        )

    def test_required_reasons_have_deterministic_order(self) -> None:
        evidence = evaluate_structure(
            snapshot(fresh=False, last=None, bid=math.nan, ask=-1.0)
        )

        self._assert_unusable(
            evidence,
            ("STALE_SNAPSHOT", "MISSING_LAST", "INVALID_BID", "INVALID_ASK"),
        )

    def test_snapshot_is_not_mutated(self) -> None:
        original = snapshot()
        before = deepcopy(original)
        evaluate_structure(original)
        self.assertEqual(original, before)

    def test_forbidden_surfaces_and_categories_are_absent(self) -> None:
        forbidden = (
            "SetupState", "direction", "probability", "score", "support",
            "resistance", "breakout", "target", "stop", "pnl", "write_cycle",
            "ledger", "resolver", "status", "broker", "execute", "relation",
            "displacement_pct", "ABOVE_BAR_CLOSE", "BELOW_BAR_CLOSE",
            "AT_BAR_CLOSE",
        )
        for name in forbidden:
            self.assertFalse(hasattr(structure, name), name)

        self.assertEqual(
            tuple(StructureEvidence.__dataclass_fields__),
            (
                "usable", "distance_from_close_pct", "midpoint",
                "distance_from_mid_pct", "location_in_quote", "reason_codes",
            ),
        )

    def _assert_unusable(
        self, evidence: StructureEvidence, reasons: tuple[str, ...]
    ) -> None:
        self.assertFalse(evidence.usable)
        self.assertIsNone(evidence.distance_from_close_pct)
        self.assertIsNone(evidence.midpoint)
        self.assertIsNone(evidence.distance_from_mid_pct)
        self.assertIsNone(evidence.location_in_quote)
        self.assertEqual(evidence.reason_codes, reasons)


if __name__ == "__main__":
    unittest.main()
