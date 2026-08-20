import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from quant.v9_math_core import V9MathCore, V9MathInput, V9MathState


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "quant" / "v9_math_core.py"


class V9MathCoreTests(unittest.TestCase):
    def test_contract_is_immutable_and_deterministic(self) -> None:
        value = V9MathInput(symbol="COIN", as_of_epoch=1_725_000_000.25)

        first = V9MathCore.evaluate(value)
        second = V9MathCore.evaluate(value)

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            V9MathState(
                symbol="COIN",
                as_of_epoch=1_725_000_000.25,
                status="EMPTY",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            value.symbol = "CHANGED"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            first.status = "CHANGED"  # type: ignore[misc]

    def test_values_are_preserved_exactly(self) -> None:
        value = V9MathInput(symbol=" coin/Usd ", as_of_epoch=-0.0)

        state = V9MathCore.evaluate(value)

        self.assertEqual(state.symbol, value.symbol)
        self.assertEqual(state.as_of_epoch, value.as_of_epoch)
        self.assertEqual(state.status, "EMPTY")

    def test_nonfinite_epochs_are_rejected(self) -> None:
        for epoch in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(epoch=epoch):
                with self.assertRaisesRegex(ValueError, "as_of_epoch must be finite"):
                    V9MathInput(symbol="COIN", as_of_epoch=epoch)

    def test_module_has_only_standard_library_imports(self) -> None:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        imports = {
            node.module if isinstance(node, ast.ImportFrom) else alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in ([node.names[0]] if isinstance(node, ast.Import) else [None])
        }
        self.assertEqual(imports, {"dataclasses", "math"})

    def test_production_runtime_does_not_import_boundary(self) -> None:
        importers = []
        for path in ROOT.rglob("*.py"):
            if path == MODULE or "tests" in path.parts:
                continue
            if "v9_math_core" in path.read_text(encoding="utf-8"):
                importers.append(path.relative_to(ROOT))
        self.assertEqual(importers, [])


if __name__ == "__main__":
    unittest.main()
