from dataclasses import FrozenInstanceError
import os
import unittest
from unittest.mock import Mock, patch

from quant.live_market import (
    LiveMarketState,
    build_v9_quant_snapshot,
    v9_math_core_enabled,
)
from quant.models import HORIZONS
from quant.v9_math_core import V9MathCore, V9QuantFamily


class Result:
    def __init__(self, quant_id, formula_version, values, *, volatility=False):
        self.quant_id = quant_id
        self.formula_version = formula_version
        if volatility:
            self.volatility_bps = values
        else:
            self.forecast_bps = values


class V9QuantSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.values = [1.0, None, 3.0, 4.0, 5.0, 6.0]
        names = (
            "momentum", "mean_reversion", "volatility", "stat_arb",
            "microstructure", "volume_liquidity", "relative_value",
            "cross_asset", "factor", "options_vol", "regime", "event_session",
        )
        self.source_results = [
            Result(f"q{index}_{name}", f"formula-{index}", self.values,
                   volatility=index == 3)
            for index, name in enumerate(names, 1)
        ]
        self.live_snapshot = Mock(**dict(zip(names, self.source_results)))

    def test_gate_defaults_false_and_only_true_enables(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(v9_math_core_enabled())
        for value in ("true", "TRUE", "True"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"V9_MATH_CORE_ENABLED": value}, clear=True
            ):
                self.assertTrue(v9_math_core_enabled())

    def test_snapshot_contract_copies_all_current_families(self) -> None:
        snapshot = build_v9_quant_snapshot(
            self.live_snapshot, symbol="COIN", as_of_epoch=123.25,
        )

        self.assertEqual(snapshot.symbol, "COIN")
        self.assertEqual(snapshot.as_of_epoch, 123.25)
        self.assertEqual(tuple(range(1, 13)), tuple(
            int(family.quant_id.split("_")[0][1:]) for family in snapshot.families
        ))
        self.assertEqual(
            tuple(f"formula-{index}" for index in range(1, 13)),
            tuple(family.formula_version for family in snapshot.families),
        )
        self.assertEqual(HORIZONS, ("30S", "1M", "5M", "15M", "30M", "1H"))
        self.assertTrue(all(family.horizon_values == tuple(self.values)
                            for family in snapshot.families))
        self.assertIsNone(snapshot.families[0].horizon_values[1])
        self.assertEqual(sum(len(item.horizon_values) for item in snapshot.families), 72)
        self.assertEqual(V9MathCore.evaluate(snapshot).status, "OBSERVING")

        self.values[0] = 999.0
        self.assertEqual(snapshot.families[0].horizon_values[0], 1.0)
        with self.assertRaises(FrozenInstanceError):
            snapshot.symbol = "CHANGED"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            snapshot.families[0].quant_id = "changed"  # type: ignore[misc]

    def test_missing_result_is_omitted_without_fabrication(self) -> None:
        self.live_snapshot.regime = None
        snapshot = build_v9_quant_snapshot(
            self.live_snapshot, symbol="COIN", as_of_epoch=123.25,
        )
        self.assertEqual(len(snapshot.families), 11)
        self.assertNotIn("q11_regime", {item.quant_id for item in snapshot.families})

    def test_family_collection_is_not_fixed_to_twelve(self) -> None:
        snapshot = build_v9_quant_snapshot(
            self.live_snapshot, symbol="COIN", as_of_epoch=123.25,
        )
        extended = snapshot.families + (
            V9QuantFamily("future", "v1", (None,) * 6),
        )
        self.assertEqual(len(extended), 13)

    @patch("quant.live_market.build_v9_quant_snapshot")
    @patch("quant.live_market.V9MathCore.evaluate")
    def test_disabled_does_no_v9_work(self, evaluate, build) -> None:
        with patch.dict(os.environ, {}, clear=True):
            state = LiveMarketState(clock=lambda: 10.0)
            self.assertTrue(state.accept_quote(bid=99.0, ask=101.0, event_epoch=1.0))
        build.assert_not_called()
        evaluate.assert_not_called()
        self.assertEqual(state.snapshot().momentum.quant_id, "q1_momentum")

    @patch("quant.live_market.V9MathCore.evaluate", side_effect=RuntimeError("v9 failed"))
    def test_v9_failure_is_fail_open_and_evidence_continues(self, evaluate) -> None:
        evidence = Mock()
        with patch.dict(os.environ, {"V9_MATH_CORE_ENABLED": "true"}, clear=True):
            state = LiveMarketState(clock=lambda: 10.0, evidence_outbox=evidence)
            self.assertTrue(state.accept_quote(bid=99.0, ask=101.0, event_epoch=1.0))
        evaluate.assert_called_once()
        evidence.put_nowait.assert_called_once()
        self.assertEqual(state.snapshot().momentum.quant_id, "q1_momentum")

    @patch("quant.live_market.build_v9_quant_snapshot",
           side_effect=RuntimeError("snapshot failed"))
    def test_snapshot_failure_is_fail_open_and_evidence_continues(self, build) -> None:
        evidence = Mock()
        with patch.dict(os.environ, {"V9_MATH_CORE_ENABLED": "true"}, clear=True):
            state = LiveMarketState(clock=lambda: 10.0, evidence_outbox=evidence)
            self.assertTrue(state.accept_quote(bid=99.0, ask=101.0, event_epoch=1.0))
        build.assert_called_once()
        evidence.put_nowait.assert_called_once()
        self.assertEqual(state.snapshot().momentum.quant_id, "q1_momentum")


if __name__ == "__main__":
    unittest.main()
