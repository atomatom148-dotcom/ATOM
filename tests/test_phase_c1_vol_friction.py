"""Phase C1 proofs for descriptive volatility/friction evidence."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.models import Snapshot
import quant.vol_friction as vol_friction
from quant.vol_friction import VolFrictionEvidence, evaluate_vol_friction


def snapshot(**overrides: object) -> Snapshot:
    values = {
        "symbol": "COIN",
        "asof_epoch": 1_700_000_000.0,
        "last": 100.0,
        "bid": 99.0,
        "ask": 101.0,
        "bar_close": 96.0,
        "source": "test",
        "fresh": True,
        "reason_codes": ["SOURCE_EVIDENCE"],
    }
    values.update(overrides)
    return Snapshot(**values)


class PhaseC1VolFrictionTests(unittest.TestCase):
    def test_computes_spread_range_and_net_range(self) -> None:
        evidence = evaluate_vol_friction(snapshot())

        self.assertEqual(
            evidence,
            VolFrictionEvidence(
                usable=True,
                range_pct=0.04,
                spread_pct=0.02,
                net_range_pct=0.02,
                reason_codes=(),
            ),
        )

    def test_net_range_has_zero_floor_and_zero_spread_is_valid(self) -> None:
        below_spread = evaluate_vol_friction(snapshot(bar_close=99.5))
        zero_spread = evaluate_vol_friction(snapshot(bid=100.0, ask=100.0))

        self.assertEqual(below_spread.net_range_pct, 0.0)
        self.assertTrue(zero_spread.usable)
        self.assertEqual(zero_spread.spread_pct, 0.0)
        self.assertEqual(zero_spread.net_range_pct, zero_spread.range_pct)

    def test_missing_range_remains_missing_but_spread_is_usable(self) -> None:
        for value in (None, 0.0, -1.0, math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value):
                evidence = evaluate_vol_friction(snapshot(bar_close=value))
                self.assertTrue(evidence.usable)
                self.assertEqual(evidence.spread_pct, 0.02)
                self.assertIsNone(evidence.range_pct)
                self.assertIsNone(evidence.net_range_pct)
                self.assertEqual(evidence.reason_codes, ("RANGE_UNAVAILABLE",))

    def test_all_required_evidence_is_validated_in_deterministic_order(self) -> None:
        evidence = evaluate_vol_friction(
            snapshot(fresh=False, last=None, bid=math.nan, ask=-1.0)
        )

        self.assertEqual(
            evidence,
            VolFrictionEvidence(
                usable=False,
                range_pct=None,
                spread_pct=None,
                net_range_pct=None,
                reason_codes=(
                    "STALE_SNAPSHOT",
                    "MISSING_LAST",
                    "INVALID_BID",
                    "INVALID_ASK",
                ),
            ),
        )

    def test_each_missing_or_invalid_required_value_is_unusable(self) -> None:
        for field, code in (
            ("last", "MISSING_LAST"),
            ("bid", "MISSING_BID"),
            ("ask", "MISSING_ASK"),
        ):
            with self.subTest(field=field, kind="missing"):
                evidence = evaluate_vol_friction(snapshot(**{field: None}))
                self.assertFalse(evidence.usable)
                self.assertEqual(evidence.reason_codes, (code,))
                self.assertIsNone(evidence.spread_pct)
                self.assertIsNone(evidence.range_pct)
                self.assertIsNone(evidence.net_range_pct)

            for value in (0.0, -1.0, math.nan, math.inf, -math.inf, True):
                with self.subTest(field=field, value=value):
                    evidence = evaluate_vol_friction(snapshot(**{field: value}))
                    self.assertFalse(evidence.usable)
                    self.assertEqual(evidence.reason_codes, (f"INVALID_{field.upper()}",))

    def test_stale_and_reversed_quote_are_unusable(self) -> None:
        stale = evaluate_vol_friction(snapshot(fresh=False))
        reversed_quote = evaluate_vol_friction(snapshot(bid=101.0, ask=100.0))

        self.assertEqual(stale.reason_codes, ("STALE_SNAPSHOT",))
        self.assertEqual(reversed_quote.reason_codes, ("ASK_BELOW_BID",))
        self.assertFalse(stale.usable)
        self.assertFalse(reversed_quote.usable)

    def test_snapshot_is_not_mutated(self) -> None:
        original = snapshot()
        before = deepcopy(original)

        evaluate_vol_friction(original)

        self.assertEqual(original, before)

    def test_forbidden_predictive_and_operational_surfaces_are_absent(self) -> None:
        forbidden = (
            "VolFrictionPolicy",
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
            self.assertFalse(hasattr(vol_friction, name), name)

        fields = VolFrictionEvidence.__dataclass_fields__
        self.assertEqual(
            tuple(fields),
            ("usable", "range_pct", "spread_pct", "net_range_pct", "reason_codes"),
        )


if __name__ == "__main__":
    unittest.main()
