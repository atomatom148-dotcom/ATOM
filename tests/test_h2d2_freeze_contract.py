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
SENSITIVE_MODULE_ROOTS = {
    "_imp",
    "_posixsubprocess",
    "_thread",
    "asyncio",
    "builtins",
    "concurrent",
    "ctypes",
    "dask",
    "importlib",
    "joblib",
    "multiprocessing",
    "nt",
    "ntpath",
    "os",
    "pkgutil",
    "posix",
    "posixpath",
    "pty",
    "queue",
    "ray",
    "runpy",
    "subprocess",
    "sys",
    "threading",
    "zipimport",
}
KNOWN_CONCURRENCY_IMPORT_NAMES = {
    "QueueListener",
}
KNOWN_CONCURRENCY_FULL_IMPORT_NAMES = {
    "faulthandler.dump_traceback_later",
    "logging.config.listen",
    "pydoc._start_server",
}
FORBIDDEN_STAGE_IMPORT_ROOTS = SENSITIVE_MODULE_ROOTS - {
    "os",
    "subprocess",
    "sys",
}
DANGEROUS_INTROSPECTION_ATTRIBUTES = {
    "__bases__",
    "__class__",
    "__dict__",
    "__getattribute__",
    "__globals__",
    "__mro__",
    "__self__",
    "__subclasses__",
}
EXPECTED_INTROSPECTION_CALL_COUNTS = {
    "quant/historical_evidence.py": 1,
    "quant/historical_evidence_verifier.py": 1,
    "quant/historical_replay_h1.py": 6,
    "quant/v9_v1_contract.py": 3,
    "quant/v9_v2d_evidence_state.py": 1,
    "quant/v9_v3_synthesis.py": 2,
    "quant/v9_v4a_evidence.py": 8,
}
ALLOWED_DYNAMIC_GETATTR_NAMES = {
    "quant/historical_replay_h1.py": {"attribute", "name"},
    "quant/v9_v1_contract.py": {"name"},
    "quant/v9_v2d_evidence_state.py": {"name"},
}
BASELINE_BUNDLE_SHA256 = "91262b90498295d7eec94022fb2e91caef7f7cab63ed78481b79868df1ef98e3"
SEQUENTIAL_RUNTIME_SOURCE_SHA256 = {
    "quant/__init__.py":
        "cc01c7d624cc73967522ab474ab1b0f94485c4e7c1116dba2813892874b608ae",
    "quant/historical_batch_h2d.py":
        "a4c9b42829b463c3d919caceea7e0252ad7062bae0d713120c17eeb7ee529683",
    "quant/historical_evidence.py":
        "e1f2616072203d7f193e566e92ab5b2fc452a4a7e61a6e5bf196d0e17b923f26",
    "quant/historical_evidence_verifier.py":
        "75bc9690b45b7b6e1278a88c587de3593436cb1ef6f9d5796872cdbf828c9709",
    "quant/historical_outcomes.py":
        "89397df5816d9f2a8909d5912ffb9b6820be9341a961222e666c59f7684b6797",
    "quant/historical_replay.py":
        "b810d0f0384483f81d131c1032f85d772ad70e9747c4f788c005088961e5a5da",
    "quant/historical_replay_h1.py":
        "0b8958d704973f031096fd541d2306b6d751c81f136470ff08d074874ae0cb10",
    "quant/history.py":
        "c42db3ea440f0c393b0180c7008943b75c298944a3a714aa22bfd18e84b06387",
    "quant/models.py":
        "9cc46919af3f99df65729390090fdf9e9eb263d97d8b49c5f49ff2e16ee8d409",
    "quant/q10_options_vol.py":
        "727b14f617e4130c5671e9370c1abaa365cb579d9091702363cc8de5a07bd1e1",
    "quant/q11_regime.py":
        "c5369859515b0bd6b9958e75efe77379320985cede5c51bce105bc7fdd672a64",
    "quant/q12_event_session.py":
        "02b6eea28a559a5a50772102aa23d195dcb8091156b06ddef8e68c8552a8f2dd",
    "quant/q1_momentum.py":
        "2ff8812102d97cde88ad8176b70b23d10ea09e735138c85a636921505d8d565a",
    "quant/q2_mean_reversion.py":
        "557ff124d453e4341192301caeafafb1ce374e7e7029ff9a22606fc21cf538f3",
    "quant/q3_volatility.py":
        "d1846b4cf8c2d59ca9874ce9b282717aef951a59a74e0277aad9f94201e755f3",
    "quant/q4_stat_arb.py":
        "bf05b0b2522a19a015303c993c62d2451d2b99416b0f8506d25407b69bd27b3b",
    "quant/q5_microstructure.py":
        "03dd9f79b8f0ede2df0ed53fd0a9a6d3dcf1c9e5642ec674a1f252e6cc531364",
    "quant/q6_volume_liquidity.py":
        "3daa7bc5264d07d100cf418854a144c830ad296bcf4d861cafed38d3883a3592",
    "quant/q7_relative_value.py":
        "f9c764f4109d403a9fbec9a6b87b5aab2cb81fe8f6f4d01f180e1493558c4fd4",
    "quant/q8_cross_asset.py":
        "42278ce758eb19daa4e92d98487480083ff29a9a75a96e315293020a53d4f51d",
    "quant/q9_factor.py":
        "af19189d37d62787adae391a71250c2c8eb6b518e2f0899d6fe5380145705244",
    "quant/quote_history.py":
        "ee8402f30e19a59c55a322f230ba1942e6aa54021af462698e8e59f96a1da11b",
    "quant/v9_v1_contract.py":
        "697b3c43ec8853f763022bcea1112b4e342584cc7cb0e59e8ac795d1ac45d057",
    "quant/v9_v2a_dataset.py":
        "78505b936eb52ae3b16acd1fa547dffe488b9354ae53c76c10fa683444c350ca",
    "quant/v9_v2b_calibration.py":
        "09aafcd8265b6e219d3bb022535fe6a116751366411cabe4a6014c95e9a2b860",
    "quant/v9_v2c_covariance.py":
        "bdaa327da0ab5ec9fd7438a8b65048ff12de884f911317584845fc2205eec826",
    "quant/v9_v2d_evidence_state.py":
        "a89ba9c0207ad2ff0546efd63017ea77ec808255b998d85e85862b1698c56308",
    "quant/v9_v3_synthesis.py":
        "f7117fd67c345ce300f5d8c83cf8e017ed6017aba00ea7b0f366873daa43f682",
    "quant/v9_v4a_evidence.py":
        "7a5ab089e73d3f460eb31f4e94207d53db90af74d985b963ddd171259638610f",
}


def canonical_source_sha256(source: str) -> str:
    normalized = source.rstrip("\n") + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def reject_duplicate_json_object_pairs(
        pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def is_sensitive_import_name(name: str) -> bool:
    root = name.split(".")[0]
    leaf = name.rsplit(".", 1)[-1]
    public_leaf = leaf.lstrip("_")
    return (
        root in SENSITIVE_MODULE_ROOTS
        or root.lstrip("_") in SENSITIVE_MODULE_ROOTS
        or name in KNOWN_CONCURRENCY_FULL_IMPORT_NAMES
        or public_leaf in KNOWN_CONCURRENCY_IMPORT_NAMES
        or public_leaf.startswith(("Thread", "Fork", "Process"))
        or public_leaf == "Pool"
        or public_leaf.endswith(("Pool", "Executor"))
    )


def is_sensitive_from_import(module: str, imported_name: str) -> bool:
    return (
        is_sensitive_import_name(module)
        or is_sensitive_import_name(imported_name)
        or is_sensitive_import_name(f"{module}.{imported_name}")
    )


def local_runtime_dependencies(relative_path: str, tree: ast.AST) -> set[str]:
    module_parts = Path(relative_path).with_suffix("").parts
    package_parts = module_parts[:-1]
    candidates = set()
    package_candidates = {
        package_parts[:depth]
        for depth in range(1, len(package_parts) + 1)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = tuple(alias.name.split("."))
                candidates.add(parts)
        elif isinstance(node, ast.ImportFrom):
            module_suffix = (
                tuple((node.module or "").split("."))
                if node.module
                else ()
            )
            if node.level:
                keep = len(package_parts) - (node.level - 1)
                if keep < 0:
                    continue
                base = package_parts[:keep] + module_suffix
            elif module_suffix:
                base = module_suffix
            else:
                continue
            candidates.add(base)
            candidates.update(base + (alias.name,) for alias in node.names)

    dependencies = set()
    for parts in candidates:
        if not parts:
            continue
        package_candidates.update(
            parts[:depth]
            for depth in range(1, len(parts) + 1)
        )
        candidate = Path(*parts).with_suffix(".py")
        if (ROOT / candidate).is_file():
            dependencies.add(candidate.as_posix())
    for parts in package_candidates:
        initializer = Path(*parts) / "__init__.py"
        if (ROOT / initializer).is_file():
            dependencies.add(initializer.as_posix())
    return dependencies


def is_explicit_exit_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id in {"exit", "quit"}
    if not isinstance(node.func, ast.Attribute):
        return False
    return (
        node.func.attr == "exit"
        or (
            node.func.attr == "_exit"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        )
    )


def execute_integrity_violations(tree: ast.Module) -> tuple[str, ...]:
    violations = []
    annotations_are_deferred = any(
        isinstance(statement, ast.ImportFrom)
        and statement.module == "__future__"
        and any(alias.name == "annotations" for alias in statement.names)
        for statement in tree.body
    )

    def record(label: str) -> None:
        if label not in violations:
            violations.append(label)

    def contains_own_yield(node: ast.AST) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return False
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
        return any(
            contains_own_yield(child)
            for child in ast.iter_child_nodes(node)
        )

    def direct_lexical_nodes(scope: ast.AST) -> tuple[ast.AST, ...]:
        result = []

        def visit(node: ast.AST) -> None:
            result.append(node)
            if node is not scope and isinstance(node, (
                ast.AsyncFunctionDef,
                ast.FunctionDef,
            )):
                for decorator in node.decorator_list:
                    visit(decorator)
                for default in node.args.defaults:
                    visit(default)
                for default in node.args.kw_defaults:
                    if default is not None:
                        visit(default)
                if not annotations_are_deferred:
                    for argument in (
                        *node.args.posonlyargs,
                        *node.args.args,
                        *node.args.kwonlyargs,
                    ):
                        if argument.annotation is not None:
                            visit(argument.annotation)
                    for argument in (node.args.vararg, node.args.kwarg):
                        if argument is not None and argument.annotation is not None:
                            visit(argument.annotation)
                    if node.returns is not None:
                        visit(node.returns)
                return
            if node is not scope and isinstance(node, ast.Lambda):
                for default in node.args.defaults:
                    visit(default)
                for default in node.args.kw_defaults:
                    if default is not None:
                        visit(default)
                return
            if node is not scope and isinstance(node, ast.ClassDef):
                for decorator in node.decorator_list:
                    visit(decorator)
                for base in node.bases:
                    visit(base)
                for keyword in node.keywords:
                    visit(keyword.value)
                return
            if isinstance(node, (
                ast.DictComp,
                ast.GeneratorExp,
                ast.ListComp,
                ast.SetComp,
            )):
                for generator in node.generators:
                    visit(generator.iter)
                    for condition in generator.ifs:
                        visit(condition)
                if isinstance(node, ast.DictComp):
                    visit(node.key)
                    visit(node.value)
                else:
                    visit(node.elt)
                return
            for child in ast.iter_child_nodes(node):
                visit(child)

        visit(scope)
        return tuple(result)

    def lexical_binding_events(
            scope: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> dict[str, tuple[ast.AST, ...]]:
        events: dict[str, list[ast.AST]] = {}

        def bind(name: str | None, node: ast.AST) -> None:
            if name:
                events.setdefault(name, []).append(node)

        for node in direct_lexical_nodes(scope):
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, (ast.Store, ast.Del))
            ):
                bind(node.id, node)
            elif isinstance(node, ast.arg):
                bind(node.arg, node)
            elif (
                node is not scope
                and isinstance(node, (
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.FunctionDef,
                ))
            ):
                bind(node.name, node)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    bind(alias.asname or alias.name.split(".", 1)[0], alias)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    bind(alias.asname or alias.name, alias)
            elif isinstance(node, ast.ExceptHandler):
                bind(
                    node.name.id if isinstance(node.name, ast.Name) else node.name,
                    node,
                )
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                for name in node.names:
                    bind(name, node)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
                bind(node.name, node)
            elif isinstance(node, ast.MatchMapping):
                bind(node.rest, node)
        return {
            name: tuple(bound_nodes)
            for name, bound_nodes in events.items()
        }

    def direct_lexical_name_loads(
            scope: ast.FunctionDef | ast.AsyncFunctionDef,
            protected_name: str,
    ) -> tuple[ast.Name, ...]:
        loads = []

        def target_names(target: ast.AST) -> set[str]:
            if isinstance(target, ast.Name):
                return {target.id}
            if isinstance(target, (ast.List, ast.Tuple)):
                return set().union(*(
                    target_names(item) for item in target.elts
                )) if target.elts else set()
            if isinstance(target, ast.Starred):
                return target_names(target.value)
            return set()

        def visit(node: ast.AST, shadowed: frozenset[str]) -> None:
            if node is not scope and isinstance(node, (
                ast.AsyncFunctionDef,
                ast.FunctionDef,
            )):
                for decorator in node.decorator_list:
                    visit(decorator, shadowed)
                for default in node.args.defaults:
                    visit(default, shadowed)
                for default in node.args.kw_defaults:
                    if default is not None:
                        visit(default, shadowed)
                if not annotations_are_deferred:
                    for argument in (
                        *node.args.posonlyargs,
                        *node.args.args,
                        *node.args.kwonlyargs,
                    ):
                        if argument.annotation is not None:
                            visit(argument.annotation, shadowed)
                    for argument in (node.args.vararg, node.args.kwarg):
                        if argument is not None and argument.annotation is not None:
                            visit(argument.annotation, shadowed)
                    if node.returns is not None:
                        visit(node.returns, shadowed)
                return
            if node is not scope and isinstance(node, ast.Lambda):
                for default in node.args.defaults:
                    visit(default, shadowed)
                for default in node.args.kw_defaults:
                    if default is not None:
                        visit(default, shadowed)
                return
            if node is not scope and isinstance(node, ast.ClassDef):
                for decorator in node.decorator_list:
                    visit(decorator, shadowed)
                for base in node.bases:
                    visit(base, shadowed)
                for keyword in node.keywords:
                    visit(keyword.value, shadowed)
                return
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id == protected_name
                and node.id not in shadowed
            ):
                loads.append(node)
                return
            if isinstance(node, (
                ast.DictComp,
                ast.GeneratorExp,
                ast.ListComp,
                ast.SetComp,
            )):
                local_shadowed = set(shadowed)
                for generator in node.generators:
                    visit(generator.iter, frozenset(local_shadowed))
                    local_shadowed.update(target_names(generator.target))
                    for condition in generator.ifs:
                        visit(condition, frozenset(local_shadowed))
                if isinstance(node, ast.DictComp):
                    visit(node.key, frozenset(local_shadowed))
                    visit(node.value, frozenset(local_shadowed))
                else:
                    visit(node.elt, frozenset(local_shadowed))
                return
            for child in ast.iter_child_nodes(node):
                visit(child, shadowed)

        visit(scope, frozenset())
        return tuple(loads)

    top_level_execute = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute"
    ]
    execute_function = (
        top_level_execute[0]
        if len(top_level_execute) == 1
        else None
    )
    if execute_function is None:
        record("execute-top-level-definition")
    else:
        if execute_function.decorator_list:
            record("execute-decoration")
        arguments = execute_function.args
        kw_defaults = arguments.kw_defaults
        exact_execute_signature = (
            not arguments.posonlyargs
            and [argument.arg for argument in arguments.args] == ["days"]
            and arguments.vararg is None
            and [argument.arg for argument in arguments.kwonlyargs] == [
                "continue_on_failure",
                "run_json",
                "existing",
            ]
            and arguments.kwarg is None
            and not arguments.defaults
            and len(kw_defaults) == 3
            and kw_defaults[0] is None
            and isinstance(kw_defaults[1], ast.Name)
            and isinstance(kw_defaults[1].ctx, ast.Load)
            and kw_defaults[1].id == "_run_json"
            and isinstance(kw_defaults[2], ast.Name)
            and isinstance(kw_defaults[2].ctx, ast.Load)
            and kw_defaults[2].id == "_existing_manifests"
        )
        if not exact_execute_signature:
            record("execute-signature")
        if any(contains_own_yield(statement) for statement in execute_function.body):
            record("execute-generator")

    execute_declarations = tuple(
        node for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        )
        and node.name == "execute"
    )
    if (
        execute_function is None
        or any(node is not execute_function for node in execute_declarations)
    ):
        record("execute-shadow")

    execute_name_writes = any(
        isinstance(node, ast.Name)
        and node.id == "execute"
        and isinstance(node.ctx, (ast.Store, ast.Del))
        for node in ast.walk(tree)
    )
    execute_arguments = any(
        isinstance(node, ast.arg) and node.arg == "execute"
        for node in ast.walk(tree)
    )
    execute_scope_declarations = any(
        isinstance(node, (ast.Global, ast.Nonlocal))
        and "execute" in node.names
        for node in ast.walk(tree)
    )
    execute_imports = any(
        (
            isinstance(node, ast.Import)
            and any(
                (alias.asname or alias.name.split(".")[0]) == "execute"
                for alias in node.names
            )
        )
        or (
            isinstance(node, ast.ImportFrom)
            and any(
                (alias.asname or alias.name) == "execute"
                for alias in node.names
            )
        )
        for node in ast.walk(tree)
    )
    execute_except_names = any(
        isinstance(node, ast.ExceptHandler) and node.name == "execute"
        for node in ast.walk(tree)
    )
    execute_match_captures = any(
        (
            isinstance(node, (ast.MatchAs, ast.MatchStar))
            and node.name == "execute"
        )
        or (
            isinstance(node, ast.MatchMapping)
            and node.rest == "execute"
        )
        for node in ast.walk(tree)
    )
    if any((
        execute_name_writes,
        execute_arguments,
        execute_scope_declarations,
        execute_imports,
        execute_except_names,
        execute_match_captures,
    )):
        record("execute-shadow")

    execute_binding_events = (
        lexical_binding_events(execute_function)
        if execute_function is not None
        else {}
    )
    run_json_parameter = None
    if execute_function is not None:
        run_json_parameter = next((
            argument
            for argument in execute_function.args.kwonlyargs
            if argument.arg == "run_json"
        ), None)
    if (
        run_json_parameter is None
        or execute_binding_events.get("run_json", ())
        != (run_json_parameter,)
    ):
        record("execute-dispatch-binding")

    day_loops = (
        tuple(
            statement for statement in execute_function.body
            if isinstance(statement, ast.For)
            and isinstance(statement.target, ast.Name)
            and isinstance(statement.target.ctx, ast.Store)
            and statement.target.id == "day"
            and isinstance(statement.iter, ast.Name)
            and isinstance(statement.iter.ctx, ast.Load)
            and statement.iter.id == "days"
            and statement.type_comment is None
        )
        if execute_function is not None
        else ()
    )
    day_loop = day_loops[0] if len(day_loops) == 1 else None
    if (
        day_loop is None
        or execute_binding_events.get("day", ()) != (day_loop.target,)
    ):
        record("execute-day-binding")

    execute_parents = {
        child: parent
        for parent in ast.walk(execute_function)
        if execute_function is not None
        for child in ast.iter_child_nodes(parent)
    }
    day_tries = (
        tuple(
            statement for statement in day_loop.body
            if isinstance(statement, ast.Try)
        )
        if day_loop is not None
        else ()
    )
    day_try = day_tries[0] if len(day_tries) == 1 else None

    def simple_assignment(name: str) -> ast.Assign | None:
        matches = tuple(
            node for node in direct_lexical_nodes(execute_function)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.targets[0].ctx, ast.Store)
            and node.targets[0].id == name
            and node.type_comment is None
        ) if execute_function is not None else ()
        return matches[0] if len(matches) == 1 else None

    run_id_assignment = simple_assignment("run_id")
    exact_run_id = False
    if run_id_assignment is not None:
        value = run_id_assignment.value
        exact_run_id = (
            execute_parents.get(run_id_assignment) is day_try
            and isinstance(value, ast.IfExp)
            and isinstance(value.test, ast.Name)
            and value.test.id == "manifest"
            and isinstance(value.body, ast.Call)
            and isinstance(value.body.func, ast.Name)
            and value.body.func.id == "str"
            and len(value.body.args) == 1
            and not value.body.keywords
            and isinstance(value.body.args[0], ast.Subscript)
            and isinstance(value.body.args[0].value, ast.Name)
            and value.body.args[0].value.id == "manifest"
            and isinstance(value.body.args[0].slice, ast.Constant)
            and value.body.args[0].slice.value == "replay_run_id"
            and isinstance(value.orelse, ast.JoinedStr)
        )

    lineage_assignments = {"run_id": run_id_assignment}
    for lineage_name in (
        "dataset_digest",
        "configuration_digest",
        "frame_count",
    ):
        assignment = simple_assignment(lineage_name)
        lineage_assignments[lineage_name] = assignment
        value = assignment.value if assignment is not None else None
        if not (
            assignment is not None
            and execute_parents.get(assignment) is day_try
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "get"
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "manifest"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Constant)
            and value.args[0].value == lineage_name
            and not value.keywords
        ):
            lineage_assignments[lineage_name] = None
    if (
        not exact_run_id
        or any(
            assignment is None
            or execute_binding_events.get(name, ())
            != (assignment.targets[0],)
            for name, assignment in lineage_assignments.items()
        )
    ):
        record("execute-lineage-binding")

    top_level_main = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    ]
    main_function = top_level_main[0] if len(top_level_main) == 1 else None
    if main_function is None:
        record("main-top-level-definition")
    else:
        if main_function.decorator_list:
            record("main-decoration")
        arguments = main_function.args
        exact_main_signature = (
            not arguments.posonlyargs
            and [argument.arg for argument in arguments.args] == ["argv"]
            and arguments.vararg is None
            and not arguments.kwonlyargs
            and arguments.kwarg is None
            and len(arguments.defaults) == 1
            and isinstance(arguments.defaults[0], ast.Constant)
            and arguments.defaults[0].value is None
            and not arguments.kw_defaults
        )
        if not exact_main_signature:
            record("main-signature")
        if any(contains_own_yield(statement) for statement in main_function.body):
            record("main-generator")

    main_declarations = tuple(
        node for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        )
        and node.name == "main"
    )
    if (
        main_function is None
        or any(node is not main_function for node in main_declarations)
    ):
        record("main-shadow")

    main_name_writes = any(
        isinstance(node, ast.Name)
        and node.id == "main"
        and isinstance(node.ctx, (ast.Store, ast.Del))
        for node in ast.walk(tree)
    )
    main_arguments = any(
        isinstance(node, ast.arg) and node.arg == "main"
        for node in ast.walk(tree)
    )
    main_scope_declarations = any(
        isinstance(node, (ast.Global, ast.Nonlocal))
        and "main" in node.names
        for node in ast.walk(tree)
    )
    main_imports = any(
        (
            isinstance(node, ast.Import)
            and any(
                (alias.asname or alias.name.split(".")[0]) == "main"
                for alias in node.names
            )
        )
        or (
            isinstance(node, ast.ImportFrom)
            and any(
                (alias.asname or alias.name) == "main"
                for alias in node.names
            )
        )
        for node in ast.walk(tree)
    )
    main_except_names = any(
        isinstance(node, ast.ExceptHandler) and node.name == "main"
        for node in ast.walk(tree)
    )
    main_match_captures = any(
        (
            isinstance(node, (ast.MatchAs, ast.MatchStar))
            and node.name == "main"
        )
        or (
            isinstance(node, ast.MatchMapping)
            and node.rest == "main"
        )
        for node in ast.walk(tree)
    )
    if any((
        main_name_writes,
        main_arguments,
        main_scope_declarations,
        main_imports,
        main_except_names,
        main_match_captures,
    )):
        record("main-shadow")

    execute_loads = tuple(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "execute"
    )
    if len(execute_loads) != 1:
        record("execute-load-count")

    direct_assignments = []
    pinned_execute_assignment = None
    if main_function is not None:
        direct_assignments = [
            statement for statement in main_function.body
            if isinstance(statement, ast.Assign)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "execute"
        ]
    if len(direct_assignments) != 1:
        record("execute-call-shape")
    else:
        assignment = direct_assignments[0]
        call = assignment.value
        keyword = call.keywords[0] if len(call.keywords) == 1 else None
        exact_call = (
            len(assignment.targets) == 1
            and isinstance(assignment.targets[0], ast.Name)
            and isinstance(assignment.targets[0].ctx, ast.Store)
            and assignment.targets[0].id == "output"
            and assignment.type_comment is None
            and len(execute_loads) == 1
            and call.func is execute_loads[0]
            and len(call.args) == 1
            and isinstance(call.args[0], ast.Name)
            and isinstance(call.args[0].ctx, ast.Load)
            and call.args[0].id == "days"
            and keyword is not None
            and keyword.arg == "continue_on_failure"
            and isinstance(keyword.value, ast.Attribute)
            and isinstance(keyword.value.ctx, ast.Load)
            and keyword.value.attr == "continue_on_failure"
            and isinstance(keyword.value.value, ast.Name)
            and isinstance(keyword.value.value.ctx, ast.Load)
            and keyword.value.value.id == "args"
        )
        if not exact_call:
            record("execute-call-shape")
        else:
            pinned_execute_assignment = assignment

    main_integrity_parents = {
        child: parent
        for parent in ast.walk(main_function) if main_function is not None
        for child in ast.iter_child_nodes(parent)
    }

    main_nodes = (
        direct_lexical_nodes(main_function)
        if main_function is not None
        else ()
    )
    main_binding_events = (
        lexical_binding_events(main_function)
        if main_function is not None
        else {}
    )
    if (
        pinned_execute_assignment is None
        or main_binding_events.get("output", ())
        != (pinned_execute_assignment.targets[0],)
    ):
        record("main-output-binding")

    exact_output_use = False
    if main_function is not None and pinned_execute_assignment is not None:
        output_index = main_function.body.index(pinned_execute_assignment)
        print_statement = (
            main_function.body[output_index + 1]
            if output_index + 1 < len(main_function.body)
            else None
        )
        return_statement = (
            main_function.body[output_index + 2]
            if output_index + 2 < len(main_function.body)
            else None
        )
        print_call = (
            print_statement.value
            if isinstance(print_statement, ast.Expr)
            else None
        )
        dumps_call = (
            print_call.args[0]
            if isinstance(print_call, ast.Call) and len(print_call.args) == 1
            else None
        )
        print_output_load = (
            dumps_call.args[0]
            if isinstance(dumps_call, ast.Call) and len(dumps_call.args) == 1
            else None
        )
        status_expression = (
            return_statement.value
            if isinstance(return_statement, ast.Return)
            else None
        )
        status_compare = (
            status_expression.test
            if isinstance(status_expression, ast.IfExp)
            else None
        )
        status_subscript = (
            status_compare.left
            if isinstance(status_compare, ast.Compare)
            else None
        )
        status_output_load = (
            status_subscript.value
            if isinstance(status_subscript, ast.Subscript)
            else None
        )
        dumps_keywords = {
            keyword.arg: keyword.value
            for keyword in dumps_call.keywords
            if keyword.arg is not None
        } if isinstance(dumps_call, ast.Call) else {}
        separators = dumps_keywords.get("separators")
        exact_output_use = (
            output_index + 3 == len(main_function.body)
            and isinstance(print_call, ast.Call)
            and isinstance(print_call.func, ast.Name)
            and print_call.func.id == "print"
            and not print_call.keywords
            and isinstance(dumps_call, ast.Call)
            and isinstance(dumps_call.func, ast.Attribute)
            and dumps_call.func.attr == "dumps"
            and isinstance(dumps_call.func.value, ast.Name)
            and dumps_call.func.value.id == "json"
            and set(dumps_keywords) == {"separators", "sort_keys"}
            and isinstance(dumps_keywords.get("sort_keys"), ast.Constant)
            and dumps_keywords["sort_keys"].value is True
            and isinstance(separators, ast.Tuple)
            and [
                element.value
                for element in separators.elts
                if isinstance(element, ast.Constant)
            ] == [",", ":"]
            and isinstance(print_output_load, ast.Name)
            and isinstance(print_output_load.ctx, ast.Load)
            and print_output_load.id == "output"
            and isinstance(status_expression, ast.IfExp)
            and isinstance(status_expression.body, ast.Constant)
            and status_expression.body.value == 1
            and isinstance(status_expression.orelse, ast.Constant)
            and status_expression.orelse.value == 0
            and isinstance(status_compare, ast.Compare)
            and len(status_compare.ops) == 1
            and isinstance(status_compare.ops[0], ast.Eq)
            and len(status_compare.comparators) == 1
            and isinstance(status_compare.comparators[0], ast.Constant)
            and status_compare.comparators[0].value == "FAILED"
            and isinstance(status_subscript, ast.Subscript)
            and isinstance(status_subscript.slice, ast.Constant)
            and status_subscript.slice.value == "overall_status"
            and isinstance(status_output_load, ast.Name)
            and isinstance(status_output_load.ctx, ast.Load)
            and status_output_load.id == "output"
            and direct_lexical_name_loads(main_function, "output")
            == (print_output_load, status_output_load)
        )
    if not exact_output_use:
        record("main-output-use")
    days_assignments = [
        node for node in main_nodes
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.targets[0].ctx, ast.Store)
        and node.targets[0].id == "days"
    ]
    pinned_days_assignment = None
    if len(days_assignments) == 1:
        days_assignment = days_assignments[0]
        days_call = days_assignment.value
        days_parent = main_integrity_parents.get(days_assignment)
        expected_keywords = (
            ("dates", "dates"),
            ("start", "start"),
            ("end", "end"),
            ("maximum", "max_sessions"),
        )
        exact_days_assignment = (
            days_assignment.type_comment is None
            and isinstance(days_call, ast.Call)
            and isinstance(days_call.func, ast.Name)
            and isinstance(days_call.func.ctx, ast.Load)
            and days_call.func.id == "requested_dates"
            and not days_call.args
            and len(days_call.keywords) == len(expected_keywords)
            and all(
                keyword.arg == keyword_name
                and isinstance(keyword.value, ast.Attribute)
                and isinstance(keyword.value.ctx, ast.Load)
                and keyword.value.attr == attribute_name
                and isinstance(keyword.value.value, ast.Name)
                and isinstance(keyword.value.value.ctx, ast.Load)
                and keyword.value.value.id == "args"
                for keyword, (keyword_name, attribute_name) in zip(
                    days_call.keywords,
                    expected_keywords,
                )
            )
            and isinstance(days_parent, ast.Try)
            and days_parent.body == [days_assignment]
            and main_integrity_parents.get(days_parent) is main_function
        )
        if exact_days_assignment:
            pinned_days_assignment = days_assignment
    if pinned_days_assignment is None:
        record("days-selection-shape")

    if (
        pinned_days_assignment is not None
        and pinned_execute_assignment is not None
    ):
        selection_end = (
            getattr(
                pinned_days_assignment,
                "end_lineno",
                pinned_days_assignment.lineno,
            ),
            getattr(pinned_days_assignment, "end_col_offset", 0),
        )
        execute_start = (
            pinned_execute_assignment.lineno,
            pinned_execute_assignment.col_offset,
        )
        if selection_end >= execute_start:
            record("days-selection-shape")
        else:
            def is_between_selection_and_execute(node: ast.AST) -> bool:
                return (
                    hasattr(node, "lineno")
                    and selection_end
                    < (node.lineno, getattr(node, "col_offset", 0))
                    < execute_start
                )

            between_nodes = tuple(
                node for node in main_nodes
                if is_between_selection_and_execute(node)
            )
            aliases = {"days"}
            aliases_changed = True
            while aliases_changed:
                aliases_changed = False
                for node in between_nodes:
                    target = value = None
                    if isinstance(node, ast.Assign) and len(node.targets) == 1:
                        target, value = node.targets[0], node.value
                    elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
                        target, value = node.target, node.value
                    if (
                        isinstance(target, ast.Name)
                        and isinstance(value, ast.Name)
                        and value.id in aliases
                        and target.id not in aliases
                    ):
                        aliases.add(target.id)
                        aliases_changed = True

            def alias_root(node: ast.AST) -> str | None:
                while isinstance(node, (
                    ast.Attribute,
                    ast.Starred,
                    ast.Subscript,
                )):
                    node = node.value
                return node.id if isinstance(node, ast.Name) else None

            def mutates_days_target(node: ast.AST) -> bool:
                if isinstance(node, ast.Name):
                    return (
                        node.id == "days"
                        and isinstance(node.ctx, (ast.Store, ast.Del))
                    )
                if isinstance(node, (ast.Attribute, ast.Subscript)):
                    return alias_root(node) in aliases
                if isinstance(node, (ast.List, ast.Tuple)):
                    return any(mutates_days_target(item) for item in node.elts)
                if isinstance(node, ast.Starred):
                    return mutates_days_target(node.value)
                return False

            mutator_names = {
                "__delitem__",
                "__iadd__",
                "__imul__",
                "__setitem__",
                "add",
                "append",
                "clear",
                "discard",
                "extend",
                "insert",
                "pop",
                "remove",
                "reverse",
                "setdefault",
                "sort",
                "update",
            }

            days_rebound = any(
                event is not pinned_days_assignment.targets[0]
                and is_between_selection_and_execute(event)
                for event in main_binding_events.get("days", ())
            )
            days_mutated = any(
                (
                    isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                    and any(
                        mutates_days_target(target)
                        for target in (
                            node.targets
                            if isinstance(node, ast.Assign)
                            else [node.target]
                        )
                    )
                )
                or (
                    isinstance(node, (ast.AugAssign, ast.Delete))
                    and any(
                        mutates_days_target(target)
                        for target in (
                            node.targets
                            if isinstance(node, ast.Delete)
                            else [node.target]
                        )
                    )
                )
                or (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in mutator_names
                    and alias_root(node.func.value) in aliases
                )
                or (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"delattr", "setattr"}
                    and node.args
                    and alias_root(node.args[0]) in aliases
                )
                or (
                    isinstance(node, (ast.For, ast.AsyncFor))
                    and mutates_days_target(node.target)
                )
                or (
                    isinstance(node, (ast.With, ast.AsyncWith))
                    and any(
                        mutates_days_target(item.optional_vars)
                        for item in node.items
                        if item.optional_vars is not None
                    )
                )
                for node in between_nodes
            )
            if days_mutated or days_rebound:
                record("days-selection-mutation")

    def contains_reachable_terminator(node: ast.AST) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return False
        if isinstance(node, (
            ast.Assert,
            ast.Break,
            ast.Continue,
            ast.Raise,
            ast.Return,
            ast.Yield,
            ast.YieldFrom,
        )):
            return True
        if is_explicit_exit_call(node):
            return True
        return any(
            contains_reachable_terminator(child)
            for child in ast.iter_child_nodes(node)
        )

    if main_function is not None and pinned_execute_assignment is not None:
        execute_index = main_function.body.index(pinned_execute_assignment)
        if any(
            contains_reachable_terminator(statement)
            for statement in main_function.body[:execute_index]
        ):
            record("main-early-termination")

    main_loads = tuple(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "main"
    )
    if len(main_loads) != 1:
        record("main-load-count")

    module_name_loads = tuple(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "__name__"
    )
    system_exit_loads = tuple(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "SystemExit"
    )
    integrity_parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    def is_module_scope(node: ast.AST) -> bool:
        parent = integrity_parents.get(node)
        while parent is not None and parent is not tree:
            if isinstance(parent, (
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.FunctionDef,
                ast.Lambda,
            )):
                return False
            parent = integrity_parents.get(parent)
        return parent is tree

    def has_protected_module_binding(name: str) -> bool:
        return any(
            (
                isinstance(node, ast.Name)
                and node.id == name
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and is_module_scope(node)
            )
            or (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == name
                and is_module_scope(node)
            )
            or (
                isinstance(node, ast.Import)
                and is_module_scope(node)
                and any(
                    (alias.asname or alias.name.split(".")[0]) == name
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and is_module_scope(node)
                and any(
                    (alias.asname or alias.name) == name
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ExceptHandler)
                and node.name == name
                and is_module_scope(node)
            )
            or (
                isinstance(node, (ast.Global, ast.Nonlocal))
                and name in node.names
            )
            or (
                isinstance(node, (ast.MatchAs, ast.MatchStar))
                and node.name == name
                and is_module_scope(node)
            )
            or (
                isinstance(node, ast.MatchMapping)
                and node.rest == name
                and is_module_scope(node)
            )
            for node in ast.walk(tree)
        )

    if (
        has_protected_module_binding("__name__")
        or has_protected_module_binding("SystemExit")
    ):
        record("main-entrypoint")
    entrypoints = [
        statement for statement in tree.body
        if isinstance(statement, ast.If)
        and isinstance(statement.test, ast.Compare)
        and isinstance(statement.test.left, ast.Name)
        and isinstance(statement.test.left.ctx, ast.Load)
        and statement.test.left.id == "__name__"
        and len(statement.test.ops) == 1
        and isinstance(statement.test.ops[0], ast.Eq)
        and len(statement.test.comparators) == 1
        and isinstance(statement.test.comparators[0], ast.Constant)
        and statement.test.comparators[0].value == "__main__"
    ]
    exact_entrypoint = False
    if len(entrypoints) == 1:
        entrypoint = entrypoints[0]
        raise_statement = (
            entrypoint.body[0]
            if len(entrypoint.body) == 1
            else None
        )
        system_exit_call = (
            raise_statement.exc
            if isinstance(raise_statement, ast.Raise)
            else None
        )
        main_call = (
            system_exit_call.args[0]
            if (
                isinstance(system_exit_call, ast.Call)
                and len(system_exit_call.args) == 1
            )
            else None
        )
        exact_entrypoint = (
            not entrypoint.orelse
            and tree.body[-1] is entrypoint
            and len(module_name_loads) == 1
            and entrypoint.test.left is module_name_loads[0]
            and isinstance(raise_statement, ast.Raise)
            and raise_statement.cause is None
            and isinstance(system_exit_call, ast.Call)
            and isinstance(system_exit_call.func, ast.Name)
            and isinstance(system_exit_call.func.ctx, ast.Load)
            and system_exit_call.func.id == "SystemExit"
            and len(system_exit_loads) == 1
            and system_exit_call.func is system_exit_loads[0]
            and not system_exit_call.keywords
            and isinstance(main_call, ast.Call)
            and isinstance(main_call.func, ast.Name)
            and isinstance(main_call.func.ctx, ast.Load)
            and main_call.func.id == "main"
            and len(main_loads) == 1
            and main_call.func is main_loads[0]
            and not main_call.args
            and not main_call.keywords
        )
        entrypoint_index = tree.body.index(entrypoint)
        if any(
            contains_reachable_terminator(statement)
            for statement in tree.body[:entrypoint_index]
        ):
            exact_entrypoint = False
    if not exact_entrypoint:
        record("main-entrypoint")

    return tuple(violations)


def lexical_import_origins(
        tree: ast.Module,
        *,
        include_from_imports: bool = False,
        propagate_aliases: bool = False,
        fallback_origins: dict[str, str] | None = None,
) -> tuple[dict[ast.AST, ast.AST], object]:
    """Resolve import bindings without leaking aliases across lexical scopes."""
    fallback_origins = fallback_origins or {}
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    scope_parents: dict[ast.AST, ast.AST | None] = {tree: None}
    node_scopes: dict[ast.AST, ast.AST] = {}
    raw_bound_names: dict[ast.AST, set[str]] = {tree: set()}
    global_names: dict[ast.AST, set[str]] = {tree: set()}
    nonlocal_names: dict[ast.AST, set[str]] = {tree: set()}
    binding_events: list[tuple[ast.AST, str, str | None]] = []
    alias_events: list[tuple[ast.AST, list[ast.AST], ast.AST]] = []

    def new_scope(scope: ast.AST, parent: ast.AST) -> None:
        if isinstance(scope, (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
        )):
            while isinstance(parent, ast.ClassDef):
                outer = scope_parents[parent]
                if outer is None:
                    break
                parent = outer
        scope_parents[scope] = parent
        raw_bound_names[scope] = set()
        global_names[scope] = set()
        nonlocal_names[scope] = set()

    def bind(scope: ast.AST, name: str, origin: str | None = None) -> None:
        raw_bound_names[scope].add(name)
        binding_events.append((scope, name, origin))

    def target_names(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name):
            return {node.id}
        if isinstance(node, (ast.List, ast.Tuple)):
            return set().union(*(
                target_names(item) for item in node.elts
            )) if node.elts else set()
        return set()

    def visit_arguments_outer(arguments: ast.arguments, scope: ast.AST) -> None:
        for default in arguments.defaults:
            visit(default, scope)
        for default in arguments.kw_defaults:
            if default is not None:
                visit(default, scope)
        for argument in (
            arguments.posonlyargs
            + arguments.args
            + arguments.kwonlyargs
        ):
            if argument.annotation is not None:
                visit(argument.annotation, scope)
        if arguments.vararg is not None and arguments.vararg.annotation is not None:
            visit(arguments.vararg.annotation, scope)
        if arguments.kwarg is not None and arguments.kwarg.annotation is not None:
            visit(arguments.kwarg.annotation, scope)

    def bind_arguments(arguments: ast.arguments, scope: ast.AST) -> None:
        for argument in (
            arguments.posonlyargs
            + arguments.args
            + arguments.kwonlyargs
        ):
            bind(scope, argument.arg)
        if arguments.vararg is not None:
            bind(scope, arguments.vararg.arg)
        if arguments.kwarg is not None:
            bind(scope, arguments.kwarg.arg)

    def visit_comprehension(node: ast.AST, scope: ast.AST) -> None:
        generators = node.generators
        new_scope(node, scope)
        visit(generators[0].iter, scope)
        for index, generator in enumerate(generators):
            if index:
                visit(generator.iter, node)
            visit(generator.target, node)
            for condition in generator.ifs:
                visit(condition, node)
        if isinstance(node, ast.DictComp):
            visit(node.key, node)
            visit(node.value, node)
        else:
            visit(node.elt, node)

    def visit(node: ast.AST, scope: ast.AST) -> None:
        node_scopes[node] = scope
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bind(scope, node.name)
            for decorator in node.decorator_list:
                visit(decorator, scope)
            visit_arguments_outer(node.args, scope)
            if node.returns is not None:
                visit(node.returns, scope)
            new_scope(node, scope)
            bind_arguments(node.args, node)
            for statement in node.body:
                visit(statement, node)
            return
        if isinstance(node, ast.Lambda):
            visit_arguments_outer(node.args, scope)
            new_scope(node, scope)
            bind_arguments(node.args, node)
            visit(node.body, node)
            return
        if isinstance(node, ast.ClassDef):
            bind(scope, node.name)
            for decorator in node.decorator_list:
                visit(decorator, scope)
            for base in node.bases:
                visit(base, scope)
            for keyword in node.keywords:
                visit(keyword.value, scope)
            new_scope(node, scope)
            for statement in node.body:
                visit(statement, node)
            return
        if isinstance(node, (
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
        )):
            visit_comprehension(node, scope)
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                origin = alias.name if alias.asname else alias.name.split(".")[0]
                bind(scope, name, origin)
            return
        if isinstance(node, ast.ImportFrom):
            if include_from_imports and node.level == 0 and node.module:
                for alias in node.names:
                    if alias.name != "*":
                        bind(
                            scope,
                            alias.asname or alias.name,
                            f"{node.module}.{alias.name}",
                        )
            else:
                for alias in node.names:
                    if alias.name != "*":
                        bind(scope, alias.asname or alias.name)
            return
        if isinstance(node, ast.Global):
            global_names[scope].update(node.names)
            return
        if isinstance(node, ast.Nonlocal):
            nonlocal_names[scope].update(node.names)
            return
        if isinstance(node, ast.ExceptHandler) and node.name:
            bind(scope, node.name)
        if isinstance(node, ast.Assign):
            alias_events.append((scope, node.targets, node.value))
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            if node.value is not None:
                alias_events.append((scope, [node.target], node.value))
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bind(scope, node.id)
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    for statement in tree.body:
        visit(statement, tree)

    def nonlocal_scope(scope: ast.AST, name: str) -> ast.AST:
        parent = scope_parents[scope]
        while parent is not None and parent is not tree:
            if name in raw_bound_names[parent]:
                return parent
            parent = scope_parents[parent]
        return tree

    def binding_scope(scope: ast.AST, name: str) -> ast.AST:
        if scope is not tree and name in global_names[scope]:
            return tree
        if scope is not tree and name in nonlocal_names[scope]:
            return nonlocal_scope(scope, name)
        return scope

    bound_names = {scope: set() for scope in scope_parents}
    import_origins: dict[ast.AST, dict[str, set[str]]] = {
        scope: {} for scope in scope_parents
    }
    for scope, name, origin in binding_events:
        target_scope = binding_scope(scope, name)
        bound_names[target_scope].add(name)
        if origin is not None:
            import_origins[target_scope].setdefault(name, set()).add(origin)

    def resolve(node: ast.Name) -> frozenset[str]:
        scope = binding_scope(node_scopes[node], node.id)
        while True:
            if node.id in bound_names[scope]:
                return frozenset(import_origins[scope].get(node.id, ()))
            parent = scope_parents[scope]
            if parent is None:
                fallback = fallback_origins.get(node.id)
                return frozenset((fallback,)) if fallback else frozenset()
            scope = parent

    def expression_origins(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name):
            return set(resolve(node))
        if isinstance(node, ast.Attribute):
            return {
                f"{origin}.{node.attr}"
                for origin in expression_origins(node.value)
            }
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return set().union(*(
                expression_origins(item) for item in node.elts
            )) if node.elts else set()
        if isinstance(node, ast.Dict):
            items = [*node.keys, *node.values]
            return set().union(*(
                expression_origins(item)
                for item in items
                if item is not None
            )) if items else set()
        if isinstance(node, (ast.Starred, ast.NamedExpr, ast.Subscript)):
            return expression_origins(node.value)
        if isinstance(node, ast.IfExp):
            return (
                expression_origins(node.body)
                | expression_origins(node.orelse)
            )
        return set()

    if propagate_aliases:
        changed = True
        while changed:
            changed = False
            for scope, targets, value in alias_events:
                origins = expression_origins(value)
                if not origins:
                    continue
                for name in set().union(*(
                    target_names(target) for target in targets
                )):
                    target_scope = binding_scope(scope, name)
                    known = import_origins[target_scope].setdefault(name, set())
                    if not origins.issubset(known):
                        known.update(origins)
                        changed = True

    return parents, resolve


def sensitive_module_reexports(
        tree: ast.AST,
        module_aliases: dict[str, str],
) -> tuple[ast.AST, ...]:
    tracked_bindings = set(module_aliases)
    parents, resolve_import_origins = lexical_import_origins(
        tree,
        include_from_imports=True,
        propagate_aliases=True,
        fallback_origins={
            "classmethod": "builtins.classmethod",
            "filter": "builtins.filter",
            "map": "builtins.map",
            "max": "builtins.max",
            "min": "builtins.min",
            "object": "builtins.object",
            "setattr": "builtins.setattr",
            "sorted": "builtins.sorted",
            "staticmethod": "builtins.staticmethod",
            "type": "builtins.type",
        },
    )

    def import_origin_names(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name):
            return set(resolve_import_origins(node))
        if isinstance(node, ast.Attribute):
            return {
                f"{origin}.{node.attr}"
                for origin in import_origin_names(node.value)
            }
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return set().union(*(
                import_origin_names(item) for item in node.elts
            )) if node.elts else set()
        if isinstance(node, ast.Dict):
            items = [*node.keys, *node.values]
            return set().union(*(
                import_origin_names(item)
                for item in items
                if item is not None
            )) if items else set()
        if isinstance(node, (ast.Starred, ast.NamedExpr, ast.Subscript)):
            return import_origin_names(node.value)
        if isinstance(node, ast.IfExp):
            return (
                import_origin_names(node.body)
                | import_origin_names(node.orelse)
            )
        return set()

    def qualified_import_attribute_names(node: ast.Attribute) -> set[str]:
        return import_origin_names(node)

    callable_nodes = {
        node for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        )
    }
    class_nodes = {
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }

    def enclosing_callable(node: ast.AST) -> ast.AST | None:
        parent = parents.get(node)
        while parent is not None and parent not in callable_nodes:
            parent = parents.get(parent)
        return parent

    callable_parents = {
        local_callable: enclosing_callable(local_callable)
        for local_callable in callable_nodes
    }
    scoped_tracked_bindings = {
        local_callable: set()
        for local_callable in callable_nodes
    }
    tracked_return_callables: set[ast.AST] = set()

    def target_names(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name):
            return {node.id}
        if isinstance(node, (ast.List, ast.Tuple)):
            return set().union(*(target_names(item) for item in node.elts))
        return set()

    def is_in_unmodeled_class_namespace(node: ast.AST) -> bool:
        parent = parents.get(node)
        while parent is not None and parent not in callable_nodes:
            if isinstance(parent, ast.ClassDef):
                return True
            parent = parents.get(parent)
        return False

    scopes: set[ast.AST | None] = {None, *callable_nodes}
    scope_bound_names = {scope: set() for scope in scopes}
    scope_import_names = {scope: set() for scope in scopes}
    scope_global_names = {scope: set() for scope in scopes}
    scope_nonlocal_names = {scope: set() for scope in scopes}
    callable_bindings: dict[
        ast.AST | None,
        dict[
            str,
            set[tuple[
                ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
                bool,
            ]],
        ],
    ] = {scope: {} for scope in scopes}

    def bind_callable(
            scope: ast.AST | None,
            name: str,
            local_callable: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
            bound_receiver: bool = False,
    ) -> bool:
        bindings = callable_bindings[scope].setdefault(name, set())
        target = (local_callable, bound_receiver)
        if target in bindings:
            return False
        bindings.add(target)
        return True

    for local_callable in callable_nodes:
        arguments = local_callable.args
        scope_bound_names[local_callable].update(
            argument.arg
            for argument in (
                arguments.posonlyargs
                + arguments.args
                + arguments.kwonlyargs
            )
        )
        if arguments.vararg is not None:
            scope_bound_names[local_callable].add(arguments.vararg.arg)
        if arguments.kwarg is not None:
            scope_bound_names[local_callable].add(arguments.kwarg.arg)
        if (
            isinstance(local_callable, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not is_in_unmodeled_class_namespace(local_callable)
        ):
            definition_scope = callable_parents[local_callable]
            scope_bound_names[definition_scope].add(local_callable.name)
            bind_callable(
                definition_scope,
                local_callable.name,
                local_callable,
            )

    alias_assignments = []
    for node in ast.walk(tree):
        if is_in_unmodeled_class_namespace(node):
            continue
        scope = enclosing_callable(node)
        if isinstance(node, ast.Assign):
            alias_assignments.append((scope, node.targets, node.value))
            scope_bound_names[scope].update(
                set().union(*(target_names(target) for target in node.targets))
            )
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            if node.value is not None:
                alias_assignments.append((scope, [node.target], node.value))
            scope_bound_names[scope].update(target_names(node.target))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            scope_bound_names[scope].update(target_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    scope_bound_names[scope].update(
                        target_names(item.optional_vars)
                    )
        elif isinstance(node, ast.ExceptHandler) and node.name:
            scope_bound_names[scope].add(node.name)
        elif isinstance(node, ast.Import):
            imported_names = {
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
            }
            scope_bound_names[scope].update(imported_names)
            scope_import_names[scope].update(imported_names)
        elif isinstance(node, ast.ImportFrom):
            imported_names = {
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            }
            scope_bound_names[scope].update(imported_names)
            scope_import_names[scope].update(imported_names)
        elif isinstance(node, ast.Global):
            scope_global_names[scope].update(node.names)
        elif isinstance(node, ast.Nonlocal):
            scope_nonlocal_names[scope].update(node.names)
        elif isinstance(node, ast.ClassDef):
            scope_bound_names[scope].add(node.name)

    class_bindings: dict[ast.AST | None, dict[str, set[ast.ClassDef]]] = {
        scope: {} for scope in scopes
    }
    instance_bindings: dict[ast.AST | None, dict[str, set[ast.ClassDef]]] = {
        scope: {} for scope in scopes
    }

    def bind_class_value(
            bindings_by_scope: dict[
                ast.AST | None,
                dict[str, set[ast.ClassDef]],
            ],
            scope: ast.AST | None,
            name: str,
            class_node: ast.ClassDef,
    ) -> bool:
        bindings = bindings_by_scope[scope].setdefault(name, set())
        if class_node in bindings:
            return False
        bindings.add(class_node)
        return True

    for class_node in class_nodes:
        if is_in_unmodeled_class_namespace(class_node):
            continue
        bind_class_value(
            class_bindings,
            enclosing_callable(class_node),
            class_node.name,
            class_node,
        )

    def resolve_scoped_classes(
            name: str,
            scope: ast.AST | None,
            bindings_by_scope: dict[
                ast.AST | None,
                dict[str, set[ast.ClassDef]],
            ],
    ) -> set[ast.ClassDef]:
        while True:
            if name in scope_bound_names[scope]:
                return set(bindings_by_scope[scope].get(name, ()))
            if scope is None:
                return set()
            scope = callable_parents[scope]

    def resolve_class_expression(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> set[ast.ClassDef]:
        if isinstance(node, ast.Name):
            return resolve_scoped_classes(node.id, scope, class_bindings)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return set().union(*(
                resolve_class_expression(item, scope)
                for item in node.elts
            )) if node.elts else set()
        if isinstance(node, ast.Dict):
            return set().union(*(
                resolve_class_expression(value, scope)
                for value in node.values
            )) if node.values else set()
        if isinstance(node, (ast.Starred, ast.NamedExpr, ast.Subscript)):
            return resolve_class_expression(node.value, scope)
        if isinstance(node, ast.IfExp):
            return (
                resolve_class_expression(node.body, scope)
                | resolve_class_expression(node.orelse, scope)
            )
        return set()

    def resolve_instance_expression(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> set[ast.ClassDef]:
        if isinstance(node, ast.Name):
            return resolve_scoped_classes(node.id, scope, instance_bindings)
        if isinstance(node, ast.Call):
            return resolve_class_expression(node.func, scope)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return set().union(*(
                resolve_instance_expression(item, scope)
                for item in node.elts
            )) if node.elts else set()
        if isinstance(node, ast.Dict):
            return set().union(*(
                resolve_instance_expression(value, scope)
                for value in node.values
            )) if node.values else set()
        if isinstance(node, (ast.Starred, ast.NamedExpr, ast.Subscript)):
            return resolve_instance_expression(node.value, scope)
        if isinstance(node, ast.IfExp):
            return (
                resolve_instance_expression(node.body, scope)
                | resolve_instance_expression(node.orelse, scope)
            )
        return set()

    class_aliases_changed = True
    while class_aliases_changed:
        class_aliases_changed = False
        for scope, targets, value in alias_assignments:
            names = set().union(*(
                target_names(target) for target in targets
            ))
            for class_node in resolve_class_expression(value, scope):
                for name in names:
                    class_aliases_changed |= bind_class_value(
                        class_bindings,
                        scope,
                        name,
                        class_node,
                    )
            for class_node in resolve_instance_expression(value, scope):
                for name in names:
                    class_aliases_changed |= bind_class_value(
                        instance_bindings,
                        scope,
                        name,
                        class_node,
                    )

    class_methods: dict[
        ast.ClassDef,
        dict[str, set[ast.FunctionDef | ast.AsyncFunctionDef]],
    ] = {class_node: {} for class_node in class_nodes}
    class_member_names = {class_node: set() for class_node in class_nodes}

    def enclosing_class_namespace(node: ast.AST) -> ast.ClassDef | None:
        parent = parents.get(node)
        while parent is not None:
            if isinstance(parent, ast.ClassDef):
                return parent
            if parent in callable_nodes:
                return None
            parent = parents.get(parent)
        return None

    for node in ast.walk(tree):
        class_node = enclosing_class_namespace(node)
        if class_node is None:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            class_member_names[class_node].add(node.name)
        elif isinstance(node, ast.Assign):
            class_member_names[class_node].update(set().union(*(
                target_names(target) for target in node.targets
            )))
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            class_member_names[class_node].update(target_names(node.target))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            class_member_names[class_node].update(target_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    class_member_names[class_node].update(
                        target_names(item.optional_vars)
                    )
        elif isinstance(node, ast.ExceptHandler) and node.name:
            class_member_names[class_node].add(node.name)
        elif isinstance(node, ast.Import):
            class_member_names[class_node].update(
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            class_member_names[class_node].update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            )

    for class_node in class_nodes:
        for statement in class_node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_methods[class_node].setdefault(
                    statement.name,
                    set(),
                ).add(statement)

    class_bases: dict[ast.ClassDef, tuple[ast.ClassDef, ...]] = {}
    class_base_resolution_complete: dict[ast.ClassDef, bool] = {}
    for class_node in class_nodes:
        bases = []
        complete = True
        for base_expression in class_node.bases:
            resolved_bases = sorted(
                resolve_class_expression(
                    base_expression,
                    enclosing_callable(class_node),
                ),
                key=lambda item: (item.lineno, item.col_offset),
            )
            if len(resolved_bases) != 1:
                complete = False
            for base in resolved_bases:
                if base in bases:
                    complete = False
                else:
                    bases.append(base)
        class_bases[class_node] = tuple(bases)
        class_base_resolution_complete[class_node] = complete

    class_mro_cache: dict[
        ast.ClassDef,
        tuple[ast.ClassDef, ...] | None,
    ] = {}

    def local_c3_mro(
            class_node: ast.ClassDef,
            resolving: frozenset[ast.ClassDef] = frozenset(),
    ) -> tuple[ast.ClassDef, ...] | None:
        if class_node in class_mro_cache:
            return class_mro_cache[class_node]
        if (
            class_node in resolving
            or not class_base_resolution_complete[class_node]
        ):
            class_mro_cache[class_node] = None
            return None
        resolving = resolving | {class_node}
        base_mros = []
        for base in class_bases[class_node]:
            base_mro = local_c3_mro(base, resolving)
            if base_mro is None:
                class_mro_cache[class_node] = None
                return None
            base_mros.append(list(base_mro))
        sequences = base_mros + [list(class_bases[class_node])]
        result = [class_node]
        while any(sequences):
            sequences = [sequence for sequence in sequences if sequence]
            candidate = next((
                sequence[0]
                for sequence in sequences
                if all(
                    sequence[0] not in other[1:]
                    for other in sequences
                )
            ), None)
            if candidate is None:
                class_mro_cache[class_node] = None
                return None
            result.append(candidate)
            for sequence in sequences:
                if sequence and sequence[0] is candidate:
                    sequence.pop(0)
        resolved = tuple(result)
        class_mro_cache[class_node] = resolved
        return resolved

    def conservative_local_methods(
            class_node: ast.ClassDef,
            method_name: str,
            visited: frozenset[ast.ClassDef] = frozenset(),
    ) -> set[ast.FunctionDef | ast.AsyncFunctionDef]:
        if class_node in visited:
            return set()
        if method_name in class_member_names[class_node]:
            return set(class_methods[class_node].get(method_name, ()))
        visited = visited | {class_node}
        return set().union(*(
            conservative_local_methods(base, method_name, visited)
            for base in class_bases[class_node]
        )) if class_bases[class_node] else set()

    def resolve_class_methods(
            class_node: ast.ClassDef,
            method_name: str,
    ) -> set[ast.FunctionDef | ast.AsyncFunctionDef]:
        mro = local_c3_mro(class_node)
        if mro is None:
            return conservative_local_methods(class_node, method_name)
        for candidate in mro:
            if method_name in class_member_names[candidate]:
                return set(class_methods[candidate].get(method_name, ()))
        return set()

    def method_descriptor_kind(
            method: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        decorator_names = {
            origin.rsplit(".", 1)[-1]
            for decorator in method.decorator_list
            for origin in import_origin_names(decorator)
        }
        if "staticmethod" in decorator_names:
            return "static"
        if "classmethod" in decorator_names:
            return "class"
        return "instance"

    def resolve_method_attribute(
            node: ast.Attribute,
            scope: ast.AST | None,
    ) -> set[tuple[ast.FunctionDef | ast.AsyncFunctionDef, bool]]:
        resolved = set()
        for class_node in resolve_class_expression(node.value, scope):
            for method in resolve_class_methods(class_node, node.attr):
                resolved.add((
                    method,
                    method_descriptor_kind(method) == "class",
                ))
        for class_node in resolve_instance_expression(node.value, scope):
            for method in resolve_class_methods(class_node, node.attr):
                resolved.add((
                    method,
                    method_descriptor_kind(method) != "static",
                ))
        return resolved

    def resolve_callable_name(
            name: str,
            scope: ast.AST | None,
    ) -> set[tuple[
        ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        bool,
    ]]:
        while True:
            if name in scope_bound_names[scope]:
                return set(callable_bindings[scope].get(name, ()))
            if scope is None:
                return set()
            scope = callable_parents[scope]

    def resolve_callable_expression(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> set[tuple[
        ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        bool,
    ]]:
        if isinstance(node, ast.Name):
            return resolve_callable_name(node.id, scope)
        if isinstance(node, ast.Lambda):
            return {(node, False)}
        if isinstance(node, ast.Attribute):
            return set(resolve_method_attribute(node, scope))
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return set().union(*(
                resolve_callable_expression(item, scope)
                for item in node.elts
            )) if node.elts else set()
        if isinstance(node, ast.Dict):
            return set().union(*(
                resolve_callable_expression(value, scope)
                for value in node.values
            )) if node.values else set()
        if isinstance(node, (ast.Starred, ast.NamedExpr, ast.Subscript)):
            return resolve_callable_expression(node.value, scope)
        if isinstance(node, ast.IfExp):
            return (
                resolve_callable_expression(node.body, scope)
                | resolve_callable_expression(node.orelse, scope)
            )
        return set()

    aliases_changed = True
    while aliases_changed:
        aliases_changed = False
        for scope, targets, value in alias_assignments:
            resolved = resolve_callable_expression(value, scope)
            if not resolved:
                continue
            for name in set().union(*(
                target_names(target) for target in targets
            )):
                for local_callable, bound_receiver in resolved:
                    aliases_changed |= bind_callable(
                        scope,
                        name,
                        local_callable,
                        bound_receiver,
                    )

    def local_call_targets(
            call: ast.Call,
    ) -> tuple[tuple[
        ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        bool,
    ], ...]:
        return tuple(resolve_callable_expression(
            call.func,
            enclosing_callable(call),
        ))

    def local_constructor_targets(
            call: ast.Call,
    ) -> tuple[tuple[
        ast.FunctionDef | ast.AsyncFunctionDef,
        bool,
    ], ...]:
        targets = set()
        scope = enclosing_callable(call)
        for class_node in resolve_class_expression(call.func, scope):
            for allocator in resolve_class_methods(class_node, "__new__"):
                targets.add((
                    allocator,
                    2 if method_descriptor_kind(allocator) == "class" else 1,
                ))
            for initializer in resolve_class_methods(class_node, "__init__"):
                targets.add((
                    initializer,
                    method_descriptor_kind(initializer) != "static",
                ))
        return tuple(targets)

    def contains_tracked_binding(
            node: ast.AST,
            scope: ast.AST | None = None,
    ) -> bool:
        def is_tracked_name(item: ast.Name) -> bool:
            item_scope = scope
            while item_scope is not None:
                if item.id in scope_global_names[item_scope]:
                    item_scope = None
                    break
                if item.id in scope_nonlocal_names[item_scope]:
                    item_scope = callable_parents[item_scope]
                    continue
                if item.id in scope_bound_names[item_scope]:
                    return (
                        item.id in scoped_tracked_bindings[item_scope]
                        or item.id in scope_import_names[item_scope]
                    )
                item_scope = callable_parents[item_scope]
            return item.id in tracked_bindings

        return any(
            isinstance(item, ast.Name)
            and isinstance(item.ctx, ast.Load)
            and is_tracked_name(item)
            for item in ast.walk(node)
        )

    def contains_passed_tracked_binding(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> bool:
        callable_references = {
            item
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            for item in ast.walk(call.func)
        }
        return any(
            isinstance(item, ast.Name)
            and isinstance(item.ctx, ast.Load)
            and item not in callable_references
            and contains_tracked_binding(item, scope)
            for item in ast.walk(node)
        )

    def contains_assignment_tracked_binding(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> bool:
        def contains_local_tracked_return(item: ast.AST) -> bool:
            if isinstance(item, ast.Call):
                return any(
                    local_callable in tracked_return_callables
                    for local_callable, _ in local_call_targets(item)
                )
            if isinstance(item, (ast.List, ast.Set, ast.Tuple)):
                return any(
                    contains_local_tracked_return(element)
                    for element in item.elts
                )
            if isinstance(item, ast.Dict):
                return any(
                    contains_local_tracked_return(element)
                    for element in (*item.keys, *item.values)
                    if element is not None
                )
            if isinstance(item, (ast.NamedExpr, ast.Starred)):
                return contains_local_tracked_return(item.value)
            if isinstance(item, ast.IfExp):
                return (
                    contains_local_tracked_return(item.body)
                    or contains_local_tracked_return(item.orelse)
                )
            return False

        return contains_local_tracked_return(node) or (
            not any(isinstance(item, ast.Call) for item in ast.walk(node))
            and contains_tracked_binding(node, scope)
        )

    def callable_parameter_bindings(
            node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
    ) -> tuple[
        list[ast.arg],
        dict[str, ast.arg],
        ast.arg | None,
        ast.arg | None,
        tuple[tuple[ast.arg, ast.expr], ...],
    ]:
        arguments = node.args
        positional = arguments.posonlyargs + arguments.args
        named = {
            argument.arg: argument
            for argument in positional + arguments.kwonlyargs
        }
        defaults = tuple(zip(
            positional[-len(arguments.defaults):],
            arguments.defaults,
        )) if arguments.defaults else ()
        defaults += tuple(
            (argument, default)
            for argument, default in zip(
                arguments.kwonlyargs,
                arguments.kw_defaults,
            )
            if default is not None
        )
        return (
            positional,
            named,
            arguments.vararg,
            arguments.kwarg,
            defaults,
        )

    def higher_order_builtin_kind(call: ast.Call) -> str | None:
        origins = import_origin_names(call.func)
        if "builtins.map" in origins:
            return "map"
        if "builtins.filter" in origins:
            return "filter"
        if "builtins.sorted" in origins:
            return "sorted"
        return None

    literal_sequence_bindings: dict[
        ast.AST | None,
        dict[str, set[tuple[ast.AST, ...]]],
    ] = {scope: {} for scope in scopes}

    def bind_literal_sequence(
            scope: ast.AST | None,
            name: str,
            sequence: tuple[ast.AST, ...],
    ) -> bool:
        bindings = literal_sequence_bindings[scope].setdefault(name, set())
        if sequence in bindings:
            return False
        bindings.add(sequence)
        return True

    def resolve_literal_sequence_name(
            name: str,
            scope: ast.AST | None,
    ) -> set[tuple[ast.AST, ...]]:
        while True:
            if name in scope_bound_names[scope]:
                return set(literal_sequence_bindings[scope].get(name, ()))
            if scope is None:
                return set()
            scope = callable_parents[scope]

    def resolve_literal_sequences(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> set[tuple[ast.AST, ...]]:
        if isinstance(node, ast.Name):
            return resolve_literal_sequence_name(node.id, scope)
        if isinstance(node, (ast.List, ast.Tuple)):
            return {tuple(node.elts)}
        if isinstance(node, ast.NamedExpr):
            return resolve_literal_sequences(node.value, scope)
        if isinstance(node, ast.IfExp):
            return (
                resolve_literal_sequences(node.body, scope)
                | resolve_literal_sequences(node.orelse, scope)
            )
        return set()

    literal_sequences_changed = True
    while literal_sequences_changed:
        literal_sequences_changed = False
        for scope, targets, value in alias_assignments:
            sequences = resolve_literal_sequences(value, scope)
            if not sequences:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                for sequence in sequences:
                    literal_sequences_changed |= bind_literal_sequence(
                        scope,
                        target.id,
                        sequence,
                    )

    literal_mapping_bindings: dict[
        ast.AST | None,
        dict[str, set[tuple[tuple[str, ast.AST], ...]]],
    ] = {scope: {} for scope in scopes}

    def bind_literal_mapping(
            scope: ast.AST | None,
            name: str,
            mapping: tuple[tuple[str, ast.AST], ...],
    ) -> bool:
        bindings = literal_mapping_bindings[scope].setdefault(name, set())
        if mapping in bindings:
            return False
        bindings.add(mapping)
        return True

    def resolve_literal_mapping_name(
            name: str,
            scope: ast.AST | None,
    ) -> set[tuple[tuple[str, ast.AST], ...]]:
        while True:
            if name in scope_bound_names[scope]:
                return set(literal_mapping_bindings[scope].get(name, ()))
            if scope is None:
                return set()
            scope = callable_parents[scope]

    def resolve_literal_mappings(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> set[tuple[tuple[str, ast.AST], ...]]:
        if isinstance(node, ast.Name):
            return resolve_literal_mapping_name(node.id, scope)
        if isinstance(node, ast.Dict):
            if any(
                not isinstance(key, ast.Constant)
                or not isinstance(key.value, str)
                for key in node.keys
            ):
                return set()
            values_by_key = {
                key.value: value
                for key, value in zip(node.keys, node.values)
            }
            return {tuple(values_by_key.items())}
        return set()

    literal_mappings_changed = True
    while literal_mappings_changed:
        literal_mappings_changed = False
        for scope, targets, value in alias_assignments:
            mappings = resolve_literal_mappings(value, scope)
            if not mappings:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                for mapping in mappings:
                    literal_mappings_changed |= bind_literal_mapping(
                        scope,
                        target.id,
                        mapping,
                    )

    def normalized_higher_order_args(
            call: ast.Call,
    ) -> set[tuple[ast.AST, ...]]:
        variants = {()}
        scope = enclosing_callable(call)
        for argument in call.args:
            expansions = (
                resolve_literal_sequences(argument.value, scope)
                if isinstance(argument, ast.Starred)
                else {(argument,)}
            )
            if not expansions:
                return set()
            variants = {
                prefix + expansion
                for prefix in variants
                for expansion in expansions
            }
        return variants

    def normalized_sorted_key_values(
            call: ast.Call,
    ) -> set[tuple[ast.AST, ...]]:
        variants = {()}
        scope = enclosing_callable(call)
        for keyword in call.keywords:
            if keyword.arg == "key":
                expansions = {(keyword.value,)}
            elif keyword.arg is None:
                mappings = resolve_literal_mappings(keyword.value, scope)
                if not mappings:
                    return set()
                expansions = {
                    tuple(
                        value for name, value in mapping
                        if name == "key"
                    )
                    for mapping in mappings
                }
            else:
                expansions = {()}
            variants = {
                prefix + expansion
                for prefix in variants
                for expansion in expansions
            }
        return variants

    def contains_direct_higher_order_input(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> bool:
        if isinstance(node, ast.Call):
            return any(
                local_callable in tracked_return_callables
                for local_callable, _ in local_call_targets(node)
            )
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            return contains_direct_higher_order_input(node.value, scope)
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            return any(
                contains_direct_higher_order_input(item, scope)
                for item in node.elts
            )
        if isinstance(node, ast.Dict):
            return any(
                contains_direct_higher_order_input(item, scope)
                for item in (*node.keys, *node.values)
                if item is not None
            )
        if isinstance(node, (ast.NamedExpr, ast.Starred)):
            return contains_direct_higher_order_input(node.value, scope)
        if isinstance(node, ast.IfExp):
            return (
                contains_direct_higher_order_input(node.body, scope)
                or contains_direct_higher_order_input(node.orelse, scope)
            )
        return contains_passed_tracked_binding(node, scope)

    def additional_higher_order_kind(call: ast.Call) -> str | None:
        origins = import_origin_names(call.func)
        if "builtins.min" in origins:
            return "min"
        if "builtins.max" in origins:
            return "max"
        if "functools.reduce" in origins:
            return "reduce"
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "sort"
            and resolve_literal_sequences(
                call.func.value,
                enclosing_callable(call),
            )
        ):
            return "list-sort"
        return None

    forced_higher_order_findings: set[ast.Call] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            value = None
            targets = []
            if isinstance(node, ast.Assign):
                value = node.value
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                value = node.value
                targets = [node.target]
            elif isinstance(node, ast.NamedExpr):
                value = node.value
                targets = [node.target]
            elif isinstance(node, ast.AugAssign) and isinstance(
                node.target,
                ast.Name,
            ):
                value = node.value
                targets = [node.target]
            if (
                value is None
                or not contains_assignment_tracked_binding(
                    value,
                    enclosing_callable(node),
                )
            ):
                continue
            new_names = set().union(*(target_names(target) for target in targets))
            scope = enclosing_callable(node)
            scope_bindings = (
                tracked_bindings
                if scope is None
                else scoped_tracked_bindings[scope]
            )
            if not new_names.issubset(scope_bindings):
                scope_bindings.update(new_names)
                changed = True

        for call in (
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (local_call_targets(node) or local_constructor_targets(node))
        ):
            call_targets = {
                *local_call_targets(call),
                *local_constructor_targets(call),
            }
            for local_callable, bound_receiver in call_targets:
                (
                    positional,
                    named,
                    vararg,
                    kwarg,
                    defaults,
                ) = callable_parameter_bindings(local_callable)
                receiver_names = {
                    parameter.arg
                    for parameter in positional[:int(bound_receiver)]
                }
                newly_tracked = {
                    parameter.arg
                    for parameter, default in defaults
                    if parameter.arg not in receiver_names
                    if contains_passed_tracked_binding(
                        default,
                        callable_parents[local_callable],
                    )
                }
                for index, argument in enumerate(call.args):
                    if not contains_passed_tracked_binding(
                        argument,
                        enclosing_callable(call),
                    ):
                        continue
                    if isinstance(argument, ast.Starred):
                        newly_tracked.update(
                            parameter.arg
                            for parameter in positional[int(bound_receiver):]
                        )
                        if vararg is not None:
                            newly_tracked.add(vararg.arg)
                    elif index + int(bound_receiver) < len(positional):
                        newly_tracked.add(
                            positional[index + int(bound_receiver)].arg
                        )
                    elif vararg is not None:
                        newly_tracked.add(vararg.arg)
                for keyword in call.keywords:
                    if not contains_passed_tracked_binding(
                        keyword.value,
                        enclosing_callable(call),
                    ):
                        continue
                    if keyword.arg is None:
                        newly_tracked.update(
                            name for name in named
                            if not (
                                bound_receiver
                                and positional
                                and name in receiver_names
                            )
                        )
                        if kwarg is not None:
                            newly_tracked.add(kwarg.arg)
                    elif (
                        keyword.arg in named
                        and keyword.arg not in receiver_names
                    ):
                        newly_tracked.add(named[keyword.arg].arg)
                    elif kwarg is not None:
                        newly_tracked.add(kwarg.arg)
                local_bindings = scoped_tracked_bindings[local_callable]
                if not newly_tracked.issubset(local_bindings):
                    local_bindings.update(newly_tracked)
                    changed = True

        for call in (
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and higher_order_builtin_kind(node) is not None
        ):
            kind = higher_order_builtin_kind(call)
            if (
                kind == "sorted"
                and any(
                    keyword.arg is None
                    and not resolve_literal_mappings(
                        keyword.value,
                        enclosing_callable(call),
                    )
                    for keyword in call.keywords
                )
                and any(
                    len(normalized_args) == 1
                    and contains_direct_higher_order_input(
                        normalized_args[0],
                        enclosing_callable(call),
                    )
                    for normalized_args in normalized_higher_order_args(call)
                )
            ):
                forced_higher_order_findings.add(call)
            for normalized_args in normalized_higher_order_args(call):
                if kind == "sorted":
                    callback_variants = normalized_sorted_key_values(call)
                    if len(normalized_args) != 1:
                        continue
                else:
                    if len(normalized_args) < 2:
                        continue
                    callback_variants = {(normalized_args[0],)}
                for callback_expressions in callback_variants:
                    if len(callback_expressions) != 1:
                        continue
                    iterable_arguments = (
                        normalized_args
                        if kind == "sorted"
                        else normalized_args[1:]
                    )
                    callback_targets = set().union(*(
                        resolve_callable_expression(
                            expression,
                            enclosing_callable(call),
                        )
                        for expression in callback_expressions
                    ))
                    for local_callable, bound_receiver in callback_targets:
                        positional, _, vararg, _, _ = callable_parameter_bindings(
                            local_callable
                        )
                        available = positional[int(bound_receiver):]
                        newly_tracked = set()
                        if kind in ("filter", "sorted"):
                            if any(
                                contains_passed_tracked_binding(
                                    argument,
                                    enclosing_callable(call),
                                )
                                for argument in iterable_arguments
                            ):
                                if available:
                                    newly_tracked.add(available[0].arg)
                                elif vararg is not None:
                                    newly_tracked.add(vararg.arg)
                        else:
                            for index, argument in enumerate(iterable_arguments):
                                if not contains_passed_tracked_binding(
                                    argument,
                                    enclosing_callable(call),
                                ):
                                    continue
                                if isinstance(argument, ast.Starred):
                                    newly_tracked.update(
                                        parameter.arg for parameter in available
                                    )
                                    if vararg is not None:
                                        newly_tracked.add(vararg.arg)
                                elif index < len(available):
                                    newly_tracked.add(available[index].arg)
                                elif vararg is not None:
                                    newly_tracked.add(vararg.arg)
                        local_bindings = scoped_tracked_bindings[local_callable]
                        if not newly_tracked.issubset(local_bindings):
                            local_bindings.update(newly_tracked)
                            changed = True

        for call in (
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and additional_higher_order_kind(node) is not None
        ):
            kind = additional_higher_order_kind(call)
            scope = enclosing_callable(call)
            unresolved_keywords = any(
                keyword.arg is None
                and not resolve_literal_mappings(keyword.value, scope)
                for keyword in call.keywords
            )
            for normalized_args in normalized_higher_order_args(call):
                if kind == "list-sort":
                    carriers = (call.func.value,)
                elif kind == "reduce":
                    carriers = normalized_args[1:3]
                else:
                    carriers = normalized_args
                has_tracked_carrier = any(
                    contains_direct_higher_order_input(carrier, scope)
                    for carrier in carriers
                )
                if has_tracked_carrier and unresolved_keywords:
                    forced_higher_order_findings.add(call)

                if kind == "reduce":
                    if len(normalized_args) < 2:
                        continue
                    callback_expressions = {normalized_args[0]}
                    tracked_parameter_indexes = set()
                    if contains_direct_higher_order_input(
                        normalized_args[1], scope,
                    ):
                        tracked_parameter_indexes.update((0, 1))
                    if (
                        len(normalized_args) >= 3
                        and contains_direct_higher_order_input(
                            normalized_args[2], scope,
                        )
                    ):
                        tracked_parameter_indexes.add(0)
                else:
                    callback_variants = normalized_sorted_key_values(call)
                    callback_expressions = {
                        variant[0]
                        for variant in callback_variants
                        if len(variant) == 1
                    }
                    tracked_parameter_indexes = {0} if has_tracked_carrier else set()
                if (
                    not callback_expressions
                    or not tracked_parameter_indexes
                ):
                    continue
                callback_targets = set().union(*(
                    resolve_callable_expression(expression, scope)
                    for expression in callback_expressions
                ))
                for local_callable, bound_receiver in callback_targets:
                    positional, _, vararg, _, _ = callable_parameter_bindings(
                        local_callable
                    )
                    available = positional[int(bound_receiver):]
                    newly_tracked = {
                        available[index].arg
                        for index in tracked_parameter_indexes
                        if index < len(available)
                    }
                    if (
                        vararg is not None
                        and any(
                            index >= len(available)
                            for index in tracked_parameter_indexes
                        )
                    ):
                        newly_tracked.add(vararg.arg)
                    local_bindings = scoped_tracked_bindings[local_callable]
                    if not newly_tracked.issubset(local_bindings):
                        local_bindings.update(newly_tracked)
                        changed = True

        for local_callable in callable_nodes:
            if isinstance(local_callable, ast.Lambda):
                returned_values = (local_callable.body,)
            else:
                returned_values = tuple(
                    node.value
                    for node in ast.walk(local_callable)
                    if isinstance(node, ast.Return)
                    and node.value is not None
                    and enclosing_callable(node) is local_callable
                )
            if (
                local_callable not in tracked_return_callables
                and any(
                    contains_assignment_tracked_binding(
                        returned_value,
                        local_callable,
                    )
                    for returned_value in returned_values
                )
            ):
                tracked_return_callables.add(local_callable)
                changed = True

    def contains_persistent_target(node: ast.AST) -> bool:
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            return True
        if isinstance(node, ast.Starred):
            return contains_persistent_target(node.value)
        if isinstance(node, (ast.List, ast.Tuple)):
            return any(contains_persistent_target(item) for item in node.elts)
        return False

    def carries_state_escape_value(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> bool:
        def direct_tracked_roots(argument: ast.AST) -> set[str]:
            if isinstance(argument, ast.Name):
                return (
                    {argument.id}
                    if contains_tracked_binding(argument, scope)
                    else set()
                )
            if isinstance(argument, (ast.Attribute, ast.Subscript)):
                return direct_tracked_roots(argument.value)
            if isinstance(argument, (ast.List, ast.Tuple, ast.Set)):
                return set().union(*(
                    direct_tracked_roots(item) for item in argument.elts
                )) if argument.elts else set()
            if isinstance(argument, ast.Dict):
                return set().union(*(
                    direct_tracked_roots(item)
                    for item in (*argument.keys, *argument.values)
                    if item is not None
                )) if argument.keys or argument.values else set()
            if isinstance(argument, (ast.Starred, ast.NamedExpr)):
                return direct_tracked_roots(argument.value)
            if isinstance(argument, ast.IfExp):
                return (
                    direct_tracked_roots(argument.body)
                    | direct_tracked_roots(argument.orelse)
                )
            return set()

        def expression_carries_value(expression: ast.AST) -> bool:
            if direct_tracked_roots(expression):
                return True
            if isinstance(expression, (
                ast.Attribute,
                ast.NamedExpr,
                ast.Starred,
                ast.Subscript,
            )):
                return expression_carries_value(expression.value)
            if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
                return any(
                    expression_carries_value(item)
                    for item in expression.elts
                )
            if isinstance(expression, ast.Dict):
                return any(
                    expression_carries_value(item)
                    for item in (*expression.keys, *expression.values)
                    if item is not None
                )
            if isinstance(expression, ast.IfExp):
                return (
                    expression_carries_value(expression.body)
                    or expression_carries_value(expression.orelse)
                )
            if not isinstance(expression, ast.Call):
                return False
            local_targets = local_call_targets(expression)
            if local_targets:
                return any(
                    local_callable in tracked_return_callables
                    for local_callable, _ in local_targets
                )
            if not isinstance(expression.func, (ast.Name, ast.Attribute)):
                return False
            local_classes = resolve_class_expression(expression.func, scope)
            if local_classes and not any(
                resolve_class_methods(class_node, "__init__")
                for class_node in local_classes
            ):
                return False
            if isinstance(expression.func, ast.Name):
                public_name = expression.func.id.lstrip("_")
                if (
                    not local_classes
                    and public_name
                    and public_name[0].isupper()
                ):
                    return False
            else:
                receiver = expression.func.value

                def name_is_lexically_bound(name: str) -> bool:
                    name_scope = scope
                    while name_scope is not None:
                        if name in scope_global_names[name_scope]:
                            name_scope = None
                            break
                        if name in scope_nonlocal_names[name_scope]:
                            name_scope = callable_parents[name_scope]
                            continue
                        if name in scope_bound_names[name_scope]:
                            return True
                        name_scope = callable_parents[name_scope]
                    return name in scope_bound_names[None]

                receiver_names = {
                    item.id
                    for item in ast.walk(receiver)
                    if isinstance(item, ast.Name)
                }
                receiver_is_unresolved = any(
                    not name_is_lexically_bound(name)
                    for name in receiver_names
                )
                if not (
                    import_origin_names(receiver)
                    or direct_tracked_roots(receiver)
                    or receiver_is_unresolved
                ):
                    return False
            arguments = (
                *expression.args,
                *(keyword.value for keyword in expression.keywords),
            )
            callable_names = {
                item.id
                for item in ast.walk(expression.func)
                if isinstance(item, ast.Name)
            }
            for argument in arguments:
                argument_roots = direct_tracked_roots(argument)
                if argument_roots:
                    if argument_roots - callable_names:
                        return True
                elif expression_carries_value(argument):
                    return True
            return False

        return (
            contains_assignment_tracked_binding(node, scope)
            or expression_carries_value(node)
        )

    exact_setter_origins = {
        "builtins.setattr",
        "builtins.object.__setattr__",
        "builtins.type.__setattr__",
    }
    mutator_stored_positions = {
        "append": {0},
        "extend": {0},
        "insert": {1},
        "add": {0},
        "update": None,
        "setdefault": {0, 1},
        "__setitem__": {0, 1},
    }
    mutator_stored_keywords = {
        "append": {"item", "object", "value"},
        "extend": {"items", "iterable", "values"},
        "insert": {"item", "object", "value"},
        "add": {"element", "item", "value"},
        "update": None,
        "setdefault": {"default", "key"},
        "__setitem__": {"key", "value"},
    }

    def normalized_positional_values(
            call: ast.Call,
    ) -> tuple[tuple[ast.AST, ...], tuple[ast.AST, ...]]:
        values = []
        unresolved_starred = []

        def append_argument(argument: ast.AST) -> None:
            if not isinstance(argument, ast.Starred):
                values.append(argument)
            elif isinstance(argument.value, (ast.List, ast.Tuple)):
                for item in argument.value.elts:
                    append_argument(item)
            else:
                unresolved_starred.append(argument.value)

        for argument in call.args:
            append_argument(argument)
        return tuple(values), tuple(unresolved_starred)

    def setter_stored_values(
            call: ast.Call,
    ) -> tuple[tuple[ast.AST, ...], tuple[ast.AST, ...]]:
        if local_call_targets(call):
            return (), ()
        positional, unresolved_starred = normalized_positional_values(call)
        origins = import_origin_names(call.func)
        if exact_setter_origins.intersection(origins):
            stored_index = 2
        elif (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "__setattr__"
        ):
            stored_index = 1
        else:
            return (), ()
        if unresolved_starred:
            return positional, unresolved_starred
        return (
            (positional[stored_index],)
            if len(positional) > stored_index
            else (),
            (),
        )

    def mutator_stored_values(
            call: ast.Call,
    ) -> tuple[tuple[ast.AST, ...], tuple[ast.AST, ...]]:
        if not isinstance(call.func, ast.Attribute) or local_call_targets(call):
            return (), ()
        method_name = call.func.attr
        if method_name not in mutator_stored_positions:
            return (), ()
        positional, unresolved_starred = normalized_positional_values(call)
        positions = mutator_stored_positions[method_name]
        positional_values = (
            positional
            if positions is None
            else tuple(
                argument
                for index, argument in enumerate(positional)
                if index in positions
            )
        )
        keyword_names = mutator_stored_keywords[method_name]
        keyword_values = tuple(
            keyword.value
            for keyword in call.keywords
            if (
                keyword.arg is None
                or keyword_names is None
                or keyword.arg in keyword_names
            )
        )
        if unresolved_starred:
            return positional + keyword_values, unresolved_starred
        return positional_values + keyword_values, ()

    findings = []
    for node in ast.walk(tree):
        if node in forced_higher_order_findings:
            findings.append(node)
        elif (
            isinstance(node, ast.Attribute)
            and contains_tracked_binding(
                node.value,
                enclosing_callable(node),
            )
            and (
                is_sensitive_import_name(node.attr)
                or node.attr.startswith("_")
                or any(
                    qualified_name in KNOWN_CONCURRENCY_FULL_IMPORT_NAMES
                    for qualified_name in qualified_import_attribute_names(node)
                )
            )
        ):
            findings.append(node)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"delattr", "getattr", "setattr", "vars"}
            and (
                node.func.id != "setattr"
                or "builtins.setattr" in import_origin_names(node.func)
            )
            and node.args
            and contains_tracked_binding(
                node.args[0],
                enclosing_callable(node),
            )
        ):
            findings.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            value = node.value
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            if (
                value is not None
                and any(contains_persistent_target(target) for target in targets)
                and carries_state_escape_value(
                    value,
                    enclosing_callable(node),
                )
            ):
                findings.append(node)
        elif (
            isinstance(node, ast.AugAssign)
            and contains_persistent_target(node.target)
            and carries_state_escape_value(
                node.value,
                enclosing_callable(node),
            )
        ):
            findings.append(node)
        elif isinstance(node, ast.Call):
            setter_values, setter_unresolved = setter_stored_values(node)
            mutator_values, mutator_unresolved = mutator_stored_values(node)
            if any(
                carries_state_escape_value(
                    stored_value,
                    enclosing_callable(node),
                )
                for stored_value in (
                    *setter_values,
                    *setter_unresolved,
                    *mutator_values,
                    *mutator_unresolved,
                )
            ):
                findings.append(node)
    return tuple(findings)


class H2D2FreezeContractTests(unittest.TestCase):
    def test_parser_and_reexport_guards_reject_ambiguous_inputs(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key: limit"):
            json.loads(
                '{"limit":99,"limit":2}',
                object_pairs_hook=reject_duplicate_json_object_pairs,
            )

        for source, imported_name in (
            (
                "from pathlib import posixpath as p\np.os.fork()\n",
                "pathlib.posixpath",
            ),
            (
                "from pathlib import posixpath as p\nq = p\nq.os.fork()\n",
                "pathlib.posixpath",
            ),
            (
                "from pathlib import posixpath as p\nq = [p]\nq[0].os.fork()\n",
                "pathlib.posixpath",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(value):\n    value.os.fork()\n"
                    "invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(*, value):\n    value.os.fork()\n"
                    "invoke(value=p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(value=p):\n    value.os.fork()\n"
                    "invoke()\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(*, value=p):\n    value.os.fork()\n"
                    "invoke()\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def identity(value):\n    return value\n"
                    "q = identity(p)\nq.os.fork()\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "(lambda value: value.os.fork())(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(value):\n    value.os.fork()\n"
                    "alias = invoke\nalias(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(value):\n    value.os.fork()\n"
                    "alias: object = invoke\nalias(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(value):\n    value.os.fork()\n"
                    "(alias := invoke)(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(value):\n    value.os.fork()\n"
                    "aliases = [invoke]\naliases[0](p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "def invoke(value):\n    value.os.fork()\n"
                    "aliases = {\"invoke\": invoke}\n"
                    "aliases[\"invoke\"](p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class Runner:\n"
                    "    @staticmethod\n"
                    "    def invoke(value):\n        value.os.fork()\n"
                    "Runner.invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class Runner:\n"
                    "    @classmethod\n"
                    "    def invoke(cls, value):\n        value.os.fork()\n"
                    "Runner.invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class Runner:\n"
                    "    def invoke(self, value):\n        value.os.fork()\n"
                    "runner = Runner()\n"
                    "alias = runner.invoke\nalias(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class Base:\n"
                    "    def invoke(self, value):\n        value.os.fork()\n"
                    "class Middle(Base):\n    pass\n"
                    "class Runner(Middle):\n    pass\n"
                    "Runner().invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class A:\n"
                    "    def invoke(self, value):\n        return value\n"
                    "class B(A):\n    pass\n"
                    "class C(A):\n"
                    "    def invoke(self, value):\n        value.os.fork()\n"
                    "class D(B, C):\n    pass\n"
                    "D().invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class A:\n"
                    "    def invoke(self, value):\n        value.os.fork()\n"
                    "class B:\n"
                    "    def invoke(self, value):\n        return value\n"
                    "class X(A, B):\n    pass\n"
                    "class Y(B, A):\n    pass\n"
                    "class Z(X, Y):\n    pass\n"
                    "Z().invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "from framework import Unknown\n"
                    "class Local:\n"
                    "    def invoke(self, value):\n        value.os.fork()\n"
                    "class Runner(Unknown, Local):\n    pass\n"
                    "Runner().invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class Base:\n"
                    "    @classmethod\n"
                    "    def invoke(cls, value):\n        value.os.fork()\n"
                    "class Runner(Base):\n    pass\n"
                    "Runner.invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "cm = classmethod\nalias = cm\n"
                    "class Runner:\n"
                    "    @alias\n"
                    "    def invoke(cls, value):\n        value.os.fork()\n"
                    "Runner.invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
            (
                (
                    "from shutil import fnmatch as p\n"
                    "class Runner:\n"
                    "    sm = staticmethod\n    alias = sm\n"
                    "    @alias\n"
                    "    def invoke(value):\n        value.os.fork()\n"
                    "Runner().invoke(p)\n"
                ),
                "shutil.fnmatch",
            ),
        ):
            with self.subTest(source=source):
                self.assertTrue(
                    sensitive_module_reexports(
                        ast.parse(source),
                        {"p": imported_name},
                    )
                )

        shadowed_source = (
            "from shutil import fnmatch as p\n"
            "def invoke(value):\n    value.os.fork()\n"
            "def run():\n"
            "    invoke = lambda value: value\n"
            "    invoke(p)\n"
            "run()\n"
        )
        self.assertFalse(
            sensitive_module_reexports(
                ast.parse(shadowed_source),
                {"p": "shutil.fnmatch"},
            ),
            "a local safe callable must shadow an outer helper with the same name",
        )

        receiver_source = (
            "from shutil import fnmatch as p\n"
            "class Runner:\n"
            "    def invoke(self, value):\n        self.os.fork()\n"
            "Runner().invoke(p)\n"
        )
        self.assertFalse(
            sensitive_module_reexports(
                ast.parse(receiver_source),
                {"p": "shutil.fnmatch"},
            ),
            "a bound receiver must not be tainted by the first explicit argument",
        )

        for safe_source in (
            (
                "from shutil import fnmatch as p\n"
                "class A:\n"
                "    def invoke(self, value):\n        return value\n"
                "class B(A):\n"
                "    def invoke(self, value):\n        return value\n"
                "class C(A):\n"
                "    def invoke(self, value):\n        value.os.fork()\n"
                "class D(B, C):\n    pass\n"
                "D().invoke(p)\n"
            ),
            (
                "from shutil import fnmatch as p\n"
                "class Base:\n"
                "    def invoke(self, value):\n        value.os.fork()\n"
                "class Runner(Base):\n"
                "    def invoke(self, value):\n        return value\n"
                "Runner().invoke(p)\n"
            ),
            (
                "from shutil import fnmatch as p\n"
                "class Base:\n"
                "    def invoke(self, value):\n        value.os.fork()\n"
                "class Runner(Base):\n"
                "    invoke = lambda self, value: value\n"
                "Runner().invoke(p)\n"
            ),
            (
                "from shutil import fnmatch as p\n"
                "cm = classmethod\n"
                "def outer():\n"
                "    cm = lambda function: function\n"
                "    class Runner:\n"
                "        @cm\n"
                "        def invoke(self, value):\n            value.os.fork()\n"
                "    Runner.invoke(p)\n"
                "outer()\n"
            ),
            (
                "from shutil import fnmatch as p\n"
                "classmethod = lambda function: function\n"
                "class Runner:\n"
                "    @classmethod\n"
                "    def invoke(self, value):\n        value.os.fork()\n"
                "Runner.invoke(p)\n"
            ),
        ):
            with self.subTest(safe_source=safe_source):
                self.assertFalse(
                    sensitive_module_reexports(
                        ast.parse(safe_source),
                        {"p": "shutil.fnmatch"},
                    ),
                    "a lexical shadow or local override must block inherited provenance",
                )

        for imported_name in (
            "Thread",
            "ThreadPoolExecutor",
            "ThreadingHTTPServer",
            "ThreadingMixIn",
            "Fork",
            "ForkingTCPServer",
            "ForkingMixIn",
            "Process",
            "ProcessPoolExecutor",
            "Pool",
            "WorkerPool",
            "Executor",
            "CustomExecutor",
            "QueueListener",
            "http.server.ThreadingHTTPServer",
            "socketserver.ForkingMixIn",
        ):
            with self.subTest(imported_name=imported_name):
                self.assertTrue(is_sensitive_import_name(imported_name))
        self.assertFalse(is_sensitive_import_name("http.server"))
        self.assertFalse(is_sensitive_import_name("PoolsideMetric"))
        self.assertFalse(is_sensitive_import_name("QueueHandler"))

        queue_listener_source = (
            "from logging.handlers import QueueListener\n"
            "QueueListener(None).start()\n"
        )
        queue_listener_tree = ast.parse(queue_listener_source)
        self.assertEqual(
            {
                (node.module, alias.name)
                for node in ast.walk(queue_listener_tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
                if is_sensitive_from_import(node.module or "", alias.name)
            },
            {("logging.handlers", "QueueListener")},
        )

        self.assertFalse(is_sensitive_import_name("listen"))
        self.assertFalse(is_sensitive_from_import("example.config", "listen"))
        for source, expected_import in (
            (
                "from logging.config import listen\nlisten().start()\n",
                ("logging.config", "listen"),
            ),
            (
                "from pydoc import _start_server\n"
                "_start_server(None, None, 0)\n",
                ("pydoc", "_start_server"),
            ),
            (
                "from faulthandler import dump_traceback_later\n"
                "dump_traceback_later(1)\n",
                ("faulthandler", "dump_traceback_later"),
            ),
        ):
            with self.subTest(source=source):
                direct_imports = {
                    (node.module, alias.name)
                    for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.ImportFrom) and node.module
                    for alias in node.names
                    if is_sensitive_from_import(node.module, alias.name)
                }
                self.assertEqual(
                    direct_imports,
                    {expected_import},
                )

        for source, bindings in (
            (
                "from http import server as s\ns.ThreadingHTTPServer\n",
                {"s": "http.server"},
            ),
            (
                "import socketserver as s\ns.ForkingMixIn\n",
                {"s": "socketserver"},
            ),
            (
                "from helpers import runtime as r\nr.ProcessPoolExecutor\n",
                {"r": "helpers.runtime"},
            ),
            (
                "import executor_tools as e\ne.CustomExecutor\n",
                {"e": "executor_tools"},
            ),
            (
                "from logging import handlers as h\n"
                "h.QueueListener(None).start()\n",
                {"h": "logging.handlers"},
            ),
            (
                "import logging.config as c\nc.listen().start()\n",
                {"c": "logging.config"},
            ),
            (
                "import logging\nlogging.config.listen().start()\n",
                {"logging": "logging"},
            ),
            (
                "import logging.config\n"
                "cfg = logging.config\n"
                "cfg.listen().start()\n",
                {"logging": "logging.config"},
            ),
            (
                "import logging\n"
                "module = logging\nconfig = module.config\n"
                "alias = config\nalias.listen().start()\n",
                {"logging": "logging"},
            ),
            (
                "import logging.config\n"
                "configs = [logging.config]\n"
                "cfg = configs[0]\ncfg.listen().start()\n",
                {"logging": "logging.config"},
            ),
            (
                "import logging.config\n"
                "configs = {'active': logging.config}\n"
                "configs['active'].listen().start()\n",
                {"logging": "logging.config"},
            ),
            (
                "import pydoc as p\np._start_server(None, None, 0)\n",
                {"p": "pydoc"},
            ),
            (
                "import faulthandler as f\n"
                "f.dump_traceback_later(1)\n",
                {"f": "faulthandler"},
            ),
        ):
            with self.subTest(source=source):
                self.assertTrue(
                    sensitive_module_reexports(ast.parse(source), bindings)
                )

        generic_listen_source = (
            "import example.config\n"
            "configs = [example.config]\n"
            "cfg = configs[0]\ncfg.listen()\n"
        )
        self.assertFalse(
            sensitive_module_reexports(
                ast.parse(generic_listen_source),
                {"example": "example.config"},
            )
        )

        lexical_shadow_source = (
            "import os\n"
            "os.fork()\n"
            "def harmless():\n"
            "    import math as os\n"
            "    return os.sqrt(4)\n"
        )
        lexical_shadow_tree = ast.parse(lexical_shadow_source)
        _, resolve_shadowed_import = lexical_import_origins(lexical_shadow_tree)
        shadowed_references = {
            node.attr: resolve_shadowed_import(node.value)
            for node in ast.walk(lexical_shadow_tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
        }
        self.assertEqual(
            shadowed_references,
            {"fork": frozenset({"os"}), "sqrt": frozenset({"math"})},
        )
        parameter_shadow_source = (
            "import os\n"
            "def harmless(os):\n"
            "    return os.fork()\n"
        )
        parameter_shadow_tree = ast.parse(parameter_shadow_source)
        _, resolve_parameter_shadow = lexical_import_origins(
            parameter_shadow_tree
        )
        shadowed_fork = next(
            node
            for node in ast.walk(parameter_shadow_tree)
            if isinstance(node, ast.Attribute) and node.attr == "fork"
        )
        self.assertEqual(
            resolve_parameter_shadow(shadowed_fork.value),
            frozenset(),
            "a local parameter must safely shadow the imported module",
        )

        scoped_listen_source = (
            "def harmless():\n"
            "    import example.config as cfg\n"
            "    return cfg.listen()\n"
            "def unrelated():\n"
            "    import logging.config as cfg\n"
            "    return None\n"
        )
        self.assertFalse(
            sensitive_module_reexports(
                ast.parse(scoped_listen_source),
                {"cfg": "logging.config"},
            ),
            "full-path concurrency origins cannot leak across functions",
        )

    def test_explicit_exit_call_guard_covers_attribute_terminators(self):
        for expression in (
            "ArgumentParser().exit(1)",
            "sys.exit(1)",
            "parser.exit(1)",
            "os._exit(1)",
        ):
            with self.subTest(expression=expression):
                call = ast.parse(expression).body[0].value
                self.assertTrue(is_explicit_exit_call(call))

        for expression in (
            "worker._exit(1)",
            "worker.exiting(1)",
            "worker.exit_code(1)",
        ):
            with self.subTest(safe_expression=expression):
                call = ast.parse(expression).body[0].value
                self.assertFalse(is_explicit_exit_call(call))

    def test_taint_guard_handles_augassign_and_higher_order_builtins(self):
        prefix = "from shutil import fnmatch as p\n"

        def findings(body: str) -> tuple[ast.AST, ...]:
            return sensitive_module_reexports(
                ast.parse(prefix + body),
                {"p": "shutil.fnmatch"},
            )

        positive_sources = {
            "augassign-container": (
                "items = []\n"
                "items += [p]\n"
                "items[0].os.fork()\n"
            ),
            "augassign-alias": (
                "items = []\n"
                "alias = items\n"
                "items += [p]\n"
                "alias[0].os.fork()\n"
            ),
            "augassign-local-call-literal": (
                "def wrap(value):\n"
                "    return value\n"
                "items = []\n"
                "items += [wrap(p)]\n"
                "items[0].os.fork()\n"
            ),
            "map": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "map(invoke, [p])\n"
            ),
            "filter": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "filter(invoke, [p])\n"
            ),
            "builtin-and-callback-aliases": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "callback = invoke\n"
                "mapper = map\n"
                "mapper(callback, [p])\n"
            ),
            "filter-alias": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "selector = filter\n"
                "selector(invoke, [p])\n"
            ),
            "bound-method-callback": (
                "class Runner:\n"
                "    def invoke(self, value):\n"
                "        value.os.fork()\n"
                "map(Runner().invoke, [p])\n"
            ),
            "lambda-callback": "map(lambda value: value.os.fork(), [p])\n",
            "map-literal-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "map(*(invoke, [p]))\n"
            ),
            "map-alias-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "args = (invoke, [p])\n"
                "map(*args)\n"
            ),
            "filter-literal-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "filter(*(invoke, [p]))\n"
            ),
            "filter-alias-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "args = (invoke, [p])\n"
                "filter(*args)\n"
            ),
            "sorted-key": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted([p], key=invoke)\n"
            ),
            "sorted-aliases": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "callback = invoke\n"
                "order = sorted\n"
                "order([p], key=callback)\n"
            ),
            "sorted-lambda": (
                "sorted([p], key=lambda value: value.os.fork())\n"
            ),
            "sorted-bound-method": (
                "class Runner:\n"
                "    def invoke(self, value):\n"
                "        value.os.fork()\n"
                "sorted([p], key=Runner().invoke)\n"
            ),
            "sorted-literal-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted(*([p],), key=invoke)\n"
            ),
            "sorted-alias-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "args = ([p],)\n"
                "sorted(*args, key=invoke)\n"
            ),
            "sorted-literal-key-mapping": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted([p], **{'key': invoke})\n"
            ),
            "sorted-aliased-key-mapping": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "kwargs = {'key': invoke}\n"
                "sorted([p], **kwargs)\n"
            ),
            "sorted-unresolved-key-mapping": (
                "kwargs = options()\n"
                "sorted([p], **kwargs)\n"
            ),
            "generic-min-key": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "min([p], key=invoke)\n"
            ),
            "generic-list-sort-key": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "items = [p]\n"
                "items.sort(key=invoke)\n"
            ),
            "generic-reduce-callback": (
                "from functools import reduce\n"
                "def invoke(left, right):\n"
                "    right.os.fork()\n"
                "reduce(invoke, [p])\n"
            ),
            "reduce-initializer": (
                "from functools import reduce\n"
                "def invoke(left, right):\n"
                "    left.os.fork()\n"
                "reduce(invoke, [None], p)\n"
            ),
            "generic-unresolved-keywords": (
                "min([p], **options())\n"
            ),
        }
        for path, source in positive_sources.items():
            with self.subTest(path=path):
                self.assertTrue(
                    findings(source),
                    f"tracked value escaped through {path}",
                )

        negative_sources = {
            "safe-numeric-augassign": "total = 0\ntotal += 1\n",
            "local-shadow-augassign": (
                "def harmless(p):\n"
                "    items = []\n"
                "    items += [p]\n"
                "    return items\n"
                "harmless(None)\n"
            ),
            "shadowed-map": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "def map(callback, values):\n"
                "    return None\n"
                "map(invoke, [p])\n"
            ),
            "shadowed-filter": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "filter = lambda callback, values: None\n"
                "filter(invoke, [p])\n"
            ),
            "safe-map-iterable": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "map(invoke, [None])\n"
            ),
            "augassign-local-discard": (
                "def discard(value):\n"
                "    return None\n"
                "items = []\n"
                "items += [discard(p)]\n"
                "items[0].os.fork()\n"
            ),
            "safe-map-star-iterable": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "args = (invoke, [None])\n"
                "map(*args)\n"
            ),
            "safe-filter-star-iterable": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "filter(*(invoke, [None]))\n"
            ),
            "shadowed-map-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "def map(*args):\n"
                "    return None\n"
                "map(*(invoke, [p]))\n"
            ),
            "shadowed-filter-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "filter = lambda *args: None\n"
                "args = (invoke, [p])\n"
                "filter(*args)\n"
            ),
            "shadowed-sorted": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "def sorted(values, *, key):\n"
                "    return values\n"
                "sorted([p], key=invoke)\n"
            ),
            "safe-sorted-iterable": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted([None], key=invoke)\n"
            ),
            "sorted-callback-ignores-item": (
                "def ignore(value):\n"
                "    return None\n"
                "sorted([p], key=ignore)\n"
            ),
            "sorted-without-key": "sorted([p])\n",
            "sorted-mapping-reverse-only": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted([p], **{'reverse': invoke})\n"
            ),
            "safe-sorted-mapping-iterable": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted([None], **{'key': invoke})\n"
            ),
            "sorted-mapping-callback-ignores-item": (
                "def ignore(value):\n"
                "    return None\n"
                "sorted([p], **{'key': ignore})\n"
            ),
            "shadowed-sorted-mapping": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "def sorted(values, **kwargs):\n"
                "    return values\n"
                "sorted([p], **{'key': invoke})\n"
            ),
            "generic-nested-discard": (
                "def discard(value):\n"
                "    return None\n"
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "min(discard(p), key=invoke)\n"
            ),
            "shadowed-min": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "def min(values, *, key):\n"
                "    return None\n"
                "min([p], key=invoke)\n"
            ),
            "safe-generic-input": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "min([None], key=invoke)\n"
            ),
            "safe-unresolved-keywords-input": "min([None], **options())\n",
            "min-optional-callback-context": (
                "def invoke(value, context=None):\n"
                "    context.os.fork()\n"
                "min([p], key=invoke)\n"
            ),
            "min-positional-callable-is-data": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "min(p, invoke)\n"
            ),
            "reduce-initializer-does-not-taint-right": (
                "from functools import reduce\n"
                "def invoke(left, right):\n"
                "    right.os.fork()\n"
                "reduce(invoke, [None], p)\n"
            ),
        }
        for path, source in negative_sources.items():
            with self.subTest(safe_path=path):
                self.assertFalse(
                    findings(source),
                    f"safe higher-order or AugAssign path was rejected: {path}",
                )

    def test_reexport_guard_rejects_persistent_state_escape(self):
        prefix = "from shutil import fnmatch as p\n"

        def findings(body: str) -> tuple[ast.AST, ...]:
            return sensitive_module_reexports(
                ast.parse(prefix + body),
                {"p": "shutil.fnmatch"},
            )

        positive_sources = {
            "instance-setter": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.module = value\n"
                "    def invoke(self):\n"
                "        return self.module.os.fork()\n"
                "r = Runner()\n"
                "r.set(p)\n"
                "r.invoke()\n"
            ),
            "receiver-alias": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.module = value\n"
                "r = Runner()\n"
                "receiver = r\n"
                "receiver.set(p)\n"
            ),
            "tuple-target": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.module, local = value, None\n"
                "r = Runner()\n"
                "r.set(p)\n"
            ),
            "subscript-target": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.modules[0] = value\n"
                "r = Runner()\n"
                "r.set(p)\n"
            ),
            "setter-alias": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.module = value\n"
                "r = Runner()\n"
                "setter = r.set\n"
                "setter(p)\n"
            ),
            "setattr-alias": (
                "setter = setattr\n"
                "class Runner:\n"
                "    def set(self, value):\n"
                "        setter(self, 'module', value)\n"
                "r = Runner()\n"
                "r.set(p)\n"
            ),
            "object-setattr": "object.__setattr__(holder, 'module', p)\n",
            "type-setattr": "type.__setattr__(Holder, 'module', p)\n",
            "augmented-assignment": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.modules += [value]\n"
                "r = Runner()\n"
                "r.set(p)\n"
            ),
            "unknown-wrapper": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.module = external_identity(value)\n"
                "r = Runner()\n"
                "r.set(p)\n"
            ),
            "wrapper-attribute-argument": (
                "holder.module = external_identity(p.child)\n"
            ),
            "wrapper-subscript-argument": (
                "holder.module = external_identity(p[0])\n"
            ),
            "wrapper-attribute-result": (
                "holder.module = external_identity(p).module\n"
            ),
            "wrapper-subscript-result": (
                "holder.module = external_identity(p)[0]\n"
            ),
            "imported-attribute-wrapper": (
                "import external\n"
                "holder.module = external.identity(p)\n"
            ),
            "unresolved-attribute-wrapper": (
                "holder.module = external.identity(p)\n"
            ),
            "nested-unknown-wrapper": "holder.module = outer(inner(p))\n",
            "nested-multi-argument-wrapper": (
                "holder.module = outer(inner(p, None))\n"
            ),
            "multi-argument-wrapper": (
                "holder.module = external_identity(p, None)\n"
            ),
            "local-constructor-capture": (
                "class Wrapper:\n"
                "    def __init__(self, value):\n"
                "        self.value = value\n"
                "holder.module = Wrapper(p)\n"
            ),
            "setattr-wrapper": (
                "setter = setattr\n"
                "setter(holder, 'module', external_identity(p))\n"
            ),
            "setattr-literal-star": (
                "setter = setattr\n"
                "setter(*(holder, 'module', p))\n"
            ),
            "object-setattr-literal-star": (
                "object.__setattr__(holder, *('module', p))\n"
            ),
            "setattr-unresolved-star": (
                "setter = setattr\n"
                "arguments = (holder, 'module', p)\n"
                "setter(*arguments)\n"
            ),
            "receiver-setattr": "holder.__setattr__('module', p)\n",
            "receiver-setattr-star": (
                "holder.__setattr__(*('module', p))\n"
            ),
            "resolved-dangerous-append-body": (
                "class Box:\n"
                "    def append(self, value):\n"
                "        self.module = value\n"
                "Box().append(p)\n"
            ),
            "annotated-assignment": "holder.module: object = p\n",
            "safe-overwrite-after-escape": (
                "holder.module = p\n"
                "holder.module = None\n"
            ),
            "constructor-init-store": (
                "class Holder:\n"
                "    def __init__(self, value):\n"
                "        self.module = value\n"
                "Holder(p)\n"
            ),
            "constructor-inherited-init": (
                "class Base:\n"
                "    def __init__(self, value):\n"
                "        self.module = value\n"
                "class Holder(Base):\n"
                "    pass\n"
                "Holder(p)\n"
            ),
            "constructor-alias": (
                "class Holder:\n"
                "    def __init__(self, value):\n"
                "        self.module = value\n"
                "Constructor = Holder\n"
                "Constructor(p)\n"
            ),
            "constructor-c3-init": (
                "class Root:\n"
                "    def __init__(self, value):\n"
                "        return None\n"
                "class Left(Root):\n"
                "    pass\n"
                "class Right(Root):\n"
                "    def __init__(self, value):\n"
                "        self.module = value\n"
                "class Holder(Left, Right):\n"
                "    pass\n"
                "Holder(p)\n"
            ),
            "constructor-new-store": (
                "class Holder:\n"
                "    def __new__(cls, value):\n"
                "        cls.module = value\n"
                "        return object.__new__(cls)\n"
                "Holder(p)\n"
            ),
            "constructor-new-inherited-alias": (
                "class Base:\n"
                "    def __new__(cls, value):\n"
                "        value.os.fork()\n"
                "        return object.__new__(cls)\n"
                "class Holder(Base):\n"
                "    pass\n"
                "Constructor = Holder\n"
                "Constructor(p)\n"
            ),
            "constructor-new-keyword": (
                "class Holder:\n"
                "    def __new__(cls, value):\n"
                "        value.os.fork()\n"
                "        return object.__new__(cls)\n"
                "Holder(value=p)\n"
            ),
            "constructor-new-star": (
                "class Holder:\n"
                "    def __new__(cls, value):\n"
                "        value.os.fork()\n"
                "        return object.__new__(cls)\n"
                "Holder(*(p,))\n"
            ),
            "constructor-static-new": (
                "class Holder:\n"
                "    @staticmethod\n"
                "    def __new__(cls, value):\n"
                "        cls.module = value\n"
                "        return object.__new__(cls)\n"
                "Holder(p)\n"
            ),
            "constructor-classmethod-new": (
                "class Holder:\n"
                "    @classmethod\n"
                "    def __new__(bound_cls, passed_cls, value):\n"
                "        bound_cls.module = value\n"
                "        return object.__new__(passed_cls)\n"
                "Holder(p)\n"
            ),
        }
        for escape, source in positive_sources.items():
            with self.subTest(escape=escape):
                self.assertTrue(
                    findings(source),
                    f"persistent tracked state escaped through {escape}",
                )

        mutator_sources = {
            "append": "items.append(p)\n",
            "append-wrapper": "items.append(external_identity(p))\n",
            "extend": "items.extend([p])\n",
            "insert": "items.insert(0, p)\n",
            "insert-literal-star": "items.insert(*(0, p))\n",
            "add": "items.add(p)\n",
            "update": "items.update({'module': p})\n",
            "setdefault": "items.setdefault('module', p)\n",
            "__setitem__": "items.__setitem__('module', p)\n",
        }
        for mutator, source in mutator_sources.items():
            with self.subTest(mutator=mutator):
                self.assertTrue(
                    findings(source),
                    f"tracked value escaped through {mutator}",
                )

        named_expression_tree = ast.parse(prefix)
        named_expression_tree.body.append(ast.Expr(value=ast.NamedExpr(
            target=ast.Attribute(
                value=ast.Name(id="holder", ctx=ast.Load()),
                attr="module",
                ctx=ast.Store(),
            ),
            value=ast.Name(id="p", ctx=ast.Load()),
        )))
        self.assertTrue(
            sensitive_module_reexports(
                named_expression_tree,
                {"p": "shutil.fnmatch"},
            ),
            "the AST guard must reject a persistent NamedExpr target",
        )

        negative_sources = {
            "local-name-shadow": (
                "def harmless(p):\n"
                "    holder.module = p\n"
                "harmless(None)\n"
            ),
            "uncalled-setter": (
                "class Runner:\n"
                "    def set(self, value):\n"
                "        self.module = value\n"
            ),
            "safe-rhs": "holder.module = 1\n",
            "shadowed-setattr": (
                "def setattr(target, name, value):\n"
                "    return value\n"
                "setattr(holder, 'module', p)\n"
            ),
            "resolved-local-discard-wrapper": (
                "def discard(value):\n"
                "    return None\n"
                "holder.module = outer(discard(p))\n"
            ),
            "resolved-safe-append": (
                "class SafeBox:\n"
                "    def append(self, value):\n"
                "        return None\n"
                "SafeBox().append(p)\n"
            ),
            "resolved-safe-setattr": (
                "class SafeBox:\n"
                "    def __setattr__(self, name, value):\n"
                "        return None\n"
                "SafeBox().__setattr__('module', p)\n"
            ),
            "local-constructor-safe-argument": (
                "class Wrapper:\n"
                "    def __init__(self, value):\n"
                "        self.value = value\n"
                "holder.module = Wrapper(None)\n"
            ),
            "constructor-discards-value": (
                "class Holder:\n"
                "    def __init__(self, value):\n"
                "        return None\n"
                "Holder(p)\n"
            ),
            "constructor-local-only": (
                "class Holder:\n"
                "    def __init__(self, value):\n"
                "        local = value\n"
                "Holder(p)\n"
            ),
            "constructor-safe-override": (
                "class Base:\n"
                "    def __init__(self, value):\n"
                "        self.module = value\n"
                "class Holder(Base):\n"
                "    def __init__(self, value):\n"
                "        return None\n"
                "Holder(p)\n"
            ),
            "unresolved-external-constructor": "External(p)\n",
            "constructor-new-receiver-only": (
                "class Holder:\n"
                "    def __new__(cls, value):\n"
                "        cls.module = cls\n"
                "        return object.__new__(cls)\n"
                "Holder(p)\n"
            ),
            "constructor-classmethod-new-receivers-only": (
                "class Holder:\n"
                "    @classmethod\n"
                "    def __new__(bound_cls, passed_cls, value):\n"
                "        bound_cls.module = passed_cls\n"
                "        return object.__new__(passed_cls)\n"
                "Holder(p)\n"
            ),
            "constructor-new-safe-override": (
                "class Base:\n"
                "    def __new__(cls, value):\n"
                "        cls.module = value\n"
                "        return object.__new__(cls)\n"
                "class Holder(Base):\n"
                "    def __new__(cls, value):\n"
                "        return object.__new__(cls)\n"
                "Holder(p)\n"
            ),
            "constructor-new-local-only": (
                "class Holder:\n"
                "    def __new__(cls, value):\n"
                "        local = value\n"
                "        return object.__new__(cls)\n"
                "Holder(p)\n"
            ),
            "insert-star-tracked-index": "items.insert(*(p, 'safe'))\n",
            "legitimate-mutators": (
                "items.append('safe')\n"
                "items.extend([1])\n"
                "items.insert(p, 'safe')\n"
                "items.add(None)\n"
                "items.update({'safe': 1})\n"
                "items.setdefault('safe', None)\n"
                "items.__setitem__('safe', None)\n"
                "setattr(holder, 'module', None)\n"
            ),
        }
        for safe_case, source in negative_sources.items():
            with self.subTest(safe_case=safe_case):
                self.assertFalse(
                    findings(source),
                    f"safe state operation was rejected: {safe_case}",
                )

    def test_execute_integrity_guard_rejects_shadows_and_relocations(self):
        valid_source = (
            "def _run_json(command, stage):\n    return {}\n"
            "def _existing_manifests(day):\n    return ()\n"
            "def requested_dates(*, dates, start, end, maximum):\n"
            "    return ()\n"
            "def execute(days, *, continue_on_failure, run_json=_run_json, "
            "existing=_existing_manifests):\n"
            "    execute_count = len(days)\n"
            "    _execute_result = None\n"
            "    for day in days:\n"
            "        try:\n"
            "            manifest = {\"replay_run_id\": \"known\", "
            "\"dataset_digest\": \"d\", \"configuration_digest\": \"c\", "
            "\"frame_count\": 1}\n"
            "            run_id = str(manifest[\"replay_run_id\"]) if manifest "
            "else f\"h2d-{day.isoformat()}\"\n"
            "            dataset_digest = manifest.get(\"dataset_digest\")\n"
            "            configuration_digest = "
            "manifest.get(\"configuration_digest\")\n"
            "            frame_count = manifest.get(\"frame_count\")\n"
            "        except Exception:\n"
            "            pass\n"
            "    return {\"count\": execute_count, "
            "\"overall_status\": \"COMPLETED\"}\n"
            "class Executor:\n    pass\n"
            "def main(argv=None):\n"
            "    args = type(\"Args\", (), {\"dates\": (), \"start\": None, "
            "\"end\": None, \"max_sessions\": 20, "
            "\"continue_on_failure\": False})()\n"
            "    try:\n"
            "        days = requested_dates(\n"
            "            dates=args.dates,\n"
            "            start=args.start,\n"
            "            end=args.end,\n"
            "            maximum=args.max_sessions,\n"
            "        )\n"
            "    except ValueError as error:\n"
            "        parser.error(str(error))\n"
            "    output = execute(days, "
            "continue_on_failure=args.continue_on_failure)\n"
            "    print(json.dumps(output, sort_keys=True, "
            "separators=(\",\", \":\")))\n"
            "    return 1 if output[\"overall_status\"] == \"FAILED\" else 0\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(valid_source)),
            "the exact interface and benign similarly named locals must pass",
        )

        exact_call = (
            "    output = execute(days, "
            "continue_on_failure=args.continue_on_failure)\n"
        )
        exact_days_selection = (
            "    try:\n"
            "        days = requested_dates(\n"
            "            dates=args.dates,\n"
            "            start=args.start,\n"
            "            end=args.end,\n"
            "            maximum=args.max_sessions,\n"
            "        )\n"
            "    except ValueError as error:\n"
            "        parser.error(str(error))\n"
        )
        exact_entrypoint = (
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        )
        mutations = {
            "decorator": (
                valid_source.replace(
                    "def execute(days,",
                    "@identity\ndef execute(days,",
                    1,
                ),
                "execute-decoration",
            ),
            "assignment": (
                valid_source + "execute = None\n",
                "execute-shadow",
            ),
            "deletion": (
                valid_source + "del execute\n",
                "execute-shadow",
            ),
            "import-alias": (
                valid_source + "import math as execute\n",
                "execute-shadow",
            ),
            "callable-alias": (
                valid_source + "dispatcher = execute\n",
                "execute-load-count",
            ),
            "default-capture": (
                valid_source
                + "def capture(callback=execute):\n    return callback\n",
                "execute-load-count",
            ),
            "relocation": (
                valid_source.replace(
                    exact_call,
                    "    if True:\n        " + exact_call.lstrip(),
                    1,
                ),
                "execute-call-shape",
            ),
            "days-selection-call-shape": (
                valid_source.replace(
                    "            maximum=args.max_sessions,\n",
                    "            maximum=20,\n",
                    1,
                ),
                "days-selection-shape",
            ),
            "days-reassignment": (
                valid_source.replace(
                    exact_call,
                    "    days = days + days\n" + exact_call,
                    1,
                ),
                "days-selection-shape",
            ),
            "days-augmented-assignment": (
                valid_source.replace(
                    exact_call,
                    "    days *= 2\n" + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-deletion": (
                valid_source.replace(
                    exact_call,
                    "    del days\n" + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-mutator": (
                valid_source.replace(
                    exact_call,
                    "    days.append(None)\n" + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-subscript-write": (
                valid_source.replace(
                    exact_call,
                    "    days[0] = None\n" + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-alias-mutator": (
                valid_source.replace(
                    exact_call,
                    "    selected = days\n"
                    "    selected.clear()\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-for-target": (
                valid_source.replace(
                    exact_call,
                    "    for days in ():\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-with-target": (
                valid_source.replace(
                    exact_call,
                    "    with context() as days:\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-import-alias": (
                valid_source.replace(
                    exact_call,
                    "    import math as days\n" + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-from-import-alias": (
                valid_source.replace(
                    exact_call,
                    "    from math import pi as days\n" + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-function-definition": (
                valid_source.replace(
                    exact_call,
                    "    def days():\n"
                    "        return None\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-async-function-definition": (
                valid_source.replace(
                    exact_call,
                    "    async def days():\n"
                    "        return None\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-class-definition": (
                valid_source.replace(
                    exact_call,
                    "    class days:\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-except-target": (
                valid_source.replace(
                    exact_call,
                    "    try:\n"
                    "        pass\n"
                    "    except Exception as days:\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-match-capture": (
                valid_source.replace(
                    exact_call,
                    "    match None:\n"
                    "        case days:\n"
                    "            pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-comprehension-named-expression": (
                valid_source.replace(
                    exact_call,
                    "    changed = [(days := ()) for _ in ()]\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-function-default": (
                valid_source.replace(
                    exact_call,
                    "    def helper(value=(days := ())):\n"
                    "        return value\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-function-decorator": (
                valid_source.replace(
                    exact_call,
                    "    @(days := decorate)\n"
                    "    def helper():\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-runtime-function-annotation": (
                valid_source.replace(
                    exact_call,
                    "    def helper(value: (days := object)):\n"
                    "        return value\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-lambda-default": (
                valid_source.replace(
                    exact_call,
                    "    helper = lambda value=(days := ()): value\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-class-base": (
                valid_source.replace(
                    exact_call,
                    "    class Helper((days := Base)):\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-class-decorator": (
                valid_source.replace(
                    exact_call,
                    "    @(days := decorate)\n"
                    "    class Helper:\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "days-class-keyword": (
                valid_source.replace(
                    exact_call,
                    "    class Helper(metaclass=(days := Meta)):\n"
                    "        pass\n"
                    + exact_call,
                    1,
                ),
                "days-selection-mutation",
            ),
            "run-json-rebinding": (
                valid_source.replace(
                    "    execute_count = len(days)\n",
                    "    run_json = None\n"
                    "    execute_count = len(days)\n",
                    1,
                ),
                "execute-dispatch-binding",
            ),
            "day-rebinding": (
                valid_source.replace(
                    "    return {\"count\": execute_count, ",
                    "    day = None\n"
                    "    return {\"count\": execute_count, ",
                    1,
                ),
                "execute-day-binding",
            ),
            "day-comprehension-named-expression": (
                valid_source.replace(
                    "    return {\"count\": execute_count, ",
                    "    changed = [(day := None) for _ in ()]\n"
                    "    return {\"count\": execute_count, ",
                    1,
                ),
                "execute-day-binding",
            ),
            "run-id-rebinding": (
                valid_source.replace(
                    "            dataset_digest = manifest.get",
                    "            run_id = 'changed'\n"
                    "            dataset_digest = manifest.get",
                    1,
                ),
                "execute-lineage-binding",
            ),
            "run-id-function-default": (
                valid_source.replace(
                    "            dataset_digest = manifest.get",
                    "            def helper(value=(run_id := 'changed')):\n"
                    "                return value\n"
                    "            dataset_digest = manifest.get",
                    1,
                ),
                "execute-lineage-binding",
            ),
            "dataset-digest-rebinding": (
                valid_source.replace(
                    "            configuration_digest = ",
                    "            dataset_digest = None\n"
                    "            configuration_digest = ",
                    1,
                ),
                "execute-lineage-binding",
            ),
            "configuration-digest-rebinding": (
                valid_source.replace(
                    "            frame_count = manifest.get",
                    "            configuration_digest = None\n"
                    "            frame_count = manifest.get",
                    1,
                ),
                "execute-lineage-binding",
            ),
            "frame-count-rebinding": (
                valid_source.replace(
                    "        except Exception:\n",
                    "            frame_count = 0\n"
                    "        except Exception:\n",
                    1,
                ),
                "execute-lineage-binding",
            ),
            "output-rebinding": (
                valid_source.replace(
                    "    print(json.dumps(output, sort_keys=True, ",
                    "    output = {}\n"
                    "    print(json.dumps(output, sort_keys=True, ",
                    1,
                ),
                "main-output-binding",
            ),
            "output-extra-load": (
                valid_source.replace(
                    "    print(json.dumps(output, sort_keys=True, ",
                    "    inspected = output\n"
                    "    print(json.dumps(output, sort_keys=True, ",
                    1,
                ),
                "main-output-use",
            ),
            "output-print-replacement": (
                valid_source.replace(
                    "print(json.dumps(output, sort_keys=True, "
                    "separators=(\",\", \":\")))",
                    "print('{}')",
                    1,
                ),
                "main-output-use",
            ),
            "output-status-replacement": (
                valid_source.replace(
                    "return 1 if output[\"overall_status\"] "
                    "== \"FAILED\" else 0",
                    "return 0",
                    1,
                ),
                "main-output-use",
            ),
            "extra-default": (
                valid_source.replace(
                    "continue_on_failure, run_json=",
                    "continue_on_failure=False, run_json=",
                    1,
                ),
                "execute-signature",
            ),
            "wrong-dispatch-default": (
                valid_source.replace(
                    "run_json=_run_json",
                    "run_json=None",
                    1,
                ),
                "execute-signature",
            ),
            "duplicate-async": (
                valid_source + "async def execute():\n    return None\n",
                "execute-shadow",
            ),
            "duplicate-class": (
                valid_source + "class execute:\n    pass\n",
                "execute-shadow",
            ),
            "parameter-shadow": (
                valid_source
                + "def capture_parameter(execute):\n    return None\n",
                "execute-shadow",
            ),
            "global-shadow": (
                valid_source
                + "def capture_global():\n    global execute\n    return None\n",
                "execute-shadow",
            ),
            "except-shadow": (
                valid_source
                + "try:\n    pass\nexcept Exception as execute:\n    pass\n",
                "execute-shadow",
            ),
            "match-capture": (
                valid_source
                + "def capture_match(value):\n"
                + "    match value:\n"
                + "        case execute:\n"
                + "            return None\n",
                "execute-shadow",
            ),
            "main-signature": (
                valid_source.replace(
                    "def main(argv=None):",
                    "def main(argv=()):",
                    1,
                ),
                "main-signature",
            ),
            "main-assignment": (
                valid_source + "main = None\n",
                "main-shadow",
            ),
            "main-deletion": (
                valid_source + "del main\n",
                "main-shadow",
            ),
            "main-import-alias": (
                valid_source + "import math as main\n",
                "main-shadow",
            ),
            "duplicate-async-main": (
                valid_source + "async def main():\n    return None\n",
                "main-shadow",
            ),
            "duplicate-class-main": (
                valid_source + "class main:\n    pass\n",
                "main-shadow",
            ),
            "entrypoint-replacement": (
                valid_source.replace(
                    exact_entrypoint,
                    "if __name__ == '__main__':\n    main()\n",
                    1,
                ),
                "main-entrypoint",
            ),
            "entrypoint-argument": (
                valid_source.replace("SystemExit(main())", "SystemExit(main([]))", 1),
                "main-entrypoint",
            ),
            "entrypoint-addition": (
                valid_source
                + "if __name__ == '__main__':\n    raise SystemExit(main())\n",
                "main-entrypoint",
            ),
            "entrypoint-not-final": (
                valid_source + "TRAILING = True\n",
                "main-entrypoint",
            ),
            "module-name-rebinding": (
                valid_source.replace(
                    exact_entrypoint,
                    "__name__ = 'disabled'\n" + exact_entrypoint,
                    1,
                ),
                "main-entrypoint",
            ),
            "system-exit-rebinding": (
                valid_source.replace(
                    exact_entrypoint,
                    "SystemExit = RuntimeError\n" + exact_entrypoint,
                    1,
                ),
                "main-entrypoint",
            ),
            "main-early-return": (
                valid_source.replace(
                    exact_call,
                    "    return 0\n" + exact_call,
                    1,
                ),
                "main-early-termination",
            ),
            "main-early-raise": (
                valid_source.replace(
                    exact_call,
                    "    raise RuntimeError\n" + exact_call,
                    1,
                ),
                "main-early-termination",
            ),
            "main-loop-break": (
                valid_source.replace(
                    exact_call,
                    "    for _ in (0,):\n        break\n" + exact_call,
                    1,
                ),
                "main-early-termination",
            ),
            "main-loop-continue": (
                valid_source.replace(
                    exact_call,
                    "    for _ in (0,):\n        continue\n" + exact_call,
                    1,
                ),
                "main-early-termination",
            ),
            "main-exit-call": (
                valid_source.replace(exact_call, "    exit(0)\n" + exact_call, 1),
                "main-early-termination",
            ),
            "main-sys-exit-call": (
                valid_source.replace(
                    exact_call,
                    "    sys.exit(0)\n" + exact_call,
                    1,
                ),
                "main-early-termination",
            ),
            "main-parser-exit-call": (
                valid_source.replace(
                    exact_call,
                    "    parser.exit(0)\n" + exact_call,
                    1,
                ),
                "main-early-termination",
            ),
            "top-level-termination": (
                valid_source.replace(
                    exact_entrypoint,
                    "raise SystemExit(0)\n" + exact_entrypoint,
                    1,
                ),
                "main-entrypoint",
            ),
            "execute-generator": (
                valid_source.replace(
                    "    return {\"count\": execute_count, "
                    "\"overall_status\": \"COMPLETED\"}\n",
                    "    if False:\n        yield None\n"
                    "    return {\"count\": execute_count, "
                    "\"overall_status\": \"COMPLETED\"}\n",
                    1,
                ),
                "execute-generator",
            ),
            "execute-yield-from": (
                valid_source.replace(
                    "    return {\"count\": execute_count, "
                    "\"overall_status\": \"COMPLETED\"}\n",
                    "    if False:\n        yield from ()\n"
                    "    return {\"count\": execute_count, "
                    "\"overall_status\": \"COMPLETED\"}\n",
                    1,
                ),
                "execute-generator",
            ),
            "main-generator": (
                valid_source.replace(
                    "    return 1 if output[\"overall_status\"] "
                    "== \"FAILED\" else 0\n",
                    "    if False:\n        yield output\n"
                    "    return 1 if output[\"overall_status\"] "
                    "== \"FAILED\" else 0\n",
                    1,
                ),
                "main-generator",
            ),
        }
        for mutation, (mutated_source, expected_violation) in mutations.items():
            with self.subTest(mutation=mutation):
                self.assertIn(
                    expected_violation,
                    execute_integrity_violations(ast.parse(mutated_source)),
                )

        async_binding_sources = {
            ast.AsyncFor: (
                "    for days in ():\n"
                "        pass\n"
            ),
            ast.AsyncWith: (
                "    with context() as days:\n"
                "        pass\n"
            ),
        }
        for async_type, binding_source in async_binding_sources.items():
            with self.subTest(days_async_binding=async_type.__name__):
                binding_tree = ast.parse(valid_source.replace(
                    exact_call,
                    binding_source + exact_call,
                    1,
                ))
                binding_main = next(
                    node for node in binding_tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "main"
                )
                binding_index = next(
                    index for index, statement in enumerate(binding_main.body)
                    if isinstance(statement, (ast.For, ast.With))
                )
                binding_statement = binding_main.body[binding_index]
                if async_type is ast.AsyncFor:
                    replacement = ast.AsyncFor(
                        target=binding_statement.target,
                        iter=binding_statement.iter,
                        body=binding_statement.body,
                        orelse=binding_statement.orelse,
                        type_comment=binding_statement.type_comment,
                    )
                else:
                    replacement = ast.AsyncWith(
                        items=binding_statement.items,
                        body=binding_statement.body,
                        type_comment=binding_statement.type_comment,
                    )
                binding_main.body[binding_index] = ast.copy_location(
                    replacement,
                    binding_statement,
                )
                self.assertIn(
                    "days-selection-mutation",
                    execute_integrity_violations(binding_tree),
                )

        for statement_type in (ast.Global, ast.Nonlocal):
            with self.subTest(days_scope_binding=statement_type.__name__):
                binding_tree = ast.parse(valid_source.replace(
                    exact_call,
                    "    pass\n" + exact_call,
                    1,
                ))
                binding_main = next(
                    node for node in binding_tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "main"
                )
                binding_index = next(
                    index for index, statement in enumerate(binding_main.body)
                    if isinstance(statement, ast.Pass)
                )
                placeholder = binding_main.body[binding_index]
                binding_main.body[binding_index] = ast.copy_location(
                    statement_type(names=["days"]),
                    placeholder,
                )
                self.assertIn(
                    "days-selection-mutation",
                    execute_integrity_violations(binding_tree),
                )

        for safe_read in (
            "    count = len(days)\n",
            "    preview = tuple(days)\n",
            "    first = days[0] if days else None\n",
            "    shadowed = [days for days in ()]\n",
            "    for item in days:\n        pass\n",
            "    with context() as item:\n        pass\n",
            "    import math as calendar\n",
            "    from math import pi as ratio\n",
            "    def nested():\n"
            "        for days in ():\n"
            "            pass\n",
            "    async def nested_async():\n"
            "        async for days in stream():\n"
            "            pass\n"
            "        async with context() as days:\n"
            "            pass\n",
            "    try:\n"
            "        pass\n"
            "    except Exception as error:\n"
            "        pass\n",
            "    match None:\n"
            "        case other:\n"
            "            pass\n",
            "    def nested_output():\n"
            "        output = None\n"
            "        return output\n",
            "    shadowed_output = [output for output in ()]\n",
            "    class Nested:\n"
            "        days = ()\n",
            "    nested_lambda = lambda: (days := ())\n",
        ):
            with self.subTest(safe_days_read=safe_read.strip()):
                self.assertFalse(
                    execute_integrity_violations(ast.parse(
                        valid_source.replace(
                            exact_call,
                            safe_read + exact_call,
                            1,
                        )
                    )),
                )

        safe_execute_shadows = valid_source.replace(
            "    return {\"count\": execute_count, ",
            "    def nested_bindings(run_json, day, run_id, dataset_digest, "
            "configuration_digest, frame_count):\n"
            "        return None\n"
            "    shadows = [None for run_json in () for day in () "
            "for run_id in () for dataset_digest in () "
            "for configuration_digest in () for frame_count in ()]\n"
            "    return {\"count\": execute_count, ",
            1,
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(safe_execute_shadows)),
            "nested and comprehension-target shadows must remain local",
        )

        deferred_annotation_shadow = (
            "from __future__ import annotations\n"
            + valid_source.replace(
                exact_call,
                "    def helper(value: (days := object)):\n"
                "        return value\n"
                + exact_call,
                1,
            )
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(deferred_annotation_shadow)),
            "deferred annotations must not create runtime binding events",
        )

    def test_baselines_are_two_read_only_certified_complete_sessions(self):
        payload = json.loads(
            BASELINES.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_json_object_pairs,
        )
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
                "key_component_order": {
                    "cutoff_at": "ascending_utc_instant",
                    "quant_id": "ascending_unsigned_utf8_bytes",
                    "horizon": "ascending_unsigned_utf8_bytes",
                },
                "database_collation": "forbidden",
                "forecast_order": ["cutoff_at", "quant_id", "horizon"],
                "outcome_order": ["cutoff_at", "horizon"],
                "bytewise_order_examples": {
                    "quant_id": [
                        "q1",
                        "q10",
                        "q11",
                        "q12",
                        "q2",
                        "q3",
                        "q4",
                        "q5",
                        "q6",
                        "q7",
                        "q8",
                        "q9",
                    ],
                    "horizon": [
                        "15M",
                        "1H",
                        "1M",
                        "30M",
                        "30S",
                        "5M",
                    ],
                },
            },
        )
        bytewise_examples = payload["ordered_content_hash_contract"][
            "bytewise_order_examples"
        ]
        for field, values in bytewise_examples.items():
            with self.subTest(bytewise_order=field):
                self.assertEqual(
                    values,
                    sorted(values, key=lambda value: value.encode("utf-8")),
                )
        self.assertLess(
            bytewise_examples["quant_id"].index("q10"),
            bytewise_examples["quant_id"].index("q2"),
        )
        self.assertEqual(
            bytewise_examples["horizon"],
            ["15M", "1H", "1M", "30M", "30S", "5M"],
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
        self.assertFalse(
            execute_integrity_violations(tree),
            "execute/main definition, binding, or direct-call integrity drifted",
        )
        imported = set()
        direct_imports = set()
        imported_bindings = {}
        star_imports = set()
        relative_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
                    imported_bindings[
                        alias.asname or alias.name.split(".")[0]
                    ] = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative_imports.add((node.level, node.module))
                if node.module:
                    imported.add(node.module)
                    direct_imports.update(
                        (node.module, alias.name) for alias in node.names
                    )
                    imported_bindings.update({
                        alias.asname or alias.name:
                            f"{node.module}.{alias.name}"
                        for alias in node.names
                    })
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
            if is_sensitive_from_import(*item)
        }
        self.assertFalse(
            direct_process_imports,
            f"direct OS/process imports are forbidden: {direct_process_imports}",
        )
        reexported_process_modules = sensitive_module_reexports(
            tree,
            imported_bindings,
        )
        self.assertFalse(
            reexported_process_modules,
            "process/concurrency modules re-exported by allowed imports",
        )
        parents, resolve_module_imports = lexical_import_origins(tree)
        qualified_references = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                qualified_references.update(
                    (origin.split(".")[0], node.attr)
                    for origin in resolve_module_imports(node.value)
                )
        allowed_process_references = {
            ("os", "environ"),
            ("subprocess", "run"),
            ("sys", "executable"),
        }
        bare_imported_module_loads = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and resolve_module_imports(node)
            and not (
                isinstance(parents.get(node), ast.Attribute)
                and parents[node].value is node
            )
        )
        self.assertFalse(
            bare_imported_module_loads,
            "imported module objects cannot be aliased, contained, or passed",
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
            and "subprocess" in {
                origin.split(".")[0]
                for origin in resolve_module_imports(node.value)
            }
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
        run_json_function = run_json_functions[0]
        self.assertIn(subprocess_run_call, tuple(ast.walk(run_json_function)))
        self.assertFalse(run_json_function.decorator_list)
        self.assertFalse(run_json_function.args.defaults)
        self.assertFalse(run_json_function.args.kw_defaults)
        self.assertEqual(
            [argument.arg for argument in run_json_function.args.args],
            ["command", "stage"],
        )
        self.assertIsInstance(run_json_function.body[0], ast.Assign)
        first_statement = run_json_function.body[0]
        self.assertEqual(len(first_statement.targets), 1)
        self.assertIsInstance(first_statement.targets[0], ast.Name)
        self.assertEqual(first_statement.targets[0].id, "completed")
        self.assertIs(first_statement.value, subprocess_run_call)
        command_loads = tuple(
            node
            for node in ast.walk(run_json_function)
            if isinstance(node, ast.Name)
            and node.id == "command"
            and isinstance(node.ctx, ast.Load)
        )
        self.assertEqual(
            command_loads,
            (subprocess_run_call.args[0],),
            "_run_json must pass its untouched command parameter exactly once",
        )
        command_writes = tuple(
            node
            for node in ast.walk(run_json_function)
            if isinstance(node, ast.Name)
            and node.id == "command"
            and isinstance(node.ctx, (ast.Store, ast.Del))
        )
        self.assertFalse(
            command_writes,
            "_run_json cannot rebind or mutate its command parameter",
        )
        indirect_command_namespace_access = tuple(
            node
            for node in ast.walk(run_json_function)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in {"globals", "locals", "vars"}
        )
        self.assertFalse(
            indirect_command_namespace_access,
            "_run_json cannot access command through a dynamic namespace",
        )
        dispatcher_or_subprocess_writes = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id in {"_run_json", "subprocess", "sys"}
            and isinstance(node.ctx, (ast.Store, ast.Del))
        )
        self.assertFalse(
            dispatcher_or_subprocess_writes,
            "the dispatcher, subprocess, and sys bindings are immutable",
        )
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
        expected_stage_commands = {
            "H1": (
                "[py, '-m', 'quant.historical_replay_h1', day.isoformat(), "
                "'--run-id', run_id, '--max-interior-gap-seconds', '5', "
                "'--persist-certified']"
            ),
            "H2B": (
                "[py, '-m', 'quant.historical_evidence_verifier', run_id, "
                "'--dataset-digest', dataset_digest, '--configuration-digest', "
                "configuration_digest, '--frame-count', str(frame_count)]"
            ),
            "H2C_RESOLVE": (
                "[py, '-m', 'quant.historical_outcomes', 'resolve-outcomes', "
                "run_id, '--dataset-digest', dataset_digest, "
                "'--configuration-digest', configuration_digest, "
                "'--frame-count', str(frame_count)]"
            ),
            "H2C_SCORE": (
                "[py, '-m', 'quant.historical_outcomes', 'score', run_id]"
            ),
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
            self.assertIn(stage.value, expected_stage_commands)
            expected_command = ast.parse(
                expected_stage_commands[stage.value],
                mode="eval",
            ).body
            self.assertEqual(
                ast.dump(command, include_attributes=False),
                ast.dump(expected_command, include_attributes=False),
                f"{stage.value} command and selectors must remain exact",
            )
            observed_stage_modules[stage.value] = command.elts[2].value
        self.assertEqual(observed_stage_modules, expected_stage_modules)
        run_json_loads = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "run_json"
        )
        self.assertEqual(
            set(run_json_loads),
            {dispatch.func for dispatch in stage_dispatches},
        )
        direct_run_json_calls = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_run_json"
        )
        self.assertFalse(
            direct_run_json_calls,
            "direct _run_json dispatch is forbidden",
        )
        run_json_default_loads = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "_run_json"
        )
        self.assertEqual(len(run_json_default_loads), 1)
        execute_functions = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "execute"
        )
        self.assertEqual(len(execute_functions), 1)
        execute_function = execute_functions[0]
        self.assertIn(
            run_json_default_loads[0],
            tuple(ast.walk(execute_function.args)),
        )
        py_writes = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id == "py"
            and isinstance(node.ctx, (ast.Store, ast.Del))
        )
        self.assertEqual(
            len(py_writes),
            1,
            "the stage interpreter binding cannot be rebound or deleted",
        )
        py_initializer = parents.get(py_writes[0])
        self.assertIsInstance(py_initializer, ast.Assign)
        self.assertEqual(py_initializer.targets, [py_writes[0]])
        self.assertIs(parents.get(py_initializer), execute_function)
        self.assertIsInstance(py_initializer.value, ast.Attribute)
        self.assertIsInstance(py_initializer.value.value, ast.Name)
        self.assertEqual(py_initializer.value.value.id, "sys")
        self.assertEqual(py_initializer.value.attr, "executable")
        self.assertIsInstance(py_initializer.value.ctx, ast.Load)
        sys_executable_references = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
            and node.attr == "executable"
        )
        self.assertEqual(sys_executable_references, (py_initializer.value,))
        py_loads = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id == "py"
            and isinstance(node.ctx, ast.Load)
        )
        self.assertEqual(len(py_loads), 4)
        self.assertEqual(
            set(py_loads),
            {dispatch.args[0].elts[0] for dispatch in stage_dispatches},
            "py may only select the interpreter for the four frozen commands",
        )
        self.assertFalse(
            tuple(
                node
                for node in ast.walk(tree)
                if (
                    isinstance(node, ast.arg)
                    and node.arg == "py"
                )
                or (
                    isinstance(node, (ast.Global, ast.Nonlocal))
                    and "py" in node.names
                )
            ),
            "py cannot be introduced through an argument or scope declaration",
        )
        dynamic_calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {
                "__import__",
                "compile",
                "delattr",
                "eval",
                "exec",
                "getattr",
                "globals",
                "locals",
                "setattr",
                "vars",
            }
        }
        self.assertFalse(
            dynamic_calls,
            f"dynamic import or execution is forbidden: {dynamic_calls}",
        )
        dangerous_builtin_names = {
            "__builtins__",
            "__import__",
            "builtins",
            "compile",
            "eval",
            "exec",
        }
        indirect_dynamic_access = tuple(
            node
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.Name)
                and node.id in dangerous_builtin_names
            )
            or (
                isinstance(node, ast.Attribute)
                and node.attr in (
                    {"__builtins__", "__import__"}
                    | DANGEROUS_INTROSPECTION_ATTRIBUTES
                )
            )
            or (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in dangerous_builtin_names
            )
        )
        self.assertFalse(
            indirect_dynamic_access,
            "indirect builtin import or execution access is forbidden",
        )
        dynamic_module_access = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "vars"}
            and node.args
            and isinstance(node.args[0], ast.Name)
            and {
                origin.split(".")[0]
                for origin in resolve_module_imports(node.args[0])
            }.intersection({"os", "subprocess", "sys"})
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
        day_loop = day_loops[0]
        self.assertIn(day_loop, tuple(ast.walk(execute_function)))
        self.assertIs(
            parents.get(day_loop),
            execute_function,
            "the per-day loop must remain in execute's direct body",
        )
        self.assertLess(
            execute_function.body.index(py_initializer),
            execute_function.body.index(day_loop),
            "the immutable interpreter must be selected before the per-day loop",
        )
        day_tries = tuple(
            statement
            for statement in day_loop.body
            if isinstance(statement, ast.Try)
        )
        self.assertEqual(len(day_tries), 1)
        day_try = day_tries[0]
        expected_dispatch_order = (
            "H1",
            "H2B",
            "H2C_RESOLVE",
            "H2C_SCORE",
        )
        ordered_dispatches = tuple(
            sorted(stage_dispatches, key=lambda node: (node.lineno, node.col_offset))
        )
        self.assertEqual(
            tuple(dispatch.args[1].value for dispatch in ordered_dispatches),
            expected_dispatch_order,
            "the per-day stage dispatch order is frozen",
        )
        expected_result_names = {
            "H1": "h1",
            "H2B": "verified",
            "H2C_RESOLVE": "outcome",
            "H2C_SCORE": "scoring",
        }
        dispatch_carriers = []
        for dispatch in ordered_dispatches:
            stage = dispatch.args[1].value
            assignment = parents.get(dispatch)
            self.assertIsInstance(
                assignment,
                ast.Assign,
                f"{stage} must remain a direct assignment dispatch",
            )
            self.assertIs(assignment.value, dispatch)
            self.assertEqual(len(assignment.targets), 1)
            self.assertIsInstance(assignment.targets[0], ast.Name)
            self.assertEqual(assignment.targets[0].id, expected_result_names[stage])
            if stage == "H1":
                known_guard = parents.get(assignment)
                self.assertIsInstance(known_guard, ast.If)
                self.assertIn(assignment, known_guard.body)
                self.assertFalse(known_guard.orelse)
                self.assertIsInstance(known_guard.test, ast.UnaryOp)
                self.assertIsInstance(known_guard.test.op, ast.Not)
                self.assertIsInstance(known_guard.test.operand, ast.Name)
                self.assertEqual(known_guard.test.operand.id, "known")
                self.assertIs(parents.get(known_guard), day_try)
                dispatch_carriers.append(known_guard)
            else:
                self.assertIs(
                    parents.get(assignment),
                    day_try,
                    f"{stage} cannot move into a lambda or control-flow branch",
                )
                dispatch_carriers.append(assignment)
        dispatch_carrier_positions = tuple(
            day_try.body.index(carrier) for carrier in dispatch_carriers
        )
        self.assertEqual(
            dispatch_carrier_positions,
            tuple(sorted(dispatch_carrier_positions)),
            "stage dispatch carriers must remain in straight-line source order",
        )
        expected_interstage_guards = (
            (
                (
                    "h1.get('execution_stage') != 'REPLAY_COMPLETE' or "
                    "h1.get('data_status') != 'CERTIFIED'",
                    "StageFailure('H1', 'NOT_CERTIFIED', h1)",
                ),
                (
                    "not isinstance(dataset_digest, str) or "
                    "not isinstance(configuration_digest, str) or "
                    "isinstance(frame_count, bool) or "
                    "not isinstance(frame_count, int) or frame_count < 1",
                    "StageFailure('MANIFEST', 'INVALID_SESSION_LINEAGE')",
                ),
            ),
            (
                (
                    "verified.get('verification_status') != 'VERIFIED' or "
                    "verified.get('manifest_count') != 1 or "
                    "verified.get('frame_count') != frame_count or "
                    "verified.get('forecast_count') != expected_forecasts or "
                    "verified.get('quant_count') != 12 or "
                    "verified.get('horizon_count') != 6 or "
                    "verified.get('dataset_digest') != dataset_digest or "
                    "verified.get('configuration_digest') != configuration_digest",
                    "StageFailure('H2B', 'VERIFIED_RECEIPT_MISMATCH', verified)",
                ),
            ),
            (),
        )
        expected_guard_containers = (
            (dispatch_carriers[0], day_try),
            (day_try,),
            (),
        )
        for pair_index, expected_guards in enumerate(expected_interstage_guards):
            first = dispatch_carrier_positions[pair_index]
            second = dispatch_carrier_positions[pair_index + 1]
            region_nodes = tuple(
                node
                for statement in day_try.body[first:second]
                for node in ast.walk(statement)
            )
            unexpected_terminators = tuple(
                node
                for node in region_nodes
                if isinstance(
                    node,
                    (
                        ast.Assert,
                        ast.Break,
                        ast.Continue,
                        ast.Return,
                        ast.Yield,
                        ast.YieldFrom,
                    ),
                )
            )
            self.assertFalse(
                unexpected_terminators,
                "terminating control flow cannot skip a later stage dispatch",
            )
            early_exit_calls = tuple(
                node
                for node in region_nodes
                if is_explicit_exit_call(node)
            )
            self.assertFalse(
                early_exit_calls,
                "explicit exit calls cannot skip a later stage dispatch",
            )
            raises = tuple(
                sorted(
                    (node for node in region_nodes if isinstance(node, ast.Raise)),
                    key=lambda node: (node.lineno, node.col_offset),
                )
            )
            self.assertEqual(
                len(raises),
                len(expected_guards),
                "no new raise may skip a later stage dispatch",
            )
            observed_guards = []
            for raise_index, raise_node in enumerate(raises):
                guard = parents.get(raise_node)
                self.assertIsInstance(guard, ast.If)
                self.assertEqual(guard.body, [raise_node])
                self.assertFalse(guard.orelse)
                expected_container = expected_guard_containers[pair_index][raise_index]
                self.assertIs(parents.get(guard), expected_container)
                self.assertIn(guard, expected_container.body)
                self.assertIsNotNone(raise_node.exc)
                self.assertIsNone(raise_node.cause)
                self.assertLess(
                    (
                        ordered_dispatches[pair_index].lineno,
                        ordered_dispatches[pair_index].col_offset,
                    ),
                    (raise_node.lineno, raise_node.col_offset),
                    "receipt validation can terminate only after its stage dispatch",
                )
                observed_guards.append(
                    (
                        ast.dump(guard.test, include_attributes=False),
                        ast.dump(raise_node.exc, include_attributes=False),
                    )
                )
            self.assertEqual(
                tuple(observed_guards),
                tuple(
                    (
                        ast.dump(
                            ast.parse(test_source, mode="eval").body,
                            include_attributes=False,
                        ),
                        ast.dump(
                            ast.parse(exception_source, mode="eval").body,
                            include_attributes=False,
                        ),
                    )
                    for test_source, exception_source in expected_guards
                ),
                "only the exact frozen receipt-validation raises may separate stages",
            )
        self.assertEqual(
            {
                node
                for carrier in dispatch_carriers
                for node in ast.walk(carrier)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "run_json"
            },
            set(stage_dispatches),
            "no alternate stage dispatch may exist outside the frozen day path",
        )
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

    def test_complete_h1_runtime_closure_is_frozen_and_sequential(self):
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
                imported_bindings = {}
                star_imports = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imported_roots.add(alias.name.split(".")[0])
                            imported_bindings[
                                alias.asname or alias.name.split(".")[0]
                            ] = alias.name
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imported_roots.add(node.module.split(".")[0])
                            direct_imports.update(
                                (node.module, alias.name)
                                for alias in node.names
                            )
                            imported_bindings.update({
                                alias.asname or alias.name:
                                    f"{node.module}.{alias.name}"
                                for alias in node.names
                            })
                        if any(alias.name == "*" for alias in node.names):
                            star_imports.add(node.module or ".")
                self.assertFalse(
                    imported_roots.intersection(FORBIDDEN_STAGE_IMPORT_ROOTS),
                    f"parallel package imported by {relative_path}",
                )
                self.assertFalse(
                    star_imports,
                    f"star import in {relative_path}: {star_imports}",
                )
                direct_process_imports = {
                    item
                    for item in direct_imports
                    if is_sensitive_from_import(*item)
                }
                self.assertFalse(
                    direct_process_imports,
                    f"direct process import in {relative_path}",
                )
                reexported_process_modules = sensitive_module_reexports(
                    tree,
                    imported_bindings,
                )
                self.assertFalse(
                    reexported_process_modules,
                    f"process module re-export in {relative_path}",
                )
                parents, resolve_module_imports = lexical_import_origins(tree)
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
                    and (
                        node.func.id in {
                            "__import__", "compile", "eval", "exec", "globals", "locals",
                        }
                        or (node.func.id == "vars" and not node.args)
                    )
                }
                self.assertFalse(
                    dynamic_calls,
                    f"dynamic execution in {relative_path}: {dynamic_calls}",
                )
                introspection_calls = tuple(
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"delattr", "getattr", "setattr", "vars"}
                )
                self.assertEqual(
                    len(introspection_calls),
                    EXPECTED_INTROSPECTION_CALL_COUNTS.get(relative_path, 0),
                    f"introspection call drift in {relative_path}",
                )
                for call in introspection_calls:
                    self.assertFalse(call.keywords)
                    if call.func.id == "vars":
                        self.assertEqual(relative_path, "quant/v9_v4a_evidence.py")
                        self.assertEqual(len(call.args), 1)
                        self.assertIsInstance(call.args[0], ast.Name)
                        self.assertEqual(call.args[0].id, "value")
                        continue
                    self.assertEqual(call.func.id, "getattr")
                    self.assertIn(len(call.args), {2, 3})
                    attribute_name = call.args[1]
                    if isinstance(attribute_name, ast.Constant):
                        self.assertIsInstance(attribute_name.value, str)
                        self.assertNotIn(
                            attribute_name.value,
                            DANGEROUS_INTROSPECTION_ATTRIBUTES,
                        )
                    else:
                        self.assertIsInstance(attribute_name, ast.Name)
                        self.assertIn(
                            attribute_name.id,
                            ALLOWED_DYNAMIC_GETATTR_NAMES.get(relative_path, set()),
                        )
                dangerous_builtin_names = {
                    "__builtins__",
                    "__import__",
                    "builtins",
                    "compile",
                    "eval",
                    "exec",
                }
                indirect_dynamic_access = tuple(
                    node
                    for node in ast.walk(tree)
                    if (
                        isinstance(node, ast.Name)
                        and node.id in dangerous_builtin_names
                    )
                    or (
                        isinstance(node, ast.Attribute)
                        and node.attr in (
                            {"__builtins__", "__import__"}
                            | DANGEROUS_INTROSPECTION_ATTRIBUTES
                        )
                    )
                    or (
                        isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and node.value in dangerous_builtin_names
                    )
                )
                self.assertFalse(
                    indirect_dynamic_access,
                    f"indirect dynamic execution in {relative_path}",
                )
                allowed_references = {("os", "environ")}
                if relative_path == "quant/historical_replay_h1.py":
                    allowed_references.add(("subprocess", "run"))
                if relative_path in {
                    "quant/v9_v2b_calibration.py",
                    "quant/v9_v2c_covariance.py",
                }:
                    allowed_references.add(("sys", "float_info"))
                qualified_references = {
                    (origin.split(".")[0], node.attr)
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    for origin in resolve_module_imports(node.value)
                    if origin.split(".")[0] in {"os", "subprocess", "sys"}
                }
                self.assertFalse(
                    qualified_references - allowed_references,
                    f"process reference in {relative_path}: "
                    f"{qualified_references - allowed_references}",
                )
                bare_module_loads = tuple(
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Name)
                    and isinstance(node.ctx, ast.Load)
                    and resolve_module_imports(node)
                    and not (
                        isinstance(parents.get(node), ast.Attribute)
                        and parents[node].value is node
                    )
                )
                self.assertFalse(
                    bare_module_loads,
                    f"imported module object escapes in {relative_path}",
                )
                dynamic_module_access = tuple(
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"getattr", "vars"}
                    and node.args
                    and isinstance(node.args[0], ast.Name)
                    and {
                        origin.split(".")[0]
                        for origin in resolve_module_imports(node.args[0])
                    }.intersection({"os", "subprocess", "sys"})
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
                    and "subprocess" in {
                        origin.split(".")[0]
                        for origin in resolve_module_imports(node.value)
                    }
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

    def test_frozen_runtime_contains_complete_local_dependency_closure(self):
        frozen_paths = set(SEQUENTIAL_RUNTIME_SOURCE_SHA256)
        for relative_path in sorted(frozen_paths):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            dependencies = local_runtime_dependencies(
                relative_path,
                ast.parse(source),
            )
            with self.subTest(module=relative_path):
                self.assertFalse(
                    dependencies - frozen_paths,
                    f"unfrozen local dependencies imported by {relative_path}: "
                    f"{dependencies - frozen_paths}",
                )

    def test_freeze_law_requires_exact_metric_and_receipt_correlation(self):
        law = " ".join(FREEZE.read_text(encoding="utf-8").split())
        for clause in (
            "parallel runtime disabled",
            "H1 → H2B → H2C_RESOLVE → H2C_SCORE",
            "exactly two worker processes",
            "non-transaction-pooled control connection",
            "`SELECT pg_try_advisory_lock(8098937340306602170)` exactly once",
            "cross-process and cross-host single-coordinator exclusion",
            "one configured Linux execution host and in the one PID namespace identity",
            "device/inode identity of `/proc/self/ns/pid`",
            "`pg_try_advisory_lock(-5133988379539764595)` for `2026-06-15`",
            "`pg_try_advisory_lock(8459531074882316998)` for `2026-07-22`",
            "separate durable OS processes and process/service failure domains, not separate hosts",
            "exactly two claim-only date guardians outside",
            "`pipe2(O_CLOEXEC)`",
            "authenticated local Unix-domain `SOCK_SEQPACKET` socket using `SCM_RIGHTS`",
            "after `SO_PEERCRED` and generation verification",
            "exact allowlisted pre-spawn inheritance into that guardian",
            "coordinator remains the sole write-end owner",
            "exact guardian becomes the sole read-end owner",
            "supervisor closes every temporary pipe-descriptor copy",
            "`cgroup.freeze`, `cgroup.kill`",
            "`cgroup.events` reports `populated 0`",
            "opens a `pidfd` for the exact coordinator OS PID",
            "calls `pidfd_open()` for the exact recorded coordinator OS PID",
            "verifies its procfs start-time ticks against the generation record",
            "host or PID-namespace identity that is missing, stale, unverifiable, or mismatched fails closed",
            "generation record is independent of PostgreSQL sessions",
            "`CLAIMING`, `ACTIVE`, `CLEANING`, or unknown state blocks replacement",
            "atomically compare-and-swaps that exact attested `CLEAN` version",
            "every later transition is conditional on the exact predecessor version and generation",
            "pre-claim path requires no new terminal receipt",
            "failure before the first supervisor compare-and-swap",
            "every unchanged supervisor re-attests the exact prior `CLEAN` version",
            "every exclusive date fence still held by its control session exactly once",
            "must not be unlocked a second time",
            "`pg_try_advisory_lock_shared`",
            "Both claim receipts are required before either guardian may create its single worker",
            "`SELECT pg_backend_pid()`",
            "at an interval of at most five seconds",
            "reap its worker",
            "A parent-death signal or process-group kill alone is not accepted",
            "After reaping the guardian and independently reproving `populated 0`",
            "Every replacement must repeat both supervisor checks in step 4",
            "release `8098937340306602170` exactly once in `finally`",
            "database restart or failover drops all three advisory-lock sessions",
            "restart or fail over PostgreSQL so all three advisory-lock sessions drop",
            "two-coordinator failover race test",
            "only one generation to obtain both supervisor claims",
            "zero surviving descendant PIDs",
            "any old/new generation overlap permanently fails H2-D-3",
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
        self.assertIn("complete local H1 runtime dependency closure", root_law)
        self.assertIn("exact 72-metric hash byte encoding", root_law)
        self.assertIn("one configured Linux execution host and one PID namespace identity", root_law)
        self.assertIn("not separate hosts", root_law)
        self.assertIn("H2-D-2 is a design freeze only", root_law)
        self.assertIn("H2-D-3 — Parallel Canary (not authorized)", phases)
        self.assertIn("No within-date concurrency or evidence writes", phases)

    def test_q10_audit_uses_frames_not_outcomes_in_forecast_equation(self):
        audit = Q10_AUDIT.read_text(encoding="utf-8")
        self.assertIn("10,445 frames × 12 families × 6 horizons", audit)
        self.assertNotIn("62,670 frames ×", audit)


if __name__ == "__main__":
    unittest.main()
