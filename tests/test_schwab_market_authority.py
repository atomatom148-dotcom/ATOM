"""Static authority proofs for the frozen Schwab S1 market-data boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
QUANT = ROOT / "quant"
BUS = QUANT / "schwab_market_bus.py"
WORKER = QUANT / "schwab_market_worker.py"
S1_MODULES = (BUS, WORKER)
S2_PROOF = ROOT / "schwab_s2_live_proof.py"
SCHWAB_BOUNDARY_MODULES = (*S1_MODULES, S2_PROOF)

EXPECTED_QUANT_EXPORTS = (
    "HORIZONS",
    "ExactSixBundle",
    "HorizonForecast",
    "SetupState",
    "Snapshot",
)


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(tree: ast.AST) -> set[str]:
    values = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    values.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    return values


def _call_name(node: ast.Call) -> str:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one {name} function")
    return matches[0]


class SchwabMarketAuthorityTests(unittest.TestCase):
    def test_s1_modules_have_no_live_quant_ui_evidence_or_broker_imports(self) -> None:
        forbidden_quant_modules = {
            "live_market",
            "web",
            "ledger",
            "resolver",
            "evidence",
            "evidence_outbox",
            "historical_evidence",
            "historical_replay",
            "q1_momentum",
            "q2_mean_reversion",
            "q3_volatility",
            "q4_stat_arb",
            "q5_microstructure",
            "q6_volume_liquidity",
            "q7_relative_value",
            "q8_cross_asset",
            "q9_factor",
            "q10_options_vol",
            "q11_regime",
            "q12_event_session",
        }
        forbidden_import_roots = {
            "alpaca",
            "ccxt",
            "ib_insync",
            "psycopg",
            "redis",
            "schwab",
            "sqlalchemy",
        }
        forbidden_calls = {
            "__import__",
            "eval",
            "exec",
            "compile",
            "accept_g2_price",
            "accept_quote",
            "append_forecast",
            "commit_forecast",
            "resolve",
            "place_order",
            "submit_order",
            "cancel_order",
            "replace_order",
            "get_account",
            "get_accounts",
            "get_positions",
            "get_transactions",
            "get_orders",
        }

        for path in SCHWAB_BOUNDARY_MODULES:
            with self.subTest(module=path.name):
                tree = _tree(path)
                imports = _imports(tree)
                import_parts = {
                    part
                    for imported in imports
                    for part in imported.lower().split(".")
                }
                self.assertTrue(forbidden_quant_modules.isdisjoint(import_parts))
                self.assertTrue(forbidden_import_roots.isdisjoint(import_parts))
                self.assertNotIn("importlib", import_parts)

                calls = {
                    _call_name(node).lower()
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                }
                self.assertTrue(forbidden_calls.isdisjoint(calls))

                for imported in imports:
                    lowered = imported.lower()
                    self.assertNotRegex(lowered, r"(^|\.)v9_v[234]($|_)")

    def test_s2_proof_is_one_shot_transient_and_has_no_storage_surface(self) -> None:
        tree = _tree(S2_PROOF)
        imports = _imports(tree)
        import_parts = {
            part
            for imported in imports
            for part in imported.lower().split(".")
        }
        self.assertTrue(
            {
                "pathlib",
                "psycopg",
                "redis",
                "sqlite3",
                "supabase",
            }.isdisjoint(import_parts)
        )
        calls = {
            _call_name(node).lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        self.assertTrue(
            {
                "open",
                "write",
                "write_bytes",
                "write_text",
                "append_forecast",
                "commit_forecast",
                "resolve",
            }.isdisjoint(calls)
        )
        assignments = {
            node.targets[0].id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        }
        self.assertEqual(assignments.get("MAX_PROOF_SECONDS"), 45.0)
        strings = {
            node.value.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertFalse(any("render" in value for value in strings))
        self.assertFalse(any("supabase" in value for value in strings))
        self.assertFalse(any("q5" in value for value in strings))

    def test_no_existing_quant_module_consumes_schwab_s1(self) -> None:
        for path in sorted(QUANT.glob("*.py")):
            if path in S1_MODULES:
                continue
            with self.subTest(module=path.name):
                tree = _tree(path)
                imports = _imports(tree)
                self.assertFalse(
                    any(
                        imported.endswith(("schwab_market_bus", "schwab_market_worker"))
                        for imported in imports
                    )
                )
                strings = {
                    node.value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                self.assertFalse(
                    any("atom:v9:schwab:" in value for value in strings)
                )

        init_tree = _tree(QUANT / "__init__.py")
        exports = None
        for node in init_tree.body:
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__all__"
                        for target in node.targets)
            ):
                exports = tuple(ast.literal_eval(node.value))
        self.assertEqual(exports, EXPECTED_QUANT_EXPORTS)

    def test_only_frozen_network_surfaces_are_reachable(self) -> None:
        tree = _tree(WORKER)
        assignments: dict[str, object] = {}
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
            ):
                assignments[node.targets[0].id] = node.value.value
        self.assertEqual(
            assignments.get("SCHWAB_TOKEN_URL"),
            "https://api.schwabapi.com/v1/oauth/token",
        )
        self.assertEqual(
            assignments.get("SCHWAB_NDX_QUOTES_URL"),
            "https://api.schwabapi.com/marketdata/v1/quotes",
        )
        self.assertEqual(
            assignments.get("SCHWAB_USER_PREFERENCE_URL"),
            "https://api.schwabapi.com/trader/v1/userPreference",
        )
        self.assertEqual(
            assignments.get("SCHWAB_STREAMER_URL"),
            "wss://streamer-api.schwab.com/ws",
        )

        transport_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "request"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "_http"
        ]
        self.assertEqual(len(transport_calls), 2)
        request_shapes = {
            (
                ast.literal_eval(call.args[0]),
                call.args[1].id if isinstance(call.args[1], ast.Name) else "",
            )
            for call in transport_calls
        }
        self.assertEqual(
            request_shapes,
            {("POST", "SCHWAB_TOKEN_URL"), ("GET", "url")},
        )

        authorized_get = _function(tree, "_authorized_get")
        ndx_guards = [
            node
            for node in ast.walk(authorized_get)
            if isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "url"
            and any(isinstance(operator, ast.NotEq) for operator in node.ops)
            and any(
                isinstance(comparator, ast.Name)
                and comparator.id == "SCHWAB_NDX_QUOTES_URL"
                for comparator in node.comparators
            )
        ]
        self.assertTrue(ndx_guards)

        authorized_response = _function(tree, "_authorized_response")
        allowlists = [
            {
                element.id
                for element in comparator.elts
                if isinstance(element, ast.Name)
            }
            for node in ast.walk(authorized_response)
            if isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "url"
            and any(isinstance(operator, ast.NotIn) for operator in node.ops)
            for comparator in node.comparators
            if isinstance(comparator, ast.Set)
        ]
        self.assertIn(
            {"SCHWAB_NDX_QUOTES_URL", "SCHWAB_USER_PREFERENCE_URL"},
            allowlists,
        )

        websocket_factory = _function(tree, "_default_websocket_factory")
        redirect_limits = [
            keyword.value.value
            for node in ast.walk(websocket_factory)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "redirect_limit"
            and isinstance(keyword.value, ast.Constant)
        ]
        self.assertEqual(redirect_limits, [0])

        string_literals = {
            node.value.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        forbidden_route_terms = (
            "/accounts",
            "/balances",
            "/positions",
            "/transactions",
            "/orders",
            "/cancel",
            "/replace",
            "/execution",
        )
        for value in string_literals:
            self.assertFalse(
                any(term in value for term in forbidden_route_terms),
                value,
            )

        public_functions = {
            node.name.lower()
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        }
        for name in public_functions:
            self.assertNotRegex(
                name,
                r"account|balance|position|transaction|order|cancel|replace|execut|trade",
            )

    def test_s1_publications_are_observer_only(self) -> None:
        from quant.schwab_market_bus import BookLevel, BookSnapshot, NDXSnapshot

        allowed_fields = {
            "symbol",
            "price",
            "size",
            "count",
            "bids",
            "asks",
            "provider_epoch",
            "quote_time_epoch",
            "received_at_epoch",
            "source_sequence",
            "trade_time_epoch",
        }
        forbidden_fields = {
            "direction",
            "forecast",
            "imbalance",
            "microprice",
            "outcome",
            "prediction",
            "probability",
            "q5",
            "score",
            "signal",
            "truth",
            "weight",
        }

        for value_type in (NDXSnapshot, BookLevel, BookSnapshot):
            with self.subTest(value_type=value_type.__name__):
                fields = set(value_type.__dataclass_fields__)
                self.assertLessEqual(fields, allowed_fields)
                self.assertTrue(fields.isdisjoint(forbidden_fields))

        self.assertEqual(
            tuple(BookLevel.__dataclass_fields__),
            ("price", "size", "count"),
        )


if __name__ == "__main__":
    unittest.main()
