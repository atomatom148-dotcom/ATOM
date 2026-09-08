"""Contract tests for the readiness-only Render Workflow."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "workflows" / "main.py"


class _Workflows:
    """Narrow SDK shim used only to test registration mechanics."""

    instances: list[_Workflows] = []

    def __init__(self) -> None:
        self.tasks: list[object] = []
        self.start = Mock()
        self.instances.append(self)

    def task(self, function: object) -> object:
        self.tasks.append(function)
        return function


class _TaskContext:
    pass


def _import_with_sdk_shim(monkeypatch):
    sdk = ModuleType("render_sdk")
    sdk.TaskContext = _TaskContext
    sdk.Workflows = _Workflows
    monkeypatch.setitem(sys.modules, "render_sdk", sdk)
    sys.modules.pop("workflows.main", None)
    _Workflows.instances.clear()
    return importlib.import_module("workflows.main")


def test_import_registers_only_readiness_smoke_without_startup(monkeypatch) -> None:
    module = _import_with_sdk_shim(monkeypatch)

    assert len(_Workflows.instances) == 1
    assert _Workflows.instances[0] is module.app
    assert [task.__name__ for task in module.app.tasks] == ["readiness_smoke"]
    module.app.start.assert_not_called()


def test_readiness_smoke_has_exact_signature_and_result(monkeypatch) -> None:
    module = _import_with_sdk_shim(monkeypatch)

    signature = inspect.signature(module.readiness_smoke)
    assert list(signature.parameters) == ["context", "check_id", "metadata"]
    assert signature.parameters["context"].annotation is _TaskContext
    assert signature.parameters["check_id"].annotation is str
    assert signature.parameters["metadata"].annotation is str
    assert signature.parameters["metadata"].default == ""

    expected = {"check_id": "check-1", "metadata": "", "status": "ready"}
    assert module.readiness_smoke(_TaskContext(), "check-1") == expected
    assert module.readiness_smoke(_TaskContext(), "check-1") == expected


def test_module_uses_only_sdk_import_and_guarded_startup() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert len(imports) == 1
    assert isinstance(imports[0], ast.ImportFrom)
    assert imports[0].module == "render_sdk"
    assert [alias.name for alias in imports[0].names] == ["TaskContext", "Workflows"]

    start_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "start"
    ]
    assert len(start_calls) == 1
    guard = tree.body[-1]
    assert isinstance(guard, ast.If)
    assert start_calls[0] in list(ast.walk(guard))


def test_dependency_is_isolated_and_exact() -> None:
    assert (ROOT / "workflows" / "requirements.txt").read_text(encoding="utf-8") == (
        "render>=1.0.1\n"
    )
