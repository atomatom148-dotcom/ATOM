import ast
import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "quant" / "historical_batch_h2d.py"
ROOT_FREEZE = ROOT / "FREEZE.md"
PHASES = ROOT / "PHASES.md"
FREEZE = ROOT / "docs" / "h2-d2-freeze.md"
BASELINES = ROOT / "docs" / "h2-d2-canary-baselines.json"
Q10_AUDIT = ROOT / "docs" / "audits" / "h2d-2026-07-22-q10-options-vol.md"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
BASELINE_BUNDLE_SHA256 = "b24e42145bc0020edfadbb0f989ebc25f1edcfc80876454fa79ae7ce88f42ab6"
SEQUENTIAL_RUNTIME_SOURCE_SHA256 = {
    "quant/historical_batch_h2d.py":
        "a4c9b42829b463c3d919caceea7e0252ad7062bae0d713120c17eeb7ee529683",
    "quant/historical_replay_h1.py":
        "0b8958d704973f031096fd541d2306b6d751c81f136470ff08d074874ae0cb10",
    "quant/historical_evidence_verifier.py":
        "75bc9690b45b7b6e1278a88c587de3593436cb1ef6f9d5796872cdbf828c9709",
    "quant/historical_outcomes.py":
        "89397df5816d9f2a8909d5912ffb9b6820be9341a961222e666c59f7684b6797",
}


def canonical_source_sha256(source: str) -> str:
    normalized = source.rstrip("\n") + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class H2D2FreezeContractTests(unittest.TestCase):
    def test_baselines_are_two_read_only_certified_complete_sessions(self):
        payload = json.loads(BASELINES.read_text(encoding="utf-8"))
        canonical_bundle = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(canonical_bundle).hexdigest(),
            BASELINE_BUNDLE_SHA256,
        )
        self.assertEqual(payload["freeze_version"], "H2-D-2")
        self.assertEqual(payload["current_runtime_version"], "H2-D-1")
        self.assertEqual(payload["capture_mode"], "read_only")
        self.assertFalse(payload["parallel_runtime_enabled"])
        self.assertEqual(payload["future_canary_worker_limit"], 2)
        self.assertEqual(
            payload["sequential_runtime_source_hash_contract"],
            {
                "algorithm": "sha256_utf8_source_v1",
                "terminal_lf_normalization":
                    "strip_all_then_append_one_lf",
            },
        )
        self.assertEqual(
            payload["sequential_runtime_source_sha256"],
            SEQUENTIAL_RUNTIME_SOURCE_SHA256,
        )
        self.assertEqual(
            payload["ordered_content_hash_contract"],
            {
                "algorithm": "sha256_utf8_newline_join_v1",
                "row_value": "stored lowercase content_sha256",
                "separator": "\n",
                "trailing_separator": False,
                "forecast_order": ["cutoff_at", "quant_id", "horizon"],
                "outcome_order": ["cutoff_at", "horizon"],
            },
        )
        self.assertEqual(
            payload["metric_hash_contract"],
            {
                "algorithm": "sha256_utf8_metric_array_v1",
                "quant_order": [
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
                ],
                "horizon_order": ["30S", "1M", "5M", "15M", "30M", "1H"],
                "field_order": [
                    "quant_id",
                    "horizon",
                    "eligible_count",
                    "resolved_count",
                    "directional_wins",
                    "directional_losses",
                    "directional_accuracy",
                    "rmse",
                    "mae",
                    "bias",
                    "coverage",
                ],
                "integer_fields": ["eligible_count", "resolved_count"],
                "nullable_integer_fields": [
                    "directional_wins",
                    "directional_losses",
                ],
                "nullable_float_fields": [
                    "directional_accuracy",
                    "rmse",
                    "mae",
                    "bias",
                ],
                "required_float_fields": ["coverage"],
                "float_encoding":
                    "finite_ieee754_binary64_python_float_hex_string",
                "null_encoding": "json_null",
                "json_encoding": {
                    "ensure_ascii": False,
                    "allow_nan": False,
                    "sort_keys": False,
                    "item_separator": ",",
                    "key_separator": ":",
                    "trailing_newline": False,
                },
                "digest_encoding": "lowercase_hex",
            },
        )
        sessions = payload["sessions"]
        self.assertEqual(
            [row["historical_session"] for row in sessions],
            ["2026-06-15", "2026-07-22"],
        )
        self.assertEqual(len({row["historical_session"] for row in sessions}), 2)
        self.assertEqual(len({row["replay_run_id"] for row in sessions}), 2)
        self.assertEqual(
            {
                row["historical_session"]: {
                    key: row[key]
                    for key in (
                        "replay_run_id",
                        "git_commit",
                        "dataset_digest",
                        "configuration_digest",
                        "session_digest",
                        "artifact_sha256",
                        "manifest_content_sha256",
                        "forecast_ordered_content_sha256",
                        "outcome_ordered_content_sha256",
                    )
                }
                for row in sessions
            },
            {
                "2026-06-15": {
                    "replay_run_id": "h2a-2026-06-15-persistence-v3",
                    "git_commit": "a9cc73ddd892c3518bda1145075cbd4de6873513",
                    "dataset_digest":
                        "c1dda6101424404b94ad39973f4c6a4a0feb67e90b537bae7f94a264130e6b3e",
                    "configuration_digest":
                        "dcd7f3af8fba60047ff965a22fc9dbf5f05734f97913c502f3d972f21cf46385",
                    "session_digest":
                        "e35a1130ae7f6e12ea4783aebd7a988e7dcff0f659a179566193e62368e23627",
                    "artifact_sha256":
                        "1edb32a8f46a757637459dcfa348480df0968a6531f8590c3c784d0d4e9a9860",
                    "manifest_content_sha256":
                        "a9f5a0d1621a8e682ede3ff0d12c70cff7da79c474e008df9aa2d17652028a8d",
                    "forecast_ordered_content_sha256":
                        "0417bed3adde008e26db5693e34e04a10633176595ecb61fa573bd6bc9c2473d",
                    "outcome_ordered_content_sha256":
                        "e1f14e02922a2c58faea0447796fe33ba6950ca44659c72fc39f62babaefa1a9",
                },
                "2026-07-22": {
                    "replay_run_id": "h2d-2026-07-22",
                    "git_commit": "fa3438f9444b624b973e7a3dc5efe89fea2dc6ca",
                    "dataset_digest":
                        "18a334e44983635dd4794385ee25f9497b8be865d255bafbcab28f3286c41aa9",
                    "configuration_digest":
                        "2fb3d521ddb0310458251225bf25a3e1759304d468f6bfa72ee92c6dd967a7d1",
                    "session_digest":
                        "cd687a7ab67d4f1a29c46780b37e4fb81562eb9eb28e1d43d367820299f1ab96",
                    "artifact_sha256":
                        "2145555052691e45880475198c9983e6816feba508015b14ebe23025cbe9931b",
                    "manifest_content_sha256":
                        "8f886e9c8a3b6245ddc143c31e16af081e6ace93dbafe1ecf27dd2077c5c7b0e",
                    "forecast_ordered_content_sha256":
                        "1109ee48009e4bbf758d574f1e71e81d1486b6aef47d71c38fc34b37e2f78473",
                    "outcome_ordered_content_sha256":
                        "2ff12383dd8abbf8c16942ba8713c90312fd4863e8f4be2f4b49a81e0061e531",
                },
            },
        )
        self.assertEqual(
            sessions[1]["db3_forecast_sha256"],
            "413e3bacb29155e2c03ad666a47dd6ab42759015f75f68c9ecbff7d06b1494e1",
        )
        self.assertEqual(
            sessions[1]["db3_outcome_sha256"],
            "d3a820111a3a8a9f68a02f738fcb98b8c5bebc13e20336d46e47394a9632e532",
        )
        digest_fields = (
            "dataset_digest",
            "configuration_digest",
            "session_digest",
            "artifact_sha256",
            "manifest_content_sha256",
            "forecast_ordered_content_sha256",
            "outcome_ordered_content_sha256",
        )
        for row in sessions:
            with self.subTest(session=row["historical_session"]):
                self.assertEqual(row["execution_stage"], "REPLAY_COMPLETE")
                self.assertEqual(row["certification_status"], "CERTIFIED")
                self.assertRegex(row["git_commit"], HEX_40)
                for field in digest_fields:
                    self.assertRegex(row[field], HEX_64)
                for field, value in row.items():
                    if field.endswith("_sha256"):
                        self.assertRegex(value, HEX_64)
                self.assertEqual(row["forecast_count"], row["frame_count"] * 72)
                self.assertEqual(row["outcome_count"], row["frame_count"] * 6)
                self.assertEqual(
                    row["forecast_available_count"] + row["forecast_unavailable_count"],
                    row["forecast_count"],
                )
                self.assertEqual(
                    row["outcome_available_count"] + row["outcome_unavailable_count"],
                    row["outcome_count"],
                )
                self.assertGreater(row["h1_total_seconds"], 0)

    def test_runtime_stays_h2d1_sequential_with_no_parallel_activation_seam(self):
        source = BATCH.read_text(encoding="utf-8")
        self.assertEqual(
            canonical_source_sha256(source),
            SEQUENTIAL_RUNTIME_SOURCE_SHA256["quant/historical_batch_h2d.py"],
        )
        tree = ast.parse(source)
        imported = set()
        direct_imports = set()
        module_aliases = {}
        star_imports = set()
        relative_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
                    module_aliases[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative_imports.add((node.level, node.module))
                if node.module:
                    imported.add(node.module)
                    direct_imports.update(
                        (node.module, alias.name) for alias in node.names
                    )
                if any(alias.name == "*" for alias in node.names):
                    star_imports.add(node.module or ".")
        self.assertEqual(
            imported,
            {
                "__future__",
                "argparse",
                "datetime",
                "hashlib",
                "json",
                "os",
                "psycopg",
                "resource",
                "subprocess",
                "sys",
                "time",
                "typing",
            },
        )
        self.assertFalse(star_imports, f"star imports are forbidden: {star_imports}")
        self.assertFalse(
            relative_imports,
            f"relative imports are forbidden: {relative_imports}",
        )
        direct_process_imports = {
            item for item in direct_imports
            if item[0] in {"os", "subprocess", "sys"}
        }
        self.assertFalse(
            direct_process_imports,
            f"direct OS/process imports are forbidden: {direct_process_imports}",
        )
        qualified_references = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                module_name = module_aliases.get(node.value.id)
                if module_name:
                    qualified_references.add((module_name, node.attr))
        allowed_process_references = {
            ("os", "environ"),
            ("subprocess", "run"),
            ("sys", "executable"),
        }
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        bare_process_module_loads = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and module_aliases.get(node.id) in {"os", "subprocess", "sys"}
            and not (
                isinstance(parents.get(node), ast.Attribute)
                and parents[node].value is node
                and (module_aliases[node.id], parents[node].attr)
                in allowed_process_references
            )
        )
        self.assertFalse(
            bare_process_module_loads,
            "bare OS/process module loads are forbidden",
        )
        process_references = {
            item for item in qualified_references
            if item[0] in {"os", "subprocess", "sys"}
        }
        self.assertFalse(
            process_references - allowed_process_references,
            "unexpected OS/process reference: "
            f"{process_references - allowed_process_references}",
        )
        subprocess_run_references = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and module_aliases.get(node.value.id) == "subprocess"
            and node.attr == "run"
        )
        self.assertEqual(len(subprocess_run_references), 1)
        subprocess_run_calls = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and node.func is subprocess_run_references[0]
        )
        self.assertEqual(len(subprocess_run_calls), 1)
        subprocess_run_call = subprocess_run_calls[0]
        self.assertEqual(len(subprocess_run_call.args), 1)
        self.assertIsInstance(subprocess_run_call.args[0], ast.Name)
        self.assertEqual(subprocess_run_call.args[0].id, "command")
        self.assertEqual(len(subprocess_run_call.keywords), 2)
        self.assertEqual(
            {
                keyword.arg: keyword.value.value
                for keyword in subprocess_run_call.keywords
                if isinstance(keyword.value, ast.Constant)
            },
            {"text": True, "capture_output": True},
        )
        self.assertTrue(
            all(
                keyword.arg in {"text", "capture_output"}
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in subprocess_run_call.keywords
            )
        )
        run_json_functions = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_run_json"
        )
        self.assertEqual(len(run_json_functions), 1)
        self.assertIn(subprocess_run_call, tuple(ast.walk(run_json_functions[0])))
        stage_dispatches = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_json"
        )
        self.assertEqual(len(stage_dispatches), 4)
        expected_stage_modules = {
            "H1": "quant.historical_replay_h1",
            "H2B": "quant.historical_evidence_verifier",
            "H2C_RESOLVE": "quant.historical_outcomes",
            "H2C_SCORE": "quant.historical_outcomes",
        }
        observed_stage_modules = {}
        for dispatch in stage_dispatches:
            self.assertEqual(len(dispatch.args), 2)
            self.assertFalse(dispatch.keywords)
            command, stage = dispatch.args
            self.assertIsInstance(command, ast.List)
            self.assertGreaterEqual(len(command.elts), 3)
            self.assertIsInstance(command.elts[0], ast.Name)
            self.assertEqual(command.elts[0].id, "py")
            self.assertIsInstance(command.elts[1], ast.Constant)
            self.assertEqual(command.elts[1].value, "-m")
            self.assertIsInstance(command.elts[2], ast.Constant)
            self.assertIsInstance(stage, ast.Constant)
            observed_stage_modules[stage.value] = command.elts[2].value
        self.assertEqual(observed_stage_modules, expected_stage_modules)
        dynamic_calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"__import__", "eval", "exec"}
        }
        self.assertFalse(
            dynamic_calls,
            f"dynamic import or execution is forbidden: {dynamic_calls}",
        )
        dynamic_module_access = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "vars"}
            and node.args
            and isinstance(node.args[0], ast.Name)
            and module_aliases.get(node.args[0].id) in {"os", "subprocess", "sys"}
        }
        self.assertFalse(
            dynamic_module_access,
            f"dynamic OS/process access is forbidden: {dynamic_module_access}",
        )
        async_nodes = tuple(
            node for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await),
            )
        )
        self.assertFalse(async_nodes, "async syntax is forbidden in H2-D-1")
        shell_keywords = tuple(
            keyword
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "shell"
        )
        self.assertFalse(shell_keywords, "subprocess shell mode is forbidden in H2-D-1")
        day_loops = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "day"
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "days"
        )
        self.assertEqual(len(day_loops), 1)
        string_constants = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        for forbidden_flag in ("--parallel", "--workers", "--max-workers"):
            self.assertNotIn(forbidden_flag, string_constants)
        for forbidden_call in (
            "ProcessPoolExecutor",
            "ThreadPoolExecutor",
            "asyncio.",
        ):
            self.assertNotIn(forbidden_call, source)
        self.assertIn('H2D_VERSION = "H2-D-1"', source)

    def test_every_executed_stage_module_is_frozen_and_sequential(self):
        stage_sources = {
            path: digest
            for path, digest in SEQUENTIAL_RUNTIME_SOURCE_SHA256.items()
            if path != "quant/historical_batch_h2d.py"
        }
        for relative_path, expected_digest in stage_sources.items():
            with self.subTest(stage=relative_path):
                source = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertEqual(
                    canonical_source_sha256(source),
                    expected_digest,
                )
                tree = ast.parse(source)
                imported_roots = set()
                direct_imports = set()
                module_aliases = {}
                star_imports = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imported_roots.add(alias.name.split(".")[0])
                            module_aliases[
                                alias.asname or alias.name.split(".")[0]
                            ] = alias.name
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imported_roots.add(node.module.split(".")[0])
                            direct_imports.update(
                                (node.module, alias.name)
                                for alias in node.names
                            )
                        if any(alias.name == "*" for alias in node.names):
                            star_imports.add(node.module or ".")
                self.assertFalse(
                    imported_roots.intersection({
                        "_thread",
                        "asyncio",
                        "concurrent",
                        "dask",
                        "joblib",
                        "multiprocessing",
                        "queue",
                        "ray",
                        "threading",
                    }),
                    f"parallel package imported by {relative_path}",
                )
                self.assertFalse(
                    star_imports,
                    f"star import in {relative_path}: {star_imports}",
                )
                direct_process_imports = {
                    item
                    for item in direct_imports
                    if item[0].split(".")[0] in {"os", "subprocess"}
                }
                self.assertFalse(
                    direct_process_imports,
                    f"direct process import in {relative_path}",
                )
                async_nodes = tuple(
                    node
                    for node in ast.walk(tree)
                    if isinstance(
                        node,
                        (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await),
                    )
                )
                self.assertFalse(
                    async_nodes,
                    f"async syntax in {relative_path}",
                )
                dynamic_calls = {
                    node.func.id
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"__import__", "eval", "exec"}
                }
                self.assertFalse(
                    dynamic_calls,
                    f"dynamic execution in {relative_path}: {dynamic_calls}",
                )
                allowed_references = {("os", "environ")}
                if relative_path == "quant/historical_replay_h1.py":
                    allowed_references.add(("subprocess", "run"))
                qualified_references = {
                    (module_aliases[node.value.id], node.attr)
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in module_aliases
                    and module_aliases[node.value.id] in {"os", "subprocess"}
                }
                self.assertFalse(
                    qualified_references - allowed_references,
                    f"process reference in {relative_path}: "
                    f"{qualified_references - allowed_references}",
                )
                parents = {
                    child: parent
                    for parent in ast.walk(tree)
                    for child in ast.iter_child_nodes(parent)
                }
                bare_module_loads = tuple(
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Name)
                    and isinstance(node.ctx, ast.Load)
                    and module_aliases.get(node.id) in {"os", "subprocess"}
                    and not (
                        isinstance(parents.get(node), ast.Attribute)
                        and parents[node].value is node
                        and (module_aliases[node.id], parents[node].attr)
                        in allowed_references
                    )
                )
                self.assertFalse(
                    bare_module_loads,
                    f"bare process module load in {relative_path}",
                )
                dynamic_module_access = tuple(
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"getattr", "vars"}
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and module_aliases.get(node.args[0].id)
                    in {"os", "subprocess"}
                )
                self.assertFalse(
                    dynamic_module_access,
                    f"dynamic process access in {relative_path}",
                )
                shell_keywords = tuple(
                    keyword
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    for keyword in node.keywords
                    if keyword.arg == "shell"
                )
                self.assertFalse(
                    shell_keywords,
                    f"subprocess shell mode in {relative_path}",
                )
                run_references = tuple(
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and module_aliases.get(node.value.id) == "subprocess"
                    and node.attr == "run"
                )
                expected_runs = int(
                    relative_path == "quant/historical_replay_h1.py"
                )
                self.assertEqual(len(run_references), expected_runs)
                if expected_runs:
                    run_calls = tuple(
                        node
                        for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and node.func is run_references[0]
                    )
                    self.assertEqual(len(run_calls), 1)
                    run_call = run_calls[0]
                    self.assertEqual(len(run_call.args), 1)
                    self.assertIsInstance(run_call.args[0], ast.Tuple)
                    self.assertEqual(
                        [item.value for item in run_call.args[0].elts],
                        ["git", "rev-parse", "HEAD"],
                    )
                    self.assertEqual(len(run_call.keywords), 3)
                    self.assertEqual(
                        {
                            keyword.arg: keyword.value.value
                            for keyword in run_call.keywords
                            if isinstance(keyword.value, ast.Constant)
                        },
                        {"check": True, "capture_output": True, "text": True},
                    )
                    self.assertTrue(
                        all(
                            keyword.arg in {"check", "capture_output", "text"}
                            and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is True
                            for keyword in run_call.keywords
                        )
                    )

    def test_freeze_law_requires_exact_metric_and_receipt_correlation(self):
        law = " ".join(FREEZE.read_text(encoding="utf-8").split())
        for clause in (
            "parallel runtime disabled",
            "H1 → H2B → H2C_RESOLVE → H2C_SCORE",
            "exactly two worker processes",
            "Every stage receipt must return the claimed historical date and run ID",
            "outcome_count = frame_count × 6",
            "canonical SHA-256 over all 72 metric objects",
            "quant outer, horizon inner",
            "Python 3.12 `float.hex()`",
            "`sort_keys=False`",
            "`scoring_hash_summary` alone is insufficient",
            "`receipt_sha256` is also excluded",
            "outcome_writes = 0",
            "connections read-only",
            "requires exactly one certified manifest and complete outcomes before launch",
            "current write-capable H1 persistence and H2C resolver commands are forbidden",
            "adds no multiprocessing/executor/async runtime",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, law)

        root_law = " ".join(ROOT_FREEZE.read_text(encoding="utf-8").split())
        phases = " ".join(PHASES.read_text(encoding="utf-8").split())
        self.assertIn("two-date read-only Parallel Canary", root_law)
        self.assertIn("separately approved", root_law)
        self.assertIn("all three executed stage source digests", root_law)
        self.assertIn("exact 72-metric hash byte encoding", root_law)
        self.assertIn("H2-D-3 — Parallel Canary (not authorized)", phases)
        self.assertIn("No within-date concurrency or evidence writes", phases)

    def test_q10_audit_uses_frames_not_outcomes_in_forecast_equation(self):
        audit = Q10_AUDIT.read_text(encoding="utf-8")
        self.assertIn("10,445 frames × 12 families × 6 horizons", audit)
        self.assertNotIn("62,670 frames ×", audit)


if __name__ == "__main__":
    unittest.main()
