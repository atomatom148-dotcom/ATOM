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
    "pydoc.browse",
    "pydoc._start_server",
}
EXECUTABLE_DESERIALIZER_FULL_IMPORT_NAMES = {
    "_pickle.load",
    "_pickle.loads",
    "cloudpickle.load",
    "cloudpickle.loads",
    "dill.load",
    "dill.load_module",
    "dill.loads",
    "dill.Unpickler.load",
    "joblib.load",
    "pandas.read_pickle",
    "pickle.load",
    "pickle.loads",
    "pickle.Unpickler.load",
    "_pickle.Unpickler.load",
    "shelve.open",
    "yaml.unsafe_load",
    "yaml.unsafe_load_all",
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
            scope: ast.AST,
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

    module_binding_events = lexical_binding_events(tree)
    integrity_import_parents, resolve_integrity_import = lexical_import_origins(
        tree
    )

    def is_module_binding_scope(node: ast.AST) -> bool:
        parent = integrity_import_parents.get(node)
        while parent is not None and parent is not tree:
            if isinstance(parent, (
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.DictComp,
                ast.FunctionDef,
                ast.GeneratorExp,
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
            )):
                return False
            parent = integrity_import_parents.get(parent)
        return parent is tree

    def assigned_expression(target: ast.Name) -> ast.AST | None:
        current: ast.AST = target
        path = []
        parent = integrity_import_parents.get(current)
        while isinstance(parent, (ast.List, ast.Tuple)):
            path.append(parent.elts.index(current))
            current = parent
            parent = integrity_import_parents.get(current)
        if isinstance(parent, ast.Starred):
            return None
        value = None
        if isinstance(parent, ast.Assign) and current in parent.targets:
            value = parent.value
        elif isinstance(parent, (ast.AnnAssign, ast.NamedExpr)):
            if parent.target is current:
                value = parent.value
        for index in reversed(path):
            if not isinstance(value, (ast.List, ast.Tuple)):
                return None
            if index >= len(value.elts):
                return None
            value = value.elts[index]
        return value

    def module_alias_is_json(
            name: str,
            reference: ast.AST,
            before: tuple[int, int],
            seen: frozenset[tuple[str, tuple[int, int]]] = frozenset(),
    ) -> bool:
        marker = (name, before)
        if marker in seen:
            return False
        seen = seen | {marker}
        module_body = tree.body

        def definitely_precedes(node: ast.AST) -> bool:
            event_owner = node
            while (
                not isinstance(event_owner, ast.stmt)
                and integrity_import_parents.get(event_owner) is not None
            ):
                event_owner = integrity_import_parents[event_owner]
            event_child = node
            while (
                integrity_import_parents.get(event_child) is not tree
                and integrity_import_parents.get(event_child) is not None
            ):
                event_child = integrity_import_parents[event_child]
            reference_child = reference
            while (
                integrity_import_parents.get(reference_child) is not tree
                and integrity_import_parents.get(reference_child) is not None
            ):
                reference_child = integrity_import_parents[reference_child]
            return (
                event_child is event_owner
                and
                not isinstance(event_owner, ast.AugAssign)
                and
                event_child in module_body
                and reference_child in module_body
                and module_body.index(event_child) < module_body.index(reference_child)
            )

        events = []
        for node in ast.walk(tree):
            position = (
                getattr(node, "lineno", -1),
                getattr(node, "col_offset", -1),
            )
            if position >= before or not is_module_binding_scope(node):
                continue
            if (
                isinstance(node, ast.Name)
                and node.id == name
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and definitely_precedes(node)
            ):
                events.append((position, node))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.asname or alias.name.split(".", 1)[0]) == name:
                        if definitely_precedes(alias):
                            events.append((position, alias))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if (alias.asname or alias.name) == name:
                        if definitely_precedes(alias):
                            events.append((position, alias))
            elif isinstance(node, (
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.FunctionDef,
            )) and node.name == name and definitely_precedes(node):
                events.append((position, node))
        if not events:
            return False
        position, event = max(events, key=lambda item: item[0])
        if isinstance(event, ast.alias):
            return event.name == "json"
        if not isinstance(event, ast.Name) or isinstance(event.ctx, ast.Del):
            return False
        value = assigned_expression(event)
        if isinstance(value, ast.Name):
            return module_alias_is_json(value.id, event, position, seen)
        return False

    lexical_scope_types = (
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.DictComp,
        ast.FunctionDef,
        ast.GeneratorExp,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
    )

    def lexical_scope(node: ast.AST) -> ast.AST:
        parent = integrity_import_parents.get(node)
        while parent is not None and parent is not tree:
            if isinstance(parent, lexical_scope_types):
                return parent
            parent = integrity_import_parents.get(parent)
        return tree

    def outer_lexical_scope(scope: ast.AST) -> ast.AST:
        if scope is tree:
            return tree
        parent = integrity_import_parents.get(scope)
        while parent is not None and parent is not tree:
            if isinstance(parent, lexical_scope_types):
                if (
                    isinstance(scope, (
                        ast.AsyncFunctionDef,
                        ast.FunctionDef,
                        ast.Lambda,
                    ))
                    and isinstance(parent, ast.ClassDef)
                ):
                    parent = integrity_import_parents.get(parent)
                    continue
                return parent
            parent = integrity_import_parents.get(parent)
        return tree

    def lexical_alias_is_json(
            name: str,
            scope: ast.AST,
            reference: ast.AST,
            before: tuple[int, int],
            seen: frozenset[
                tuple[str, int, tuple[int, int]]
        ] = frozenset(),
    ) -> bool:
        if scope is tree:
            return module_alias_is_json(name, reference, before)
        marker = (name, id(scope), before)
        if marker in seen:
            return False
        seen = seen | {marker}
        direct_nodes = tuple(
            node for node in ast.walk(scope)
            if lexical_scope(node) is scope
        )
        if any(
            isinstance(node, ast.Global) and name in node.names
            for node in direct_nodes
        ):
            return module_alias_is_json(name, reference, before)
        if any(
            isinstance(node, ast.Nonlocal) and name in node.names
            for node in direct_nodes
        ):
            return lexical_alias_is_json(
                name,
                outer_lexical_scope(scope),
                reference,
                before,
                seen,
            )
        scope_body = scope.body if isinstance(scope.body, list) else []

        def definitely_precedes(node: ast.AST) -> bool:
            event_owner = node
            while (
                not isinstance(event_owner, ast.stmt)
                and integrity_import_parents.get(event_owner) is not None
            ):
                event_owner = integrity_import_parents[event_owner]
            event_child = node
            while (
                integrity_import_parents.get(event_child) is not scope
                and integrity_import_parents.get(event_child) is not None
            ):
                event_child = integrity_import_parents[event_child]
            reference_child = reference
            while (
                integrity_import_parents.get(reference_child) is not scope
                and integrity_import_parents.get(reference_child) is not None
            ):
                reference_child = integrity_import_parents[reference_child]
            return (
                event_child is event_owner
                and
                not isinstance(event_owner, ast.AugAssign)
                and
                event_child in scope_body
                and reference_child in scope_body
                and scope_body.index(event_child) < scope_body.index(reference_child)
            )

        events = []
        for node in direct_nodes:
            position = (
                getattr(node, "lineno", -1),
                getattr(node, "col_offset", -1),
            )
            if (
                isinstance(node, ast.Name)
                and node.id == name
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and definitely_precedes(node)
            ):
                events.append((position, node))
            elif isinstance(node, ast.arg) and node.arg == name:
                events.append((position, node))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.asname or alias.name.split(".", 1)[0]) == name:
                        if definitely_precedes(alias):
                            events.append((position, alias))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if (alias.asname or alias.name) == name:
                        if definitely_precedes(alias):
                            events.append((position, alias))
            elif (
                node is not scope
                and isinstance(node, (
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.FunctionDef,
                ))
                and node.name == name
                and definitely_precedes(node)
            ):
                events.append((position, node))
        if not events:
            return lexical_alias_is_json(
                name,
                outer_lexical_scope(scope),
                reference,
                before,
                seen,
            )
        prior_events = [event for event in events if event[0] < before]
        if not prior_events:
            return False
        position, event = max(prior_events, key=lambda item: item[0])
        if isinstance(event, ast.alias):
            return event.name == "json"
        if isinstance(event, ast.arg):
            positional = scope.args.posonlyargs + scope.args.args
            defaults = {
                argument.arg: default
                for argument, default in zip(
                    positional[-len(scope.args.defaults):],
                    scope.args.defaults,
                )
            } if scope.args.defaults else {}
            defaults.update(
                (argument.arg, default)
                for argument, default in zip(
                    scope.args.kwonlyargs,
                    scope.args.kw_defaults,
                )
                if default is not None
            )
            default = defaults.get(event.arg)
            return (
                isinstance(default, ast.Name)
                and lexical_alias_is_json(
                    default.id,
                    outer_lexical_scope(scope),
                    scope,
                    (scope.lineno, scope.col_offset),
                    seen,
                )
            )
        if not isinstance(event, ast.Name) or isinstance(event.ctx, ast.Del):
            return False
        value = assigned_expression(event)
        if isinstance(value, ast.Name):
            return lexical_alias_is_json(
                value.id,
                scope,
                event,
                position,
                seen,
            )
        return False

    def canonical_json_receiver(node: ast.Name) -> bool:
        return lexical_alias_is_json(
            node.id,
            lexical_scope(node),
            node,
            (node.lineno, node.col_offset),
        )

    json_dumps_mutations = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and node.attr == "dumps"
        and isinstance(node.value, ast.Name)
        and canonical_json_receiver(node.value)
    )

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
    protected_eager_builtins = {
        "all",
        "any",
        "dict",
        "frozenset",
        "iter",
        "list",
        "max",
        "min",
        "set",
        "sorted",
        "sum",
        "tuple",
    }
    if protected_eager_builtins.intersection(module_binding_events):
        record("execute-pre-dispatch-termination")
    execute_days_parameter = None
    if execute_function is not None and execute_function.args.args:
        candidate = execute_function.args.args[0]
        if candidate.arg == "days":
            execute_days_parameter = candidate
    if (
        execute_days_parameter is None
        or execute_binding_events.get("days", ())
        != (execute_days_parameter,)
    ):
        record("execute-days-binding")
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
    existing_parameter = None
    if execute_function is not None:
        existing_parameter = next((
            argument
            for argument in execute_function.args.kwonlyargs
            if argument.arg == "existing"
        ), None)
    if (
        existing_parameter is None
        or execute_binding_events.get("existing", ())
        != (existing_parameter,)
    ):
        record("execute-existing-binding")

    protected_execute_names = {
        "configuration_digest",
        "dataset_digest",
        "day",
        "days",
        "existing",
        "frame_count",
        "run_id",
        "run_json",
    }
    nested_execute_nonlocals = {
        name
        for node in ast.walk(execute_function)
        if execute_function is not None and isinstance(node, ast.Nonlocal)
        for name in node.names
        if name in protected_execute_names
    }
    if "run_json" in nested_execute_nonlocals:
        record("execute-dispatch-binding")
    if "existing" in nested_execute_nonlocals:
        record("execute-existing-binding")
    if "day" in nested_execute_nonlocals:
        record("execute-day-binding")
    if "days" in nested_execute_nonlocals:
        record("execute-days-binding")
    if nested_execute_nonlocals.intersection({
        "configuration_digest",
        "dataset_digest",
        "frame_count",
        "run_id",
    }):
        record("execute-lineage-binding")

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

    existing_assignments = (
        tuple(
            node for node in direct_lexical_nodes(execute_function)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.targets[0].ctx, ast.Store)
            and node.targets[0].id == "manifests"
            and node.type_comment is None
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and isinstance(node.value.func.ctx, ast.Load)
            and node.value.func.id == "existing"
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Name)
            and isinstance(node.value.args[0].ctx, ast.Load)
            and node.value.args[0].id == "day"
            and not node.value.keywords
        )
        if execute_function is not None
        else ()
    )
    existing_assignment = (
        existing_assignments[0]
        if len(existing_assignments) == 1
        else None
    )
    if not (
        existing_assignment is not None
        and execute_parents.get(existing_assignment) is day_try
        and direct_lexical_name_loads(execute_function, "existing")
        == (existing_assignment.value.func,)
    ):
        record("execute-existing-call")

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
    nested_main_nonlocals = {
        name
        for node in ast.walk(main_function)
        if main_function is not None and isinstance(node, ast.Nonlocal)
        for name in node.names
        if name in {"days", "output"}
    }
    if "days" in nested_main_nonlocals:
        record("days-selection-mutation")
    if "output" in nested_main_nonlocals:
        record("main-output-binding")
    top_level_json_imports = tuple(
        (statement, alias)
        for statement in tree.body
        if isinstance(statement, ast.Import)
        for alias in statement.names
        if alias.name == "json"
    )
    canonical_json_alias = (
        top_level_json_imports[0][1]
        if (
            len(top_level_json_imports) == 1
            and top_level_json_imports[0][0].names
            == [top_level_json_imports[0][1]]
            and top_level_json_imports[0][1].asname is None
        )
        else None
    )
    if (
        canonical_json_alias is None
        or module_binding_events.get("json", ()) != (canonical_json_alias,)
        or module_binding_events.get("print", ())
        or json_dumps_mutations
        or main_binding_events.get("json", ())
        or main_binding_events.get("print", ())
        or any(
            isinstance(node, ast.Global)
            and {"json", "print"}.intersection(node.names)
            for node in ast.walk(tree)
        )
    ):
        record("main-output-call-target")
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
            and direct_lexical_name_loads(main_function, "print")
            == (print_call.func,)
            and not print_call.keywords
            and isinstance(dumps_call, ast.Call)
            and isinstance(dumps_call.func, ast.Attribute)
            and dumps_call.func.attr == "dumps"
            and isinstance(dumps_call.func.value, ast.Name)
            and dumps_call.func.value.id == "json"
            and direct_lexical_name_loads(main_function, "json")
            == (dumps_call.func.value,)
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

    def evaluated_in_execute(node: ast.AST) -> bool:
        original = node
        child = node
        parent = execute_parents.get(child)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child in parent.body:
                    return False
                if annotations_are_deferred:
                    annotation_roots = [
                        argument.annotation
                        for argument in (
                            *parent.args.posonlyargs,
                            *parent.args.args,
                            *parent.args.kwonlyargs,
                        )
                        if argument.annotation is not None
                    ]
                    annotation_roots.extend(
                        argument.annotation
                        for argument in (parent.args.vararg, parent.args.kwarg)
                        if argument is not None
                        and argument.annotation is not None
                    )
                    if parent.returns is not None:
                        annotation_roots.append(parent.returns)
                    if any(
                        original is root
                        or is_descendant_of(original, root)
                        for root in annotation_roots
                    ):
                        return False
            elif isinstance(parent, ast.Lambda) and child is parent.body:
                return False
            child = parent
            parent = execute_parents.get(child)
        return parent is execute_function

    def is_descendant_of(node: ast.AST, ancestor: ast.AST) -> bool:
        parent = execute_parents.get(node)
        while parent is not None:
            if parent is ancestor:
                return True
            parent = execute_parents.get(parent)
        return False

    def nearest_enclosing_loop(node: ast.AST) -> ast.AST | None:
        parent = execute_parents.get(node)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, (ast.For, ast.AsyncFor, ast.While)):
                return parent
            parent = execute_parents.get(parent)
        return None

    def execute_exit_callable(
            expression: ast.AST,
            reference: ast.AST,
            before: tuple[int, int],
            seen: frozenset[str] = frozenset(),
    ) -> bool:
        if isinstance(expression, ast.Name):
            if expression.id in {"exit", "quit"}:
                return True
            if expression.id in seen:
                return False
            candidates = []
            for node in direct_lexical_nodes(execute_function):
                if (
                    execute_function is None
                    or not isinstance(node, ast.Name)
                    or node.id != expression.id
                    or not isinstance(node.ctx, (ast.Store, ast.Del))
                    or not hasattr(node, "lineno")
                    or (node.lineno, node.col_offset) >= before
                ):
                    continue
                owner: ast.AST = node
                while (
                    not isinstance(owner, ast.stmt)
                    and execute_parents.get(owner) is not None
                ):
                    owner = execute_parents[owner]
                owner_parent = execute_parents.get(owner)
                definitely_dominates = False
                if isinstance(owner, (ast.Assign, ast.AnnAssign, ast.Expr)):
                    for field_name in ("body", "orelse", "finalbody"):
                        block = getattr(owner_parent, field_name, None)
                        if not isinstance(block, list) or owner not in block:
                            continue
                        reference_child = reference
                        while (
                            execute_parents.get(reference_child) is not owner_parent
                            and execute_parents.get(reference_child) is not None
                        ):
                            reference_child = execute_parents[reference_child]
                        if (
                            reference_child in block
                            and block.index(owner) < block.index(reference_child)
                        ):
                            definitely_dominates = True
                            break
                candidates.append((
                    (node.lineno, node.col_offset),
                    node,
                    definitely_dominates,
                ))
            if not candidates:
                return False
            definite = [event for event in candidates if event[2]]
            latest_definite = (
                max(definite, key=lambda event: event[0])
                if definite
                else None
            )
            definite_position = latest_definite[0] if latest_definite else (-1, -1)

            def event_is_exit(event: tuple[tuple[int, int], ast.Name, bool]) -> bool:
                position, target, _ = event
                value = assigned_expression(target)
                return (
                    value is not None
                    and execute_exit_callable(
                        value,
                        target,
                        position,
                        seen | {expression.id},
                    )
                )

            if latest_definite is not None and event_is_exit(latest_definite):
                return True
            return any(
                position > definite_position
                and not dominates
                and event_is_exit(event)
                for event in candidates
                for position, _, dominates in (event,)
            )
        if not isinstance(expression, ast.Attribute):
            return False
        return (
            expression.attr == "exit"
            or (
                expression.attr == "_exit"
                and isinstance(expression.value, ast.Name)
                and expression.value.id == "os"
            )
        )

    def is_execute_exit_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and execute_exit_callable(
                node.func,
                node.func,
                (node.lineno, node.col_offset),
            )
        )

    weekend_test_dump = ast.dump(
        ast.parse("day.weekday() >= 5", mode="eval").body,
        include_attributes=False,
    )
    conflict_test_dump = ast.dump(
        ast.parse("len(manifests) > 1", mode="eval").body,
        include_attributes=False,
    )
    conflict_raise_dump = ast.dump(
        ast.parse(
            "raise StageFailure('EXISTING', 'CONFLICTING_SESSION_RUNS')"
        ).body[0].exc,
        include_attributes=False,
    )

    def is_canonical_pre_dispatch_terminator(node: ast.AST) -> bool:
        parent = execute_parents.get(node)
        if not isinstance(parent, ast.If) or node not in parent.body:
            return False
        if isinstance(node, ast.Continue):
            return (
                nearest_enclosing_loop(node) is day_loop
                and parent.body[-1] is node
                and ast.dump(parent.test, include_attributes=False)
                == weekend_test_dump
            )
        return (
            isinstance(node, ast.Raise)
            and parent.body == [node]
            and node.cause is None
            and node.exc is not None
            and ast.dump(parent.test, include_attributes=False)
            == conflict_test_dump
            and ast.dump(node.exc, include_attributes=False)
            == conflict_raise_dump
        )

    def literal_truth_value(node: ast.AST) -> bool | None:
        try:
            return bool(ast.literal_eval(node))
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return None

    def finite_literal_iterable_state(
            node: ast.AST,
            seen: frozenset[int] = frozenset(),
    ) -> tuple[bool, bool]:
        marker = id(node)
        if marker in seen:
            return False, False
        seen = seen | {marker}
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, (str, bytes, tuple, frozenset)):
                return True, not value
            return True, False
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            definitely_empty = True
            for item in node.elts:
                if not isinstance(item, ast.Starred):
                    if isinstance(item, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
                        finite, _ = finite_literal_iterable_state(item, seen)
                        if not finite:
                            return False, False
                    definitely_empty = False
                    continue
                finite, empty = finite_literal_iterable_state(item.value, seen)
                if not finite:
                    return False, False
                definitely_empty &= empty
            return True, definitely_empty
        if isinstance(node, ast.Dict):
            definitely_empty = True
            for key, value in zip(node.keys, node.values):
                if key is not None:
                    for evaluated in (key, value):
                        if isinstance(
                            evaluated,
                            (ast.List, ast.Tuple, ast.Set, ast.Dict),
                        ):
                            finite, _ = finite_literal_iterable_state(
                                evaluated,
                                seen,
                            )
                            if not finite:
                                return False, False
                    definitely_empty = False
                    continue
                if not isinstance(value, ast.Dict):
                    return False, False
                finite, empty = finite_literal_iterable_state(value, seen)
                if not finite:
                    return False, False
                definitely_empty &= empty
            return True, definitely_empty
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "days"
            and not enclosing_comprehension_binds_name(node, "days")
            and execute_days_parameter is not None
            and execute_binding_events.get("days", ())
            == (execute_days_parameter,)
        ):
            return True, False
        if known_bounded_iterator_wrapper(node):
            return True, False
        return False, False

    def is_plain_finite_literal_iterable(node: ast.AST) -> bool:
        return finite_literal_iterable_state(node)[0]

    def is_bounded_comprehension_iterable(node: ast.AST) -> bool:
        return (
            is_plain_finite_literal_iterable(node)
            or known_bounded_iterator_wrapper(node)
            or (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id == "days"
                and not enclosing_comprehension_binds_name(node, "days")
                and execute_days_parameter is not None
                and execute_binding_events.get("days", ())
                == (execute_days_parameter,)
            )
        )

    def target_binds_name(target: ast.AST, name: str) -> bool:
        if isinstance(target, ast.Name):
            return target.id == name
        if isinstance(target, (ast.List, ast.Tuple)):
            return any(target_binds_name(item, name) for item in target.elts)
        if isinstance(target, ast.Starred):
            return target_binds_name(target.value, name)
        return False

    def enclosing_comprehension_binds_name(
            reference: ast.AST,
            name: str,
    ) -> bool:
        parent = execute_parents.get(reference)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, (
                ast.DictComp,
                ast.GeneratorExp,
                ast.ListComp,
                ast.SetComp,
            )):
                active_targets = []
                for generator in parent.generators:
                    if (
                        reference is generator.iter
                        or is_descendant_of(reference, generator.iter)
                    ):
                        break
                    active_targets.append(generator.target)
                    if any(
                        reference is condition
                        or is_descendant_of(reference, condition)
                        for condition in generator.ifs
                    ):
                        break
                if any(
                    target_binds_name(target, name)
                    for target in active_targets
                ):
                    return True
            parent = execute_parents.get(parent)
        return False

    def enclosing_class_definitely_binds_name(
            reference: ast.AST,
            name: str,
    ) -> bool:
        child = reference
        parent = execute_parents.get(child)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                return False
            if isinstance(parent, ast.ClassDef):
                direct_child = child
                while execute_parents.get(direct_child) is not parent:
                    next_child = execute_parents.get(direct_child)
                    if next_child is None:
                        return False
                    direct_child = next_child
                if direct_child not in parent.body:
                    return False
                for statement in reversed(
                    parent.body[:parent.body.index(direct_child)]
                ):
                    if isinstance(statement, ast.Delete) and any(
                        target_binds_name(target, name)
                        for target in statement.targets
                    ):
                        return False
                    if isinstance(statement, ast.Assign) and any(
                        target_binds_name(target, name)
                        for target in statement.targets
                    ):
                        return True
                    if isinstance(statement, ast.AnnAssign) and target_binds_name(
                        statement.target,
                        name,
                    ):
                        return statement.value is not None
                    if isinstance(statement, (
                        ast.AsyncFunctionDef,
                        ast.ClassDef,
                        ast.FunctionDef,
                    )) and statement.name == name:
                        return True
                    if isinstance(statement, (ast.Import, ast.ImportFrom)) and any(
                        (
                            alias.asname
                            or (
                                alias.name
                                if isinstance(statement, ast.ImportFrom)
                                else alias.name.split(".", 1)[0]
                            )
                        ) == name
                        for alias in statement.names
                    ):
                        return True
                return False
            child = parent
            parent = execute_parents.get(child)
        return False

    def known_bounded_iterator_wrapper(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "iter"
            and len(node.args) == 1
            and not node.keywords
            and not module_binding_events.get("iter", ())
            and not execute_binding_events.get("iter", ())
            and not enclosing_comprehension_binds_name(node, "iter")
            and not enclosing_class_definitely_binds_name(node, "iter")
            and is_bounded_comprehension_iterable(node.args[0])
        )

    eager_consumer_names = protected_eager_builtins - {"iter"}

    def is_unshadowed_eager_consumer(call: ast.Call) -> bool:
        return (
            isinstance(call.func, ast.Name)
            and call.func.id in eager_consumer_names
            and not module_binding_events.get(call.func.id, ())
            and not execute_binding_events.get(call.func.id, ())
            and not enclosing_comprehension_binds_name(call, call.func.id)
            and not enclosing_class_definitely_binds_name(call, call.func.id)
        )

    static_eager_call_error = object()
    static_eager_bounded_unknown = object()

    def expand_static_eager_positional(
            expression: ast.AST,
            seen: frozenset[int] = frozenset(),
    ) -> tuple[ast.AST, ...] | object | None:
        if id(expression) in seen:
            return None
        seen = seen | {id(expression)}
        if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
            expanded = []
            for item in expression.elts:
                if not isinstance(item, ast.Starred):
                    expanded.append(item)
                    continue
                nested = expand_static_eager_positional(item.value, seen)
                if nested in {
                    None,
                    static_eager_call_error,
                    static_eager_bounded_unknown,
                }:
                    return nested
                expanded.extend(nested)
            return tuple(expanded)
        if isinstance(expression, ast.Dict):
            keys = []
            for key, value in zip(expression.keys, expression.values):
                if key is not None:
                    keys.append(key)
                    continue
                nested = expand_static_eager_mapping(value, seen)
                if nested is None or nested is static_eager_call_error:
                    return nested
                keys.extend(
                    ast.Constant(value=keyword_name)
                    for keyword_name, _ in nested
                )
            return tuple(keys)
        if isinstance(expression, ast.Constant):
            value = expression.value
            if isinstance(value, (str, bytes)):
                return tuple(ast.Constant(value=item) for item in value)
            return static_eager_call_error
        if is_bounded_comprehension_iterable(expression):
            return static_eager_bounded_unknown
        return None

    def expand_static_eager_mapping(
            expression: ast.AST,
            seen: frozenset[int] = frozenset(),
    ) -> tuple[tuple[str, ast.AST], ...] | object | None:
        if id(expression) in seen or not isinstance(expression, ast.Dict):
            return None
        seen = seen | {id(expression)}
        expanded: dict[str, ast.AST] = {}
        for key, value in zip(expression.keys, expression.values):
            if key is None:
                nested = expand_static_eager_mapping(value, seen)
                if nested is None or nested is static_eager_call_error:
                    return nested
                expanded.update(nested)
                continue
            try:
                keyword_name = ast.literal_eval(key)
            except (
                ValueError,
                TypeError,
                SyntaxError,
                MemoryError,
                RecursionError,
            ):
                return None
            if not isinstance(keyword_name, str):
                return static_eager_call_error
            expanded[keyword_name] = value
        return tuple(expanded.items())

    def normalized_eager_consumer_arguments(
            call: ast.Call,
    ) -> (
        tuple[tuple[ast.AST, ...], tuple[tuple[str, ast.AST], ...]]
        | object
        | None
    ):
        if not is_unshadowed_eager_consumer(call):
            return None

        normalized_args = []
        for argument in call.args:
            if not isinstance(argument, ast.Starred):
                normalized_args.append(argument)
                continue
            expanded = expand_static_eager_positional(argument.value)
            if expanded in {
                None,
                static_eager_call_error,
                static_eager_bounded_unknown,
            }:
                return expanded
            normalized_args.extend(expanded)
        normalized_keywords = []
        for keyword in call.keywords:
            if keyword.arg is not None:
                normalized_keywords.append((keyword.arg, keyword.value))
                continue
            expanded = expand_static_eager_mapping(keyword.value)
            if expanded is None or expanded is static_eager_call_error:
                return expanded
            normalized_keywords.extend(expanded)
        keyword_names = [name for name, _ in normalized_keywords]
        if len(set(keyword_names)) != len(keyword_names):
            return static_eager_call_error
        return tuple(normalized_args), tuple(normalized_keywords)

    def known_eager_generator_arguments(call: ast.Call) -> tuple[ast.AST, ...]:
        normalized = normalized_eager_consumer_arguments(call)
        if (
            normalized is None
            or normalized is static_eager_call_error
            or normalized is static_eager_bounded_unknown
            or not isinstance(call.func, ast.Name)
        ):
            return ()
        arguments, keywords = normalized
        name = call.func.id
        keyword_names = {keyword_name for keyword_name, _ in keywords}
        if name in {"all", "any", "frozenset", "list", "set", "tuple"}:
            return (
                arguments
                if len(arguments) == 1 and not keywords
                else ()
            )
        if name == "sorted":
            return (
                arguments
                if len(arguments) == 1
                and keyword_names.issubset({"key", "reverse"})
                else ()
            )
        if name == "sum":
            return (
                arguments[:1]
                if len(arguments) in {1, 2}
                and keyword_names.issubset({"start"})
                and not (len(arguments) == 2 and "start" in keyword_names)
                else ()
            )
        if name in {"max", "min"}:
            return (
                arguments
                if len(arguments) == 1
                and keyword_names.issubset({"default", "key"})
                else ()
            )
        if name == "dict":
            return arguments if len(arguments) == 1 else ()
        return ()

    def eager_consumer_has_unsafe_expansion(call: ast.Call) -> bool:
        return (
            is_unshadowed_eager_consumer(call)
            and normalized_eager_consumer_arguments(call) is None
        )

    def known_expression_truth_value(node: ast.AST) -> bool | None:
        literal = literal_truth_value(node)
        if literal is not None:
            return literal
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = known_expression_truth_value(node.operand)
            return None if operand is None else not operand
        if isinstance(node, ast.BoolOp):
            values = [known_expression_truth_value(value) for value in node.values]
            if isinstance(node.op, ast.And):
                if False in values:
                    return False
                return True if all(value is True for value in values) else None
            if True in values:
                return True
            return False if all(value is False for value in values) else None
        if isinstance(node, ast.IfExp):
            test = known_expression_truth_value(node.test)
            if test is True:
                return known_expression_truth_value(node.body)
            if test is False:
                return known_expression_truth_value(node.orelse)
            body = known_expression_truth_value(node.body)
            orelse = known_expression_truth_value(node.orelse)
            return body if body is not None and body == orelse else None
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id not in {"all", "any"}
        ):
            return None
        arguments = known_eager_generator_arguments(node)
        if (
            len(arguments) != 1
            or not isinstance(arguments[0], ast.GeneratorExp)
            or not generator_expression_is_definitely_empty(arguments[0])
        ):
            return None
        return node.func.id == "all"

    def generator_expression_is_definitely_empty(node: ast.GeneratorExp) -> bool:
        for generator in node.generators:
            if finite_literal_iterable_state(generator.iter) == (True, True):
                return True
            if any(
                known_expression_truth_value(condition) is False
                for condition in generator.ifs
            ):
                return True
        return False

    def expression_has_unsafe_eager_unpack(node: ast.AST) -> bool:
        if isinstance(node, ast.Starred):
            expanded = expand_static_eager_positional(node.value)
            return (
                expanded is None
                or expression_has_unsafe_eager_unpack(node.value)
            )
        if isinstance(node, ast.keyword) and node.arg is None:
            return (
                not isinstance(node.value, ast.Dict)
                or not is_plain_finite_literal_iterable(node.value)
                or expression_has_unsafe_eager_unpack(node.value)
            )
        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            if not is_plain_finite_literal_iterable(node):
                return True
        if isinstance(node, ast.IfExp):
            if expression_has_unsafe_eager_unpack(node.test):
                return True
            truth = known_expression_truth_value(node.test)
            if truth is True:
                return expression_has_unsafe_eager_unpack(node.body)
            if truth is False:
                return expression_has_unsafe_eager_unpack(node.orelse)
            return (
                expression_has_unsafe_eager_unpack(node.body)
                or expression_has_unsafe_eager_unpack(node.orelse)
            )
        if isinstance(node, ast.BoolOp):
            for value in node.values:
                if expression_has_unsafe_eager_unpack(value):
                    return True
                truth = known_expression_truth_value(value)
                if (
                    isinstance(node.op, ast.And) and truth is False
                ) or (
                    isinstance(node.op, ast.Or) and truth is True
                ):
                    return False
            return False
        if (
            isinstance(node, ast.Call)
            and eager_non_generator_consumer_is_unsafe(node)
        ):
            return True
        if isinstance(node, ast.Call) and any(
            isinstance(argument, ast.GeneratorExp)
            and comprehension_is_unsafe_before_dispatch(
                argument,
                consume_generator=True,
            )
            for argument in known_eager_generator_arguments(node)
        ):
            return True
        if isinstance(node, ast.Lambda):
            return any(
                expression_has_unsafe_eager_unpack(default)
                for default in (
                    *node.args.defaults,
                    *(
                        default
                        for default in node.args.kw_defaults
                        if default is not None
                    ),
                )
            )
        if isinstance(node, (
            ast.DictComp,
            ast.GeneratorExp,
            ast.ListComp,
            ast.SetComp,
        )):
            return comprehension_is_unsafe_before_dispatch(node)
        return any(
            expression_has_unsafe_eager_unpack(child)
            for child in ast.iter_child_nodes(node)
        )

    def comprehension_is_unsafe_before_dispatch(
            node: ast.DictComp | ast.GeneratorExp | ast.ListComp | ast.SetComp,
            *,
            consume_generator: bool = False,
    ) -> bool:
        if isinstance(node, ast.GeneratorExp) and not consume_generator:
            first_iterable = node.generators[0].iter
            return (
                not is_bounded_comprehension_iterable(first_iterable)
                or expression_has_unsafe_eager_unpack(first_iterable)
            )
        for generator in node.generators:
            if not is_bounded_comprehension_iterable(generator.iter):
                return True
            if expression_has_unsafe_eager_unpack(generator.iter):
                return True
            if finite_literal_iterable_state(generator.iter) == (True, True):
                return False
            for condition in generator.ifs:
                if expression_has_unsafe_eager_unpack(condition):
                    return True
                if known_expression_truth_value(condition) is False:
                    return False
        body = (
            (node.key, node.value)
            if isinstance(node, ast.DictComp)
            else (node.elt,)
        )
        return any(expression_has_unsafe_eager_unpack(item) for item in body)

    def generator_expression_is_immediately_consumed(node: ast.AST) -> bool:
        if not isinstance(node, ast.GeneratorExp):
            return False
        parent = execute_parents.get(node)
        return (
            isinstance(parent, ast.Call)
            and node in known_eager_generator_arguments(parent)
        )

    def eager_non_generator_consumer_is_unsafe(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        evaluated_argument_is_unsafe = (
            is_unshadowed_eager_consumer(node)
            and any(
                expression_has_unsafe_eager_unpack(expression)
                for expression in (
                    *node.args,
                    *(keyword.value for keyword in node.keywords),
                )
            )
        )
        return evaluated_argument_is_unsafe or any(
            not isinstance(argument, ast.GeneratorExp)
            and (
                not is_bounded_comprehension_iterable(argument)
                or expression_has_unsafe_eager_unpack(argument)
            )
            for argument in known_eager_generator_arguments(node)
        ) or eager_consumer_has_unsafe_expansion(node)

    def has_enclosing_comprehension(node: ast.AST) -> bool:
        parent = execute_parents.get(node)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, (
                ast.DictComp,
                ast.GeneratorExp,
                ast.ListComp,
                ast.SetComp,
            )):
                return True
            parent = execute_parents.get(parent)
        return False

    def is_in_statically_dead_expression_branch(node: ast.AST) -> bool:
        child = node
        parent = execute_parents.get(child)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, ast.IfExp):
                truth = known_expression_truth_value(parent.test)
                if (
                    (child is parent.body and truth is False)
                    or (child is parent.orelse and truth is True)
                ):
                    return True
            elif isinstance(parent, ast.BoolOp) and child in parent.values:
                child_index = parent.values.index(child)
                for earlier in parent.values[:child_index]:
                    truth = known_expression_truth_value(earlier)
                    if (
                        isinstance(parent.op, ast.And) and truth is False
                    ) or (
                        isinstance(parent.op, ast.Or) and truth is True
                    ):
                        return True
            child = parent
            parent = execute_parents.get(child)
        return False

    def block_guarantees_loop_break(
            statements: list[ast.stmt],
            loop: ast.While,
    ) -> bool:
        for statement in statements:
            if isinstance(statement, ast.Break):
                return nearest_enclosing_loop(statement) is loop
            if isinstance(statement, (ast.Continue, ast.Raise, ast.Return)):
                return False
            if isinstance(statement, ast.If):
                truth = known_expression_truth_value(statement.test)
                if truth is True:
                    return block_guarantees_loop_break(statement.body, loop)
                if truth is False:
                    return block_guarantees_loop_break(statement.orelse, loop)
                if (
                    statement.body
                    and statement.orelse
                    and block_guarantees_loop_break(statement.body, loop)
                    and block_guarantees_loop_break(statement.orelse, loop)
                ):
                    return True
        return False

    def is_statically_dead_in_execute(node: ast.AST) -> bool:
        child = node
        parent = execute_parents.get(child)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, ast.If):
                truth = known_expression_truth_value(parent.test)
                if (
                    (child in parent.body and truth is False)
                    or (child in parent.orelse and truth is True)
                ):
                    return True
            elif (
                isinstance(parent, ast.While)
                and child in parent.body
                and known_expression_truth_value(parent.test) is False
            ):
                return True
            elif (
                isinstance(parent, ast.For)
                and child in parent.body
                and finite_literal_iterable_state(parent.iter) == (True, True)
            ):
                return True
            child = parent
            parent = execute_parents.get(child)
        return False

    def is_unsafe_protected_loop(node: ast.AST) -> bool:
        if is_statically_dead_in_execute(node):
            return False
        if isinstance(node, ast.While):
            if known_expression_truth_value(node.test) is False:
                return False
            return not block_guarantees_loop_break(node.body, node)
        if isinstance(node, ast.AsyncFor):
            return True
        return (
            isinstance(node, ast.For)
            and node is not day_loop
            and not is_plain_finite_literal_iterable(node.iter)
        )

    execute_dispatches = (
        tuple(
            node
            for node in ast.walk(day_loop)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and isinstance(node.func.ctx, ast.Load)
            and node.func.id == "run_json"
            and evaluated_in_execute(node)
        )
        if day_loop is not None
        else ()
    )
    first_execute_dispatch = min(
        execute_dispatches,
        key=lambda node: (node.lineno, node.col_offset),
        default=None,
    )
    final_execute_dispatch = max(
        execute_dispatches,
        key=lambda node: (node.lineno, node.col_offset),
        default=None,
    )
    if execute_function is not None and day_loop is not None:
        day_loop_start = (day_loop.lineno, day_loop.col_offset)
        dispatch_start = (
            (first_execute_dispatch.lineno, first_execute_dispatch.col_offset)
            if first_execute_dispatch is not None
            else None
        )
        prefix_nodes = tuple(
            node
            for node in ast.walk(execute_function)
            if node is not execute_function
            and evaluated_in_execute(node)
            and hasattr(node, "lineno")
            and (
                (node.lineno, getattr(node, "col_offset", 0)) < day_loop_start
                or (
                    dispatch_start is not None
                    and is_descendant_of(node, day_loop)
                    and (node.lineno, getattr(node, "col_offset", 0))
                    < dispatch_start
                )
            )
        )
        unexpected_prefix_terminators = tuple(
            node
            for node in prefix_nodes
            if (
                isinstance(node, (
                    ast.Assert,
                    ast.Break,
                    ast.Continue,
                    ast.Raise,
                    ast.Return,
                    ast.Yield,
                    ast.YieldFrom,
                ))
                or is_execute_exit_call(node)
            )
            and not (
                isinstance(node, (ast.Break, ast.Continue))
                and nearest_enclosing_loop(node) is not day_loop
            )
            and not is_canonical_pre_dispatch_terminator(node)
        )
        final_dispatch_start = (
            (
                final_execute_dispatch.lineno,
                final_execute_dispatch.col_offset,
            )
            if final_execute_dispatch is not None
            else dispatch_start
        )
        unsafe_protected_loops = tuple(
            node
            for node in ast.walk(execute_function)
            if isinstance(node, (ast.For, ast.AsyncFor, ast.While))
            and evaluated_in_execute(node)
            and final_dispatch_start is not None
            and (node.lineno, node.col_offset) < final_dispatch_start
            and is_unsafe_protected_loop(node)
        )
        unsafe_protected_comprehensions = tuple(
            node
            for node in ast.walk(execute_function)
            if isinstance(node, (
                ast.DictComp,
                ast.GeneratorExp,
                ast.ListComp,
                ast.SetComp,
            ))
            and evaluated_in_execute(node)
            and final_dispatch_start is not None
            and (node.lineno, node.col_offset) < final_dispatch_start
            and not is_statically_dead_in_execute(node)
            and not has_enclosing_comprehension(node)
            and not is_in_statically_dead_expression_branch(node)
            and comprehension_is_unsafe_before_dispatch(
                node,
                consume_generator=generator_expression_is_immediately_consumed(
                    node
                ),
            )
        )
        unsafe_eager_iterator_consumers = tuple(
            node
            for node in ast.walk(execute_function)
            if isinstance(node, ast.Call)
            and evaluated_in_execute(node)
            and final_dispatch_start is not None
            and (node.lineno, node.col_offset) < final_dispatch_start
            and not is_statically_dead_in_execute(node)
            and not is_in_statically_dead_expression_branch(node)
            and not has_enclosing_comprehension(node)
            and eager_non_generator_consumer_is_unsafe(node)
        )
        if (
            first_execute_dispatch is None
            or unexpected_prefix_terminators
            or unsafe_protected_loops
            or unsafe_protected_comprehensions
            or unsafe_eager_iterator_consumers
        ):
            record("execute-pre-dispatch-termination")

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


def h2c_score_receipt_suffix_violations(
        tree: ast.Module,
) -> tuple[str, ...]:
    expected_source = """
def frozen_receipt_tail():
    try:
        scoring = run_json(
            [py, "-m", "quant.historical_outcomes", "score", run_id],
            "H2C_SCORE",
        )
        stages["scoring_seconds"] = round(time.monotonic() - started, 6)
        if (
            len(scoring.get("metrics", ())) != 72
            or scoring.get("forecast_count") != expected_forecasts
            or scoring.get("dataset_digest") != dataset_digest
            or scoring.get("configuration_digest") != configuration_digest
        ):
            raise StageFailure(
                "H2C_SCORE",
                "SCORING_RECEIPT_MISMATCH",
                scoring,
            )
        state = "SKIPPED_VERIFIED" if known else "COMPLETED"
        item.update(
            state=state,
            outcome_count=scoring.get("outcome_count"),
            metrics_count=len(scoring.get("metrics", ())),
            outcome_writes=outcome.get("inserted"),
            scoring_hash_summary=scoring.get("content_hash_summary"),
            stage_timings=stages,
            elapsed_seconds=round(time.monotonic() - session_started, 6),
        )
        item["receipt_sha256"] = _digest(item)
        receipt["skipped" if known else "completed"].append(day.isoformat())
        receipt["sessions"].append(item)
    except Exception:
        pass
"""
    expected_tree = ast.parse(expected_source)
    expected_try = next(
        node for node in ast.walk(expected_tree)
        if isinstance(node, ast.Try)
    )
    expected_tail = tuple(
        ast.dump(statement, include_attributes=False)
        for statement in expected_try.body
    )

    execute_functions = tuple(
        statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef)
        and statement.name == "execute"
    )
    if len(execute_functions) != 1:
        return ("h2c-score-receipt-execute",)
    execute_function = execute_functions[0]
    day_loops = tuple(
        statement
        for statement in execute_function.body
        if isinstance(statement, ast.For)
        and isinstance(statement.target, ast.Name)
        and statement.target.id == "day"
        and isinstance(statement.iter, ast.Name)
        and statement.iter.id == "days"
    )
    if len(day_loops) != 1:
        return ("h2c-score-receipt-day-loop",)
    day_loop = day_loops[0]
    day_tries = tuple(
        statement for statement in day_loop.body
        if isinstance(statement, ast.Try)
    )
    if len(day_tries) != 1:
        return ("h2c-score-receipt-try",)
    day_try = day_tries[0]

    score_assignments = tuple(
        statement
        for statement in day_try.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "scoring"
        and isinstance(statement.value, ast.Call)
        and len(statement.value.args) == 2
        and isinstance(statement.value.args[1], ast.Constant)
        and statement.value.args[1].value == "H2C_SCORE"
    )
    if len(score_assignments) != 1:
        return ("h2c-score-receipt-dispatch",)
    score_index = day_try.body.index(score_assignments[0])
    observed_tail = tuple(
        ast.dump(statement, include_attributes=False)
        for statement in day_try.body[score_index:]
    )
    violations = []
    if observed_tail != expected_tail:
        violations.append("h2c-score-receipt-tail")
    if day_try.orelse or day_try.finalbody:
        violations.append("h2c-score-receipt-control-flow")

    binding_parents, resolve_builtin_origin = lexical_import_origins(
        tree,
        include_from_imports=True,
        fallback_origins={
            "bool": "builtins.bool",
            "len": "builtins.len",
        },
    )
    annotations_are_deferred = any(
        isinstance(statement, ast.ImportFrom)
        and statement.module == "__future__"
        and any(alias.name == "annotations" for alias in statement.names)
        for statement in tree.body
    )

    def enclosing_function(node: ast.AST) -> ast.AST | None:
        parent = binding_parents.get(node)
        while parent is not None and not isinstance(parent, (
            ast.AsyncFunctionDef,
            ast.FunctionDef,
            ast.Lambda,
        )):
            parent = binding_parents.get(parent)
        return parent

    def is_descendant(node: ast.AST, ancestor: ast.AST) -> bool:
        parent = binding_parents.get(node)
        while parent is not None:
            if parent is ancestor:
                return True
            parent = binding_parents.get(parent)
        return False

    def target_contains_name(target: ast.AST, name: str) -> bool:
        if isinstance(target, ast.Name):
            return target.id == name
        if isinstance(target, (ast.List, ast.Tuple)):
            return any(
                target_contains_name(item, name) for item in target.elts
            )
        if isinstance(target, ast.Starred):
            return target_contains_name(target.value, name)
        return False

    def is_comprehension_target_name(node: ast.Name) -> bool:
        parent = binding_parents.get(node)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, ast.comprehension):
                return node is parent.target or is_descendant(node, parent.target)
            parent = binding_parents.get(parent)
        return False

    def is_nested_class_namespace(node: ast.AST) -> bool:
        parent = binding_parents.get(node)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, ast.ClassDef):
                return True
            if isinstance(parent, (
                ast.AsyncFunctionDef,
                ast.FunctionDef,
                ast.Lambda,
            )):
                return False
            parent = binding_parents.get(parent)
        return False

    def is_module_scope_node(node: ast.AST) -> bool:
        parent = binding_parents.get(node)
        while parent is not None and parent is not tree:
            if isinstance(parent, (
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.DictComp,
                ast.FunctionDef,
                ast.GeneratorExp,
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
            )):
                return False
            parent = binding_parents.get(parent)
        return parent is tree

    def enclosing_comprehension_shadows(node: ast.AST, name: str) -> bool:
        parent = binding_parents.get(node)
        while parent is not None and parent is not execute_function:
            if isinstance(parent, (
                ast.DictComp,
                ast.GeneratorExp,
                ast.ListComp,
                ast.SetComp,
            )):
                active_targets = []
                for generator in parent.generators:
                    if node is generator.iter or is_descendant(node, generator.iter):
                        break
                    active_targets.append(generator.target)
                    if any(
                        node is condition or is_descendant(node, condition)
                        for condition in generator.ifs
                    ):
                        break
                if any(
                    target_contains_name(target, name)
                    for target in active_targets
                ):
                    return True
            parent = binding_parents.get(parent)
        return False

    def direct_binding_events(name: str) -> tuple[ast.AST, ...]:
        events = []

        def header_binding_events(expression: ast.AST):
            if isinstance(expression, ast.NamedExpr):
                if target_contains_name(expression.target, name):
                    events.append(expression.target)
                yield from header_binding_events(expression.value)
                return
            if isinstance(expression, ast.Lambda):
                for default in (
                    *expression.args.defaults,
                    *(
                        item for item in expression.args.kw_defaults
                        if item is not None
                    ),
                ):
                    yield from header_binding_events(default)
                return
            for child in ast.iter_child_nodes(expression):
                yield from header_binding_events(child)

        for node in ast.walk(execute_function):
            if is_nested_class_namespace(node):
                continue
            if (
                isinstance(node, ast.Name)
                and node.id == name
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and enclosing_function(node) is execute_function
                and not is_comprehension_target_name(node)
                and not is_nested_class_namespace(node)
            ):
                events.append(node)
            elif (
                isinstance(node, ast.arg)
                and node.arg == name
                and enclosing_function(node) is execute_function
            ):
                events.append(node)
            elif (
                node is not execute_function
                and isinstance(node, (
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.FunctionDef,
                ))
                and node.name == name
                and enclosing_function(node) is execute_function
            ):
                events.append(node)
            elif (
                isinstance(node, ast.ExceptHandler)
                and node.name == name
                and enclosing_function(node) is execute_function
            ):
                events.append(node)
            elif isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
                if (
                    enclosing_function(node) is execute_function
                    and not is_nested_class_namespace(node)
                ):
                    events.append(node)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == name:
                if enclosing_function(node) is execute_function:
                    events.append(node)
            elif isinstance(node, ast.MatchMapping) and node.rest == name:
                if enclosing_function(node) is execute_function:
                    events.append(node)
            elif isinstance(node, ast.Import) and enclosing_function(node) is execute_function:
                events.extend(
                    alias for alias in node.names
                    if (alias.asname or alias.name.split(".", 1)[0]) == name
                )
            elif isinstance(node, ast.ImportFrom) and enclosing_function(node) is execute_function:
                events.extend(
                    alias for alias in node.names
                    if (alias.asname or alias.name) == name
                )
            if (
                node is not execute_function
                and isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                and enclosing_function(node) is execute_function
            ):
                expressions = (
                    *node.decorator_list,
                    *node.args.defaults,
                    *(
                        item for item in node.args.kw_defaults
                        if item is not None
                    ),
                )
                if not annotations_are_deferred:
                    expressions += tuple(
                        argument.annotation
                        for argument in (
                            *node.args.posonlyargs,
                            *node.args.args,
                            *node.args.kwonlyargs,
                            node.args.vararg,
                            node.args.kwarg,
                        )
                        if argument is not None
                        and argument.annotation is not None
                    )
                    if node.returns is not None:
                        expressions += (node.returns,)
                for expression in expressions:
                    tuple(header_binding_events(expression))
            elif (
                isinstance(node, ast.Lambda)
                and enclosing_function(node) is execute_function
            ):
                for expression in (
                    *node.args.defaults,
                    *(
                        item for item in node.args.kw_defaults
                        if item is not None
                    ),
                ):
                    tuple(header_binding_events(expression))
            elif (
                node is not execute_function
                and isinstance(node, ast.ClassDef)
                and enclosing_function(node) is execute_function
            ):
                for expression in (
                    *node.decorator_list,
                    *node.bases,
                    *(keyword.value for keyword in node.keywords),
                ):
                    tuple(header_binding_events(expression))
        return tuple(events)

    def direct_name_loads(name: str) -> tuple[ast.Name, ...]:
        return tuple(
            node
            for node in ast.walk(execute_function)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == name
            and enclosing_function(node) is execute_function
            and not enclosing_comprehension_shadows(node, name)
            and not is_nested_class_namespace(node)
        )

    tail_len_loads = tuple(
        node
        for statement in day_try.body[score_index:]
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "len"
    )
    if (
        len(tail_len_loads) != 2
        or any(
            resolve_builtin_origin(node) != frozenset({"builtins.len"})
            for node in tail_len_loads
        )
        or any(
            not isinstance(event, ast.Global)
            for event in direct_binding_events("len")
        )
        or any(
            isinstance(node, ast.ImportFrom)
            and is_module_scope_node(node)
            and any(
                (alias.asname or alias.name) == "len"
                for alias in node.names
            )
            for node in ast.walk(tree)
        )
    ):
        violations.append("h2c-score-receipt-len-identity")

    expected_manifests_assignment = ast.parse(
        "manifests = existing(day)"
    ).body[0]
    expected_conflict_guard = ast.parse(
        """
if len(manifests) > 1:
    raise StageFailure("EXISTING", "CONFLICTING_SESSION_RUNS")
"""
    ).body[0]
    expected_known_assignment = ast.parse(
        "known = bool(manifests)"
    ).body[0]
    expected_manifest_assignment = ast.parse(
        "manifest = manifests[0] if known else None"
    ).body[0]
    canonical_manifests_assignment = (
        day_try.body[1] if len(day_try.body) > 1 else None
    )
    canonical_known_assignment = (
        day_try.body[3] if len(day_try.body) > 3 else None
    )
    canonical_conflict_guard = (
        day_try.body[2] if len(day_try.body) > 2 else None
    )
    canonical_manifest_assignment = (
        day_try.body[4] if len(day_try.body) > 4 else None
    )
    canonical_known_target = (
        canonical_known_assignment.targets[0]
        if isinstance(canonical_known_assignment, ast.Assign)
        and len(canonical_known_assignment.targets) == 1
        else None
    )
    canonical_manifests_target = (
        canonical_manifests_assignment.targets[0]
        if isinstance(canonical_manifests_assignment, ast.Assign)
        and len(canonical_manifests_assignment.targets) == 1
        else None
    )
    canonical_bool_load = (
        canonical_known_assignment.value.func
        if isinstance(canonical_known_assignment, ast.Assign)
        and isinstance(canonical_known_assignment.value, ast.Call)
        and isinstance(canonical_known_assignment.value.func, ast.Name)
        else None
    )
    expected_h1_test = ast.parse("if not known:\n    pass\n").body[0].test
    h1_dispatches = tuple(
        node
        for node in ast.walk(day_try)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "h1"
        and isinstance(node.value, ast.Call)
        and len(node.value.args) == 2
        and isinstance(node.value.args[1], ast.Constant)
        and node.value.args[1].value == "H1"
    )
    canonical_h1_guard = (
        binding_parents.get(h1_dispatches[0])
        if len(h1_dispatches) == 1
        else None
    )
    canonical_state_statement = (
        day_try.body[score_index + 3]
        if len(day_try.body) > score_index + 3
        else None
    )
    canonical_success_statement = (
        day_try.body[score_index + 6]
        if len(day_try.body) > score_index + 6
        else None
    )
    canonical_known_loads = {
        node
        for statement in (
            canonical_manifest_assignment,
            canonical_h1_guard.test
            if isinstance(canonical_h1_guard, ast.If)
            else None,
            canonical_state_statement,
            canonical_success_statement,
        )
        if statement is not None
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "known"
    }
    canonical_manifests_loads = {
        node
        for statement in (
            canonical_conflict_guard,
            canonical_known_assignment,
            canonical_manifest_assignment,
        )
        if statement is not None
        for node in ast.walk(statement)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "manifests"
    }

    def mutates_reflected_protected_binding(node: ast.AST) -> bool:
        if not (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "locals"
            and not node.value.args
            and not node.value.keywords
            and isinstance(node.slice, ast.Constant)
            and node.slice.value in {"known", "manifests"}
        ):
            return False
        parent = binding_parents.get(node)
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            return True
        return (
            isinstance(parent, ast.Attribute)
            and parent.value is node
            and isinstance(binding_parents.get(parent), ast.Call)
        )

    def function_directly_binds(
            function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
            name: str,
    ) -> bool:
        if any(
            isinstance(node, (ast.Global, ast.Nonlocal))
            and name in node.names
            and enclosing_function(node) is function
            and not is_nested_class_namespace(node)
            for node in ast.walk(function)
        ):
            return False
        arguments = function.args
        if name in {
            argument.arg
            for argument in (
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                arguments.vararg,
                arguments.kwarg,
            )
            if argument is not None
        }:
            return True

        def header_expression_binds(expression: ast.AST) -> bool:
            if isinstance(expression, ast.NamedExpr):
                return (
                    target_contains_name(expression.target, name)
                    or header_expression_binds(expression.value)
                )
            if isinstance(expression, ast.Lambda):
                return any(
                    header_expression_binds(default)
                    for default in (
                        *expression.args.defaults,
                        *(
                            item for item in expression.args.kw_defaults
                            if item is not None
                        ),
                    )
                )
            return any(
                header_expression_binds(child)
                for child in ast.iter_child_nodes(expression)
            )

        for node in ast.walk(function):
            if is_nested_class_namespace(node):
                continue
            expressions: tuple[ast.AST, ...] = ()
            if (
                node is not function
                and isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                and enclosing_function(node) is function
            ):
                expressions = (
                    *node.decorator_list,
                    *node.args.defaults,
                    *(
                        item for item in node.args.kw_defaults
                        if item is not None
                    ),
                )
                if not annotations_are_deferred:
                    expressions += tuple(
                        argument.annotation
                        for argument in (
                            *node.args.posonlyargs,
                            *node.args.args,
                            *node.args.kwonlyargs,
                            node.args.vararg,
                            node.args.kwarg,
                        )
                        if argument is not None
                        and argument.annotation is not None
                    )
                    if node.returns is not None:
                        expressions += (node.returns,)
            elif (
                isinstance(node, ast.Lambda)
                and enclosing_function(node) is function
            ):
                expressions = (
                    *node.args.defaults,
                    *(
                        item for item in node.args.kw_defaults
                        if item is not None
                    ),
                )
            elif (
                node is not function
                and isinstance(node, ast.ClassDef)
                and enclosing_function(node) is function
            ):
                expressions = (
                    *node.decorator_list,
                    *node.bases,
                    *(keyword.value for keyword in node.keywords),
                )
            if any(header_expression_binds(item) for item in expressions):
                return True
        return any(
            isinstance(node, ast.Name)
            and node.id == name
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and enclosing_function(node) is function
            and not is_comprehension_target_name(node)
            and not is_nested_class_namespace(node)
            for node in ast.walk(function)
        ) or any(
            node is not function
            and isinstance(node, (
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.FunctionDef,
            ))
            and node.name == name
            and enclosing_function(node) is function
            and not is_nested_class_namespace(node)
            for node in ast.walk(function)
        ) or any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and enclosing_function(node) is function
            and not is_nested_class_namespace(node)
            and any(
                (
                    alias.asname
                    or (
                        alias.name
                        if isinstance(node, ast.ImportFrom)
                        else alias.name.split(".", 1)[0]
                    )
                ) == name
                for alias in node.names
            )
            for node in ast.walk(function)
        ) or any(
            isinstance(node, ast.ExceptHandler)
            and node.name == name
            and enclosing_function(node) is function
            for node in ast.walk(function)
        ) or any(
            (
                isinstance(node, (ast.MatchAs, ast.MatchStar))
                and node.name == name
            ) or (
                isinstance(node, ast.MatchMapping)
                and node.rest == name
            )
            for node in ast.walk(function)
            if enclosing_function(node) is function
            and not is_nested_class_namespace(node)
        )

    def nonlocal_resolves_to_execute(node: ast.Nonlocal, name: str) -> bool:
        current = enclosing_function(node)
        if not is_nested_class_namespace(node):
            current = enclosing_function(current) if current is not None else None
        while isinstance(current, (
            ast.AsyncFunctionDef,
            ast.FunctionDef,
            ast.Lambda,
        )):
            if function_directly_binds(current, name):
                return current is execute_function
            current = enclosing_function(current)
        return True
    if (
        canonical_manifests_assignment is None
        or ast.dump(canonical_manifests_assignment, include_attributes=False)
        != ast.dump(expected_manifests_assignment, include_attributes=False)
        or canonical_known_assignment is None
        or ast.dump(canonical_known_assignment, include_attributes=False)
        != ast.dump(expected_known_assignment, include_attributes=False)
        or canonical_conflict_guard is None
        or ast.dump(canonical_conflict_guard, include_attributes=False)
        != ast.dump(expected_conflict_guard, include_attributes=False)
        or canonical_manifest_assignment is None
        or ast.dump(canonical_manifest_assignment, include_attributes=False)
        != ast.dump(expected_manifest_assignment, include_attributes=False)
        or canonical_bool_load is None
        or resolve_builtin_origin(canonical_bool_load)
        != frozenset({"builtins.bool"})
        or any(
            not isinstance(event, ast.Global)
            for event in direct_binding_events("bool")
        )
        or any(
            isinstance(node, ast.ImportFrom)
            and is_module_scope_node(node)
            and any(
                (alias.asname or alias.name) == "bool"
                for alias in node.names
            )
            for node in ast.walk(tree)
        )
        or direct_binding_events("known") != (canonical_known_target,)
        or direct_binding_events("manifests") != (canonical_manifests_target,)
        or set(direct_name_loads("known")) != canonical_known_loads
        or set(direct_name_loads("manifests")) != canonical_manifests_loads
        or not isinstance(canonical_h1_guard, ast.If)
        or canonical_h1_guard not in day_try.body
        or h1_dispatches[0] not in canonical_h1_guard.body
        or ast.dump(canonical_h1_guard.test, include_attributes=False)
        != ast.dump(expected_h1_test, include_attributes=False)
        or any(
            mutates_reflected_protected_binding(node)
            and enclosing_function(node) is execute_function
            for node in ast.walk(execute_function)
        )
        or any(
            isinstance(node, ast.Nonlocal)
            and any(
                name in {"known", "manifests"}
                and nonlocal_resolves_to_execute(node, name)
                for name in node.names
            )
            for node in ast.walk(execute_function)
        )
    ):
        violations.append("h2c-score-receipt-known-identity")

    expected_weekend_guard = ast.parse(
        """
if day.weekday() >= 5:
    item.update(state="REJECTED", reason="MARKET_CLOSED_WEEKEND")
    receipt["rejected"].append(day.isoformat())
    receipt["sessions"].append(item)
    continue
"""
    ).body[0]
    weekend_guards = tuple(
        statement
        for statement in day_try.body[:score_index]
        if isinstance(statement, ast.If)
        and ast.dump(statement, include_attributes=False)
        == ast.dump(expected_weekend_guard, include_attributes=False)
    )
    if (
        not day_try.body
        or weekend_guards != (day_try.body[0],)
    ):
        violations.append("h2c-score-receipt-weekend-path")

    expected_failure_handler = ast.parse(
        """
try:
    pass
except Exception as error:
    stage = error.stage if isinstance(error, StageFailure) else "ORCHESTRATOR"
    reason = error.reason if isinstance(error, StageFailure) else type(error).__name__
    item.update(
        state="FAILED",
        failed_stage=stage,
        reason=reason,
        stage_timings=stages,
        elapsed_seconds=round(time.monotonic() - session_started, 6),
    )
    receipt["failed"].append(day.isoformat())
    receipt["sessions"].append(item)
    if not continue_on_failure:
        break
"""
    ).body[0].handlers[0]
    if (
        len(day_try.handlers) != 1
        or ast.dump(day_try.handlers[0], include_attributes=False)
        != ast.dump(expected_failure_handler, include_attributes=False)
    ):
        violations.append("h2c-score-receipt-failure-path")

    def evaluated_day_try_nodes(node: ast.AST):
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                yield from evaluated_day_try_nodes(decorator)
            for default in (
                *node.args.defaults,
                *(item for item in node.args.kw_defaults if item is not None),
            ):
                yield from evaluated_day_try_nodes(default)
            return
        if isinstance(node, ast.Lambda):
            for default in (
                *node.args.defaults,
                *(item for item in node.args.kw_defaults if item is not None),
            ):
                yield from evaluated_day_try_nodes(default)
            return
        for child in ast.iter_child_nodes(node):
            yield from evaluated_day_try_nodes(child)

    evaluated_nodes = tuple(
        node
        for statement in day_try.body
        for node in evaluated_day_try_nodes(statement)
    )
    canonical_state_assignment = (
        day_try.body[score_index + 3]
        if len(day_try.body) > score_index + 3
        else None
    )
    canonical_state_target = (
        canonical_state_assignment.targets[0]
        if isinstance(canonical_state_assignment, ast.Assign)
        and len(canonical_state_assignment.targets) == 1
        and isinstance(canonical_state_assignment.targets[0], ast.Name)
        and canonical_state_assignment.targets[0].id == "state"
        else None
    )
    state_binding_nodes = tuple(
        node
        for node in evaluated_nodes
        if isinstance(node, ast.Name)
        and node.id == "state"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    )
    if (
        canonical_state_target is None
        or state_binding_nodes != (canonical_state_target,)
    ):
        violations.append("h2c-score-receipt-state-inventory")

    def receipt_append_key(call: ast.Call) -> str | None:
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "append"
            and isinstance(call.func.value, ast.Subscript)
            and isinstance(call.func.value.value, ast.Name)
            and call.func.value.value.id == "receipt"
        ):
            return None
        selector = call.func.value.slice
        if isinstance(selector, ast.Constant) and isinstance(selector.value, str):
            return selector.value
        if (
            isinstance(selector, ast.IfExp)
            and isinstance(selector.body, ast.Constant)
            and selector.body.value == "skipped"
            and isinstance(selector.orelse, ast.Constant)
            and selector.orelse.value == "completed"
        ):
            return "success"
        return None

    receipt_appends = {
        call: receipt_append_key(call)
        for call in evaluated_nodes
        if isinstance(call, ast.Call)
    }
    canonical_success_append = (
        day_try.body[score_index + 6].value
        if len(day_try.body) > score_index + 6
        and isinstance(day_try.body[score_index + 6], ast.Expr)
        and isinstance(day_try.body[score_index + 6].value, ast.Call)
        else None
    )
    success_appends = tuple(
        call
        for call, key in receipt_appends.items()
        if key in {"completed", "skipped", "success"}
    )
    if success_appends != (canonical_success_append,):
        violations.append("h2c-score-receipt-success-inventory")

    allowed_path_appends = set()
    if weekend_guards:
        allowed_path_appends.update(
            node
            for node in ast.walk(weekend_guards[0])
            if isinstance(node, ast.Call)
            and receipt_append_key(node) in {"rejected", "sessions"}
        )
    canonical_session_append = (
        day_try.body[score_index + 7].value
        if len(day_try.body) > score_index + 7
        and isinstance(day_try.body[score_index + 7], ast.Expr)
        and isinstance(day_try.body[score_index + 7].value, ast.Call)
        else None
    )
    if canonical_session_append is not None:
        allowed_path_appends.add(canonical_session_append)
    observed_path_appends = {
        call
        for call, key in receipt_appends.items()
        if key in {"rejected", "sessions"}
    }
    if observed_path_appends != allowed_path_appends:
        violations.append("h2c-score-receipt-path-inventory")

    pre_score_success_updates = tuple(
        node
        for statement in day_try.body[:score_index]
        for node in evaluated_day_try_nodes(statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "item"
        and any(
            keyword.arg == "state"
            and not (
                isinstance(keyword.value, ast.Constant)
                and keyword.value.value == "REJECTED"
            )
            for keyword in node.keywords
        )
    )
    if pre_score_success_updates:
        violations.append("h2c-score-receipt-pre-score-success")

    pre_score_nodes = tuple(
        node
        for statement in day_try.body[:score_index]
        for node in evaluated_day_try_nodes(statement)
    )
    weekend_nodes = (
        set(ast.walk(weekend_guards[0]))
        if weekend_guards
        else set()
    )
    receipt_aliases = {"receipt"}
    item_aliases = {"item"}
    aliases_changed = True
    while aliases_changed:
        aliases_changed = False
        for node in pre_score_nodes:
            if not (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Name)
            ):
                continue
            if node.value.id in receipt_aliases and node.targets[0].id not in receipt_aliases:
                receipt_aliases.add(node.targets[0].id)
                aliases_changed = True
            if node.value.id in item_aliases and node.targets[0].id not in item_aliases:
                item_aliases.add(node.targets[0].id)
                aliases_changed = True

    def constant_subscript_key(node: ast.Subscript) -> object:
        return (
            node.slice.value
            if isinstance(node.slice, ast.Constant)
            else None
        )

    protected_receipt_accesses = tuple(
        node
        for node in pre_score_nodes
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in receipt_aliases
        and constant_subscript_key(node) in {
            "completed",
            "rejected",
            "sessions",
            "skipped",
        }
        and node not in weekend_nodes
    )
    item_state_writes = tuple(
        node
        for node in pre_score_nodes
        if isinstance(node, ast.Subscript)
        and isinstance(node.ctx, (ast.Store, ast.Del))
        and isinstance(node.value, ast.Name)
        and node.value.id in item_aliases
        and constant_subscript_key(node) == "state"
    )
    positional_state_updates = tuple(
        node
        for node in pre_score_nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in item_aliases
        and node not in weekend_nodes
        and (
            bool(node.args)
            or any(keyword.arg == "state" for keyword in node.keywords)
        )
    )
    if (
        protected_receipt_accesses
        or item_state_writes
        or positional_state_updates
    ):
        violations.append("h2c-score-receipt-pre-score-success")
    scoring_stores = tuple(
        node
        for node in ast.walk(execute_function)
        if isinstance(node, ast.Name)
        and node.id == "scoring"
        and isinstance(node.ctx, (ast.Store, ast.Del))
    )
    if scoring_stores != (score_assignments[0].targets[0],):
        violations.append("h2c-score-receipt-binding")
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
            for type_parameter in getattr(node, "type_params", ()):
                bind(node, type_parameter.name)
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
            for type_parameter in getattr(node, "type_params", ()):
                bind(node, type_parameter.name)
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
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            bind(scope, node.name)
        if isinstance(node, ast.MatchMapping) and node.rest:
            bind(scope, node.rest)
        if isinstance(node, ast.ExceptHandler) and node.name:
            bind(scope, node.name)
        if isinstance(node, ast.Assign):
            alias_events.append((scope, node.targets, node.value))
        elif isinstance(node, ast.NamedExpr):
            binding_owner = scope
            while isinstance(binding_owner, (
                ast.DictComp,
                ast.GeneratorExp,
                ast.ListComp,
                ast.SetComp,
            )):
                binding_owner = scope_parents[binding_owner]
            alias_events.append((binding_owner, [node.target], node.value))
            node_scopes[node.target] = binding_owner
            for name in target_names(node.target):
                bind(binding_owner, name)
            visit(node.value, scope)
            return
        elif isinstance(node, ast.AnnAssign):
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
            "aiter": "builtins.aiter",
            "classmethod": "builtins.classmethod",
            "filter": "builtins.filter",
            "iter": "builtins.iter",
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
    tracked_yield_callables: set[ast.AST] = set()
    tracked_exception_handler_payloads: dict[
        ast.ExceptHandler,
        set[
            tuple[
                tuple[ast.AST, ...],
                ast.AST | None,
                tuple[ast.AST, ...],
            ]
        ],
    ] = {}
    tracked_exception_handler_constructors: dict[
        ast.ExceptHandler,
        set[tuple[ast.Call, ast.AST | None]],
    ] = {}
    tracked_protocol_vararg_slots: dict[
        ast.AST,
        dict[str, set[tuple[int, int]]],
    ] = {}
    safely_overwritten_loop_targets: dict[ast.AST, set[str]] = {}

    def protocol_vararg_slots_for_expression(
            expression: ast.AST,
            scope: ast.AST | None,
    ) -> set[tuple[int, int]]:
        if isinstance(expression, ast.NamedExpr):
            return protocol_vararg_slots_for_expression(
                expression.value,
                scope,
            )
        if not isinstance(expression, ast.Name):
            return set()
        return set(
            tracked_protocol_vararg_slots.get(scope, {}).get(
                expression.id,
                (),
            )
        )

    def target_names(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name):
            return {node.id}
        if isinstance(node, (ast.List, ast.Tuple)):
            return set().union(*(target_names(item) for item in node.elts))
        if isinstance(node, ast.Starred):
            return target_names(node.value)
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
            if (
                not resolved_bases
                and "builtins.type" in import_origin_names(base_expression)
            ):
                continue
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

    def effective_local_metaclasses(
            class_node: ast.ClassDef,
            visited: frozenset[ast.ClassDef] = frozenset(),
    ) -> set[ast.ClassDef]:
        if class_node in visited:
            return set()
        explicit = set().union(*(
            resolve_class_expression(
                keyword.value,
                enclosing_callable(class_node),
            )
            for keyword in class_node.keywords
            if keyword.arg == "metaclass"
        )) if class_node.keywords else set()
        if explicit:
            return explicit
        visited = visited | {class_node}
        return set().union(*(
            effective_local_metaclasses(base, visited)
            for base in class_bases[class_node]
        )) if class_bases[class_node] else set()

    def local_constructor_targets(
            call: ast.Call,
    ) -> tuple[tuple[
        ast.FunctionDef | ast.AsyncFunctionDef,
        bool,
    ], ...]:
        targets = set()
        scope = enclosing_callable(call)
        for class_node in resolve_class_expression(call.func, scope):
            metaclasses = effective_local_metaclasses(class_node)
            metacall_targets = set()
            for metaclass in metaclasses:
                for metacall in resolve_class_methods(metaclass, "__call__"):
                    metacall_targets.add((
                        metacall,
                        0
                        if method_descriptor_kind(metacall) == "static"
                        else 1,
                    ))
            if metacall_targets:
                targets.update(metacall_targets)
                continue
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
        def is_tracked_handler_name(item: ast.Name) -> bool:
            child: ast.AST = item
            parent = parents.get(child)
            while parent is not None and parent is not scope:
                if isinstance(parent, ast.ExceptHandler):
                    payloads = tracked_exception_handler_payloads.get(parent)
                    if not (
                        payloads
                        and parent.name == item.id
                        and child in parent.body
                    ):
                        return False
                    containing_statement = child
                    while (
                        parents.get(containing_statement) is not parent
                        and parents.get(containing_statement) is not None
                    ):
                        containing_statement = parents[containing_statement]
                    if containing_statement in parent.body:
                        for statement in reversed(
                            parent.body[:parent.body.index(containing_statement)]
                        ):
                            assigned_value = None
                            definitely_rebound = False
                            if isinstance(statement, ast.Assign):
                                definitely_rebound = any(
                                    item.id in target_names(target)
                                    for target in statement.targets
                                )
                                assigned_value = statement.value
                            elif isinstance(statement, ast.AnnAssign):
                                definitely_rebound = (
                                    item.id in target_names(statement.target)
                                )
                                assigned_value = statement.value
                            elif isinstance(statement, ast.Delete):
                                definitely_rebound = any(
                                    item.id in target_names(target)
                                    for target in statement.targets
                                )
                            if not definitely_rebound:
                                continue
                            if assigned_value is None or not any(
                                isinstance(reference, ast.Name)
                                and isinstance(reference.ctx, ast.Load)
                                and reference.id == item.id
                                for reference in ast.walk(assigned_value)
                            ):
                                return False
                            break

                    cursor: ast.AST = item
                    saw_args = False
                    selected_index: int | None = None
                    unknown_index = False
                    while cursor is not node:
                        cursor_parent = parents.get(cursor)
                        if cursor_parent is None:
                            break
                        if (
                            isinstance(cursor_parent, ast.Attribute)
                            and cursor_parent.value is cursor
                            and cursor_parent.attr == "args"
                        ):
                            saw_args = True
                        elif (
                            saw_args
                            and isinstance(cursor_parent, ast.Subscript)
                            and cursor_parent.value is cursor
                        ):
                            try:
                                index = ast.literal_eval(cursor_parent.slice)
                            except (
                                ValueError,
                                TypeError,
                                SyntaxError,
                                MemoryError,
                                RecursionError,
                            ):
                                unknown_index = True
                            else:
                                if isinstance(index, int) and not isinstance(index, bool):
                                    selected_index = index
                                else:
                                    unknown_index = True
                        cursor = cursor_parent

                    for arguments, payload_scope, keyword_values in payloads:
                        if keyword_values or unknown_index or not saw_args:
                            candidates = arguments + keyword_values
                        elif selected_index is None:
                            candidates = arguments
                        else:
                            normalized_index = (
                                selected_index
                                if selected_index >= 0
                                else len(arguments) + selected_index
                            )
                            candidates = (
                                (arguments[normalized_index],)
                                if 0 <= normalized_index < len(arguments)
                                else ()
                            )
                        if any(
                            contains_passed_tracked_binding(
                                candidate,
                                payload_scope,
                            )
                            for candidate in candidates
                        ):
                            return True
                    return False
                if isinstance(parent, (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.Lambda,
                )):
                    return False
                child = parent
                parent = parents.get(child)
            return False

        def is_safely_overwritten_in_loop(item: ast.Name) -> bool:
            child: ast.AST = item
            parent = parents.get(child)
            while parent is not None:
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    return False
                if isinstance(parent, (ast.For, ast.AsyncFor)):
                    if child in parent.body:
                        target_position = (
                            parent.target.lineno,
                            parent.target.col_offset,
                        )
                        item_position = (item.lineno, item.col_offset)
                        target_nodes = set(ast.walk(parent.target))
                        containing_statement: ast.AST = item
                        while (
                            parents.get(containing_statement) is not parent
                            and parents.get(containing_statement) is not None
                        ):
                            containing_statement = parents[containing_statement]
                        preceding_statements = (
                            parent.body[:parent.body.index(containing_statement)]
                            if containing_statement in parent.body
                            else ()
                        )
                        latest_direct_write: tuple[tuple[int, int], ast.AST | None] | None = None
                        for statement in preceding_statements:
                            write_value: ast.AST | None = None
                            writes_name = False
                            if isinstance(statement, ast.Assign):
                                writes_name = any(
                                    item.id in target_names(target)
                                    for target in statement.targets
                                )
                                write_value = statement.value
                            elif isinstance(statement, ast.AnnAssign):
                                writes_name = item.id in target_names(statement.target)
                                write_value = statement.value
                            elif isinstance(statement, ast.AugAssign):
                                writes_name = item.id in target_names(statement.target)
                            elif isinstance(statement, ast.Delete):
                                writes_name = any(
                                    item.id in target_names(target)
                                    for target in statement.targets
                                )
                            if writes_name:
                                latest_direct_write = (
                                    (statement.lineno, statement.col_offset),
                                    write_value,
                                )
                        if latest_direct_write is not None:
                            _, write_value = latest_direct_write
                            return (
                                write_value is not None
                                and not contains_assignment_tracked_binding(
                                    write_value,
                                    scope,
                                )
                            )
                        if item.id not in safely_overwritten_loop_targets.get(
                            parent,
                            set(),
                        ):
                            return False
                        intervening_write = any(
                            isinstance(candidate, ast.Name)
                            and candidate not in target_nodes
                            and candidate.id == item.id
                            and isinstance(candidate.ctx, (ast.Store, ast.Del))
                            and target_position
                            < (candidate.lineno, candidate.col_offset)
                            < item_position
                            and enclosing_callable(candidate) is scope
                            for candidate in ast.walk(parent)
                        )
                        return not intervening_write
                    return False
                child = parent
                parent = parents.get(child)
            return False

        def is_tracked_name(item: ast.Name) -> bool:
            if is_tracked_handler_name(item):
                return True
            if is_safely_overwritten_in_loop(item):
                return False
            item_scope = scope
            while item_scope is not None:
                if item.id in scope_global_names[item_scope]:
                    item_scope = None
                    break
                if item.id in scope_nonlocal_names[item_scope]:
                    item_scope = callable_parents[item_scope]
                    continue
                if item.id in scope_bound_names[item_scope]:
                    vararg_slots = tracked_protocol_vararg_slots.get(
                        item_scope,
                        {},
                    ).get(item.id)
                    if vararg_slots:
                        containing_statement: ast.AST = item
                        while (
                            parents.get(containing_statement) is not item_scope
                            and parents.get(containing_statement) is not None
                        ):
                            containing_statement = parents[containing_statement]
                        body = getattr(item_scope, "body", ())
                        if isinstance(body, list) and containing_statement in body:
                            for statement in reversed(
                                body[:body.index(containing_statement)]
                            ):
                                value = None
                                writes = False
                                if isinstance(statement, ast.Assign):
                                    writes = any(
                                        item.id in target_names(target)
                                        for target in statement.targets
                                    )
                                    if writes:
                                        value = next((
                                            assigned_value_for_name(
                                                target,
                                                statement.value,
                                                item.id,
                                            )
                                            for target in statement.targets
                                            if item.id in target_names(target)
                                        ), None)
                                elif isinstance(statement, ast.AnnAssign):
                                    writes = item.id in target_names(statement.target)
                                    if writes:
                                        value = assigned_value_for_name(
                                            statement.target,
                                            statement.value,
                                            item.id,
                                        )
                                elif isinstance(statement, ast.Delete):
                                    writes = any(
                                        item.id in target_names(target)
                                        for target in statement.targets
                                    )
                                if writes:
                                    if value is None:
                                        return False
                                    replacement_slots = (
                                        protocol_vararg_slots_for_expression(
                                            value,
                                            item_scope,
                                        )
                                    )
                                    if replacement_slots:
                                        vararg_slots = replacement_slots
                                    else:
                                        return contains_passed_tracked_binding(
                                            value,
                                            item_scope,
                                        )
                                    break
                        selected_index = None
                        cursor: ast.AST = item
                        cursor_parent = parents.get(cursor)
                        if (
                            isinstance(cursor_parent, ast.Subscript)
                            and cursor_parent.value is cursor
                        ):
                            try:
                                candidate_index = ast.literal_eval(
                                    cursor_parent.slice
                                )
                            except (
                                ValueError,
                                TypeError,
                                SyntaxError,
                                MemoryError,
                                RecursionError,
                            ):
                                candidate_index = None
                            if isinstance(candidate_index, int) and not isinstance(
                                candidate_index,
                                bool,
                            ):
                                selected_index = candidate_index
                        if selected_index is None:
                            return True
                        return any(
                            (
                                selected_index
                                if selected_index >= 0
                                else length + selected_index
                            ) == tracked_index
                            for tracked_index, length in vararg_slots
                        )
                    if item.id in scoped_tracked_bindings[item_scope]:
                        containing_statement: ast.AST = item
                        while (
                            parents.get(containing_statement) is not item_scope
                            and parents.get(containing_statement) is not None
                        ):
                            containing_statement = parents[containing_statement]
                        body = getattr(item_scope, "body", ())
                        if isinstance(body, list) and containing_statement in body:
                            for statement in reversed(
                                body[:body.index(containing_statement)]
                            ):
                                value = None
                                writes = False
                                if isinstance(statement, ast.Assign):
                                    writes = any(
                                        item.id in target_names(target)
                                        for target in statement.targets
                                    )
                                    value = statement.value
                                elif isinstance(statement, ast.AnnAssign):
                                    writes = item.id in target_names(statement.target)
                                    value = statement.value
                                elif isinstance(statement, ast.Delete):
                                    writes = any(
                                        item.id in target_names(target)
                                        for target in statement.targets
                                    )
                                if writes:
                                    return bool(
                                        value is not None
                                        and contains_passed_tracked_binding(
                                            value,
                                            item_scope,
                                        )
                                    )
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
        if (
            isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp))
            and len(node.generators) == 1
            and not node.generators[0].ifs
            and isinstance(node.generators[0].target, ast.Name)
        ):
            source_variants = resolve_literal_sequences(
                node.generators[0].iter,
                scope,
            )
            if (
                isinstance(node.elt, ast.Name)
                and node.elt.id == node.generators[0].target.id
            ):
                return source_variants
            if not any(
                isinstance(item, ast.Name)
                and isinstance(item.ctx, ast.Load)
                and item.id == node.generators[0].target.id
                for item in ast.walk(node.elt)
            ):
                return {
                    tuple(node.elt for _ in source)
                    for source in source_variants
                }
        if (
            isinstance(node, ast.Call)
            and "builtins.iter" in import_origin_names(node.func)
            and len(node.args) == 1
            and not node.keywords
        ):
            return resolve_literal_sequences(node.args[0], scope)
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

    def unresolved_higher_order_starred(
            call: ast.Call,
    ) -> tuple[ast.AST, ...]:
        scope = enclosing_callable(call)
        return tuple(
            argument.value
            for argument in call.args
            if isinstance(argument, ast.Starred)
            and not resolve_literal_sequences(argument.value, scope)
        )

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
        if "itertools.starmap" in origins:
            return "starmap"
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
    forced_iterable_findings: set[ast.AST] = set()

    def taint_higher_order_callback(
            callback_expressions: set[ast.AST],
            tracked_parameter_indexes: set[int],
            scope: ast.AST | None,
    ) -> tuple[bool, bool]:
        callback_targets = set().union(*(
            resolve_callable_expression(expression, scope)
            for expression in callback_expressions
        )) if callback_expressions else set()
        updated = False
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
                updated = True
        return updated, bool(callback_targets)

    def is_definitely_none_callback(node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and node.value is None

    def own_yield_nodes(
            local_callable: ast.AST,
    ) -> tuple[ast.Yield | ast.YieldFrom, ...]:
        return tuple(
            node
            for node in ast.walk(local_callable)
            if isinstance(node, (ast.Yield, ast.YieldFrom))
            and enclosing_callable(node) is local_callable
        )

    def assigned_value_for_name(
            target: ast.AST,
            value: ast.AST,
            name: str,
    ) -> ast.AST | None:
        if isinstance(target, ast.Name):
            return value if target.id == name else None
        if isinstance(target, ast.Starred):
            return assigned_value_for_name(target.value, value, name)
        if not isinstance(target, (ast.List, ast.Tuple)):
            return None
        if not isinstance(value, (ast.List, ast.Tuple)):
            return None
        starred_indexes = [
            index
            for index, item in enumerate(target.elts)
            if isinstance(item, ast.Starred)
        ]
        aligned = []
        if not starred_indexes:
            if len(target.elts) != len(value.elts):
                return None
            aligned = list(zip(target.elts, value.elts))
        elif len(starred_indexes) == 1:
            star_index = starred_indexes[0]
            suffix_length = len(target.elts) - star_index - 1
            if len(value.elts) < star_index + suffix_length:
                return None
            aligned.extend(
                (target.elts[index], value.elts[index])
                for index in range(star_index)
            )
            middle_end = len(value.elts) - suffix_length
            aligned.append((
                target.elts[star_index],
                ast.List(
                    elts=list(value.elts[star_index:middle_end]),
                    ctx=ast.Load(),
                ),
            ))
            aligned.extend(
                (
                    target.elts[star_index + 1 + index],
                    value.elts[middle_end + index],
                )
                for index in range(suffix_length)
            )
        else:
            return None
        for target_item, value_item in reversed(aligned):
            assigned = assigned_value_for_name(target_item, value_item, name)
            if assigned is not None:
                return assigned
        return None

    def latest_iterable_alias_value(
            node: ast.Name,
            scope: ast.AST | None,
    ) -> tuple[ast.AST, ast.AST | None] | None:
        lookup_scope = scope
        while True:
            if lookup_scope is not None and node.id in scope_global_names[lookup_scope]:
                lookup_scope = None
            elif (
                lookup_scope is not None
                and node.id in scope_nonlocal_names[lookup_scope]
            ):
                lookup_scope = callable_parents[lookup_scope]
                continue
            if node.id in scope_bound_names[lookup_scope]:
                break
            if lookup_scope is None:
                return None
            lookup_scope = callable_parents[lookup_scope]

        before = (node.lineno, node.col_offset)
        candidates = []
        for event_scope, targets, value in alias_assignments:
            if event_scope is not lookup_scope:
                continue
            assigned = next((
                result
                for target in targets
                for result in (assigned_value_for_name(target, value, node.id),)
                if result is not None
            ), None)
            if assigned is None or not hasattr(assigned, "lineno"):
                continue
            position = (assigned.lineno, assigned.col_offset)
            if position < before:
                candidates.append((position, assigned))
        if not candidates:
            return None
        _, assigned = max(candidates, key=lambda item: item[0])
        return assigned, lookup_scope

    def is_lexical_builtin_expression(
            expression: ast.AST,
            scope: ast.AST | None,
            builtin_name: str,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> bool:
        if not isinstance(expression, ast.Name):
            return False
        marker = (scope, expression.id)
        if marker in seen:
            return False
        latest_alias = latest_iterable_alias_value(expression, scope)
        if latest_alias is not None:
            assigned, assigned_scope = latest_alias
            return is_lexical_builtin_expression(
                assigned,
                assigned_scope,
                builtin_name,
                seen | {marker},
            )
        lookup_scope = scope
        while lookup_scope is not None:
            if expression.id in scope_global_names[lookup_scope]:
                lookup_scope = None
                break
            if expression.id in scope_nonlocal_names[lookup_scope]:
                lookup_scope = callable_parents[lookup_scope]
                continue
            if expression.id in scope_bound_names[lookup_scope]:
                return False
            lookup_scope = callable_parents[lookup_scope]
        return (
            expression.id == builtin_name
            and expression.id not in scope_bound_names[None]
        )

    def iterable_rows(
            iterable: ast.AST,
            scope: ast.AST | None,
            seen_aliases: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> tuple[tuple[tuple[ast.AST, ast.AST | None], ...], bool]:
        if isinstance(iterable, ast.Name):
            alias_key = (scope, iterable.id)
            if alias_key not in seen_aliases:
                latest_alias = latest_iterable_alias_value(iterable, scope)
                if latest_alias is not None:
                    assigned, assigned_scope = latest_alias
                    return iterable_rows(
                        assigned,
                        assigned_scope,
                        seen_aliases | {alias_key},
                    )
        if (
            isinstance(iterable, ast.Call)
            and len(iterable.args) == 1
            and not iterable.keywords
        ):
            wrapper_names = {
                "iter": "builtins.iter",
                "aiter": "builtins.aiter",
            }
            for wrapper_name, wrapper_origin in wrapper_names.items():
                if is_lexical_builtin_expression(
                    iterable.func,
                    scope,
                    wrapper_name,
                ):
                    return iterable_rows(
                        iterable.args[0],
                        scope,
                        seen_aliases,
                    )
                if wrapper_origin in import_origin_names(iterable.func):
                    return (), False
        if isinstance(iterable, ast.Set):
            return tuple((item, scope) for item in iterable.elts), False
        if (
            isinstance(iterable, (ast.GeneratorExp, ast.ListComp, ast.SetComp))
            and len(iterable.generators) == 1
            and not iterable.generators[0].ifs
            and isinstance(iterable.generators[0].target, ast.Name)
        ):
            generator = iterable.generators[0]
            source_rows, source_unknown = iterable_rows(
                generator.iter,
                scope,
                seen_aliases,
            )
            if (
                isinstance(iterable.elt, ast.Name)
                and iterable.elt.id == generator.target.id
            ):
                return source_rows, source_unknown
            target_is_loaded = any(
                isinstance(item, ast.Name)
                and isinstance(item.ctx, ast.Load)
                and item.id == generator.target.id
                for item in ast.walk(iterable.elt)
            )
            if not target_is_loaded:
                return (
                    tuple((iterable.elt, scope) for _ in source_rows),
                    False,
                )
        literal_variants = resolve_literal_sequences(iterable, scope)
        if literal_variants:
            return (
                tuple(
                    (row, scope)
                    for variant in literal_variants
                    for row in variant
                ),
                False,
            )
        if isinstance(iterable, ast.Dict):
            return tuple(
                (key, scope) for key in iterable.keys if key is not None
            ), False
        rows = []
        unknown_tracked_shape = False
        protocol_iterators = set().union(*(
            resolve_class_methods(class_node, method_name)
            for class_node in resolve_instance_expression(iterable, scope)
            for method_name in ("__iter__", "__aiter__")
        ))
        for local_callable in protocol_iterators:
            yields = own_yield_nodes(local_callable)
            if yields:
                for yielded in yields:
                    value = yielded.value
                    if value is None:
                        continue
                    if isinstance(yielded, ast.Yield):
                        rows.append((value, local_callable))
                        continue
                    variants = resolve_literal_sequences(value, local_callable)
                    if variants:
                        rows.extend(
                            (row, local_callable)
                            for variant in variants
                            for row in variant
                        )
                    elif contains_assignment_tracked_binding(
                        value,
                        local_callable,
                    ):
                        unknown_tracked_shape = True
                continue
            for returned in (
                node.value
                for node in ast.walk(local_callable)
                if isinstance(node, ast.Return)
                and node.value is not None
                and enclosing_callable(node) is local_callable
            ):
                variants = resolve_literal_sequences(returned, local_callable)
                if variants:
                    rows.extend(
                        (row, local_callable)
                        for variant in variants
                        for row in variant
                    )
                elif contains_assignment_tracked_binding(
                    returned,
                    local_callable,
                ):
                    unknown_tracked_shape = True
        if rows:
            return tuple(rows), unknown_tracked_shape
        if any(
            local_callable in tracked_return_callables
            or local_callable in tracked_yield_callables
            for local_callable in protocol_iterators
        ):
            return (), True
        if not isinstance(iterable, ast.Call):
            return (), False
        for local_callable, _ in local_call_targets(iterable):
            yields = own_yield_nodes(local_callable)
            if yields:
                for yielded in yields:
                    value = yielded.value
                    if value is None:
                        continue
                    if isinstance(yielded, ast.Yield):
                        rows.append((value, local_callable))
                        continue
                    variants = resolve_literal_sequences(value, local_callable)
                    if variants:
                        rows.extend(
                            (row, local_callable)
                            for variant in variants
                            for row in variant
                        )
                    elif contains_assignment_tracked_binding(
                        value,
                        local_callable,
                    ):
                        unknown_tracked_shape = True
                continue
            returned_values = tuple(
                node.value
                for node in ast.walk(local_callable)
                if isinstance(node, ast.Return)
                and node.value is not None
                and enclosing_callable(node) is local_callable
            )
            for value in returned_values:
                variants = resolve_literal_sequences(value, local_callable)
                if variants:
                    rows.extend(
                        (row, local_callable)
                        for variant in variants
                        for row in variant
                    )
                elif contains_assignment_tracked_binding(
                    value,
                    local_callable,
                ):
                    unknown_tracked_shape = True
        if not rows and any(
            local_callable in tracked_return_callables
            or local_callable in tracked_yield_callables
            for local_callable, _ in local_call_targets(iterable)
        ):
            unknown_tracked_shape = True
        return tuple(rows), unknown_tracked_shape

    def tracked_loop_targets(
            target: ast.AST,
            yielded_value: ast.AST,
            scope: ast.AST | None,
    ) -> tuple[set[str], bool]:
        if isinstance(target, ast.Starred):
            return tracked_loop_targets(target.value, yielded_value, scope)
        if isinstance(target, ast.Name):
            return (
                ({target.id}, False)
                if contains_assignment_tracked_binding(yielded_value, scope)
                else (set(), False)
            )
        if isinstance(target, (ast.Attribute, ast.Subscript)):
            return set(), contains_assignment_tracked_binding(
                yielded_value,
                scope,
            )
        if not isinstance(target, (ast.List, ast.Tuple)):
            return set(), False
        value_variants = resolve_literal_sequences(yielded_value, scope)
        if not value_variants:
            if contains_assignment_tracked_binding(yielded_value, scope):
                return target_names(target), any(
                    isinstance(part, (ast.Attribute, ast.Subscript))
                    for part in ast.walk(target)
                )
            return set(), False

        tracked_names = set()
        persistent = False
        starred_indexes = [
            index
            for index, item in enumerate(target.elts)
            if isinstance(item, ast.Starred)
        ]
        for values in value_variants:
            aligned: list[tuple[ast.AST, tuple[ast.AST, ...]]] = []
            if not starred_indexes:
                if len(values) != len(target.elts):
                    continue
                aligned = [
                    (item, (value,))
                    for item, value in zip(target.elts, values)
                ]
            elif len(starred_indexes) == 1:
                star_index = starred_indexes[0]
                suffix_length = len(target.elts) - star_index - 1
                if len(values) < star_index + suffix_length:
                    continue
                aligned.extend(
                    (target.elts[index], (values[index],))
                    for index in range(star_index)
                )
                middle_end = len(values) - suffix_length
                aligned.append((
                    target.elts[star_index],
                    tuple(values[star_index:middle_end]),
                ))
                aligned.extend(
                    (
                        target.elts[star_index + 1 + index],
                        (values[middle_end + index],),
                    )
                    for index in range(suffix_length)
                )
            for item, assigned_values in aligned:
                item_names = set()
                item_persistent = False
                for assigned_value in assigned_values:
                    names, escapes = tracked_loop_targets(
                        item,
                        assigned_value,
                        scope,
                    )
                    item_names.update(names)
                    item_persistent |= escapes
                tracked_names.update(item_names)
                persistent |= item_persistent
        return tracked_names, persistent

    def starmap_tracked_indexes(
            iterable: ast.AST,
            scope: ast.AST | None,
    ) -> tuple[set[int], bool]:
        rows, unknown_tracked_shape = iterable_rows(iterable, scope)
        tracked_indexes = set()
        for row, row_scope in rows:
            variants = resolve_literal_sequences(row, row_scope)
            if not variants:
                if contains_assignment_tracked_binding(row, row_scope):
                    unknown_tracked_shape = True
                continue
            for values in variants:
                tracked_indexes.update(
                    index
                    for index, value in enumerate(values)
                    if contains_assignment_tracked_binding(value, row_scope)
                )
        return tracked_indexes, unknown_tracked_shape

    def update_loop_provenance(loop: ast.For | ast.AsyncFor) -> bool:
        if is_in_unmodeled_class_namespace(loop):
            return False
        updated = False
        scope = enclosing_callable(loop)
        rows, unknown_tracked_shape = iterable_rows(loop.iter, scope)
        new_names = set()
        persistent_escape = False
        for row, row_scope in rows:
            names, escapes = tracked_loop_targets(
                loop.target,
                row,
                row_scope,
            )
            new_names.update(names)
            persistent_escape |= escapes
        if unknown_tracked_shape:
            new_names.update(target_names(loop.target))
            persistent_escape |= any(
                isinstance(target_part, (ast.Attribute, ast.Subscript))
                for target_part in ast.walk(loop.target)
            )
        safe_targets = safely_overwritten_loop_targets.setdefault(loop, set())
        previous_safe_targets = set(safe_targets)
        safe_targets.difference_update(new_names)
        if rows and not unknown_tracked_shape:
            safe_targets.update(target_names(loop.target) - new_names)
        if safe_targets != previous_safe_targets:
            updated = True
        for name in new_names:
            destination_scope = scope
            if (
                destination_scope is not None
                and name in scope_global_names[destination_scope]
            ):
                destination_scope = None
            elif (
                destination_scope is not None
                and name in scope_nonlocal_names[destination_scope]
            ):
                destination_scope = callable_parents[destination_scope]
                while (
                    destination_scope is not None
                    and name not in scope_bound_names[destination_scope]
                ):
                    destination_scope = callable_parents[destination_scope]
            destination_bindings = (
                tracked_bindings
                if destination_scope is None
                else scoped_tracked_bindings[destination_scope]
            )
            if name not in destination_bindings:
                destination_bindings.add(name)
                updated = True
        if persistent_escape:
            forced_iterable_findings.add(loop)
        return updated

    for initial_loop in (
        node for node in ast.walk(tree)
        if isinstance(node, (ast.For, ast.AsyncFor))
    ):
        update_loop_provenance(initial_loop)

    def exception_type_keys(
            expression: ast.AST,
            scope: ast.AST | None,
    ) -> set[tuple[str, object]]:
        keys: set[tuple[str, object]] = {
            ("origin", origin)
            for origin in import_origin_names(expression)
        }
        keys.update(
            ("class", class_node)
            for class_node in resolve_class_expression(expression, scope)
        )
        if not keys:
            keys.add(("syntax", ast.dump(expression, include_attributes=False)))
        return keys

    def is_unshadowed_builtin_exception(
            expression: ast.AST,
            scope: ast.AST | None,
    ) -> bool:
        if not (
            isinstance(expression, ast.Name)
            and expression.id in {"BaseException", "Exception"}
        ):
            return False
        lookup_scope = scope
        while True:
            if expression.id in scope_bound_names[lookup_scope]:
                return False
            if lookup_scope is None:
                return True
            lookup_scope = callable_parents[lookup_scope]

    def exception_handler_matches(
            raised_type: ast.AST,
            handler_type: ast.AST | None,
            scope: ast.AST | None,
    ) -> bool:
        if handler_type is None:
            return True
        if isinstance(handler_type, ast.Tuple):
            return any(
                exception_handler_matches(raised_type, item, scope)
                for item in handler_type.elts
            )
        if is_unshadowed_builtin_exception(handler_type, scope):
            return True
        raised_classes = resolve_class_expression(raised_type, scope)
        handler_classes = resolve_class_expression(handler_type, scope)

        def reaches_local_base(
                raised_class: ast.ClassDef,
                handler_class: ast.ClassDef,
                seen: frozenset[ast.ClassDef] = frozenset(),
        ) -> bool:
            if raised_class is handler_class:
                return True
            if raised_class in seen:
                return False
            return any(
                reaches_local_base(
                    base,
                    handler_class,
                    seen | {raised_class},
                )
                for base in class_bases[raised_class]
            )

        if any(
            handler_class in (local_c3_mro(raised_class) or ())
            or reaches_local_base(raised_class, handler_class)
            for raised_class in raised_classes
            for handler_class in handler_classes
        ):
            return True
        return bool(
            exception_type_keys(raised_type, scope)
            & exception_type_keys(handler_type, scope)
        )

    def raised_alias_assignment_dominates(
            value: ast.AST,
            reference: ast.AST,
    ) -> bool:
        owner: ast.AST = value
        while not isinstance(owner, ast.stmt) and parents.get(owner) is not None:
            owner = parents[owner]
        owner_parent = parents.get(owner)
        if owner_parent is None:
            return False
        for field_name in ("body", "orelse", "finalbody"):
            block = getattr(owner_parent, field_name, None)
            if not isinstance(block, list) or owner not in block:
                continue
            reference_child = reference
            while (
                parents.get(reference_child) is not owner_parent
                and parents.get(reference_child) is not None
            ):
                reference_child = parents[reference_child]
            return (
                reference_child in block
                and block.index(owner) < block.index(reference_child)
            )
        return False

    def resolve_raised_exception_constructors(
            expression: ast.AST,
            scope: ast.AST | None,
            before: tuple[int, int],
            seen: frozenset[str] = frozenset(),
    ) -> set[tuple[ast.Call, ast.AST | None]]:
        if isinstance(expression, ast.Call):
            return {(expression, scope)}
        if isinstance(expression, ast.NamedExpr):
            return resolve_raised_exception_constructors(
                expression.value,
                scope,
                before,
                seen,
            )
        if isinstance(expression, ast.IfExp):
            return set().union(*(
                resolve_raised_exception_constructors(
                    branch,
                    scope,
                    before,
                    seen,
                )
                for branch in (expression.body, expression.orelse)
            ))
        if not isinstance(expression, ast.Name) or expression.id in seen:
            return set()
        candidates = []
        for event_scope, targets, value in alias_assignments:
            if event_scope is not scope:
                continue
            if not any(expression.id in target_names(target) for target in targets):
                continue
            position = (value.lineno, value.col_offset)
            if position < before:
                candidates.append((
                    position,
                    value,
                    raised_alias_assignment_dominates(value, expression),
                ))
        if not candidates:
            return set()
        definite = tuple(event for event in candidates if event[2])
        latest_definite = (
            max(definite, key=lambda item: item[0])
            if definite
            else None
        )
        cutoff = latest_definite[0] if latest_definite else (-1, -1)
        possible_values = []
        if latest_definite is not None:
            possible_values.append(latest_definite)
        possible_values.extend(
            event
            for event in candidates
            if not event[2] and event[0] > cutoff
        )
        return set().union(*(
            resolve_raised_exception_constructors(
                value,
                scope,
                position,
                seen | {expression.id},
            )
            for position, value, _ in possible_values
        )) if possible_values else set()

    def matching_exception_handlers(
            raise_node: ast.Raise,
            raised_type: ast.AST,
    ) -> tuple[ast.ExceptHandler, ...]:
        scope = enclosing_callable(raise_node)
        child: ast.AST = raise_node
        parent = parents.get(child)
        while parent is not None and parent is not scope:
            if isinstance(parent, (ast.Try, ast.TryStar)) and child in parent.body:
                matches = tuple(
                    handler
                    for handler in parent.handlers
                    if exception_handler_matches(
                        raised_type,
                        handler.type,
                        scope,
                    )
                )
                if matches:
                    return matches[:1]
            child = parent
            parent = parents.get(child)
        return ()

    def active_reraise_constructors(
            raise_node: ast.Raise,
            scope: ast.AST | None,
    ) -> set[tuple[ast.Call, ast.AST | None]]:
        child: ast.AST = raise_node
        parent = parents.get(child)
        handler = None
        while parent is not None and parent is not scope:
            if isinstance(parent, ast.ExceptHandler) and child in parent.body:
                handler = parent
                break
            child = parent
            parent = parents.get(child)
        if handler is None:
            return set()
        if raise_node.exc is None:
            return set(tracked_exception_handler_constructors.get(handler, ()))
        if not handler.name:
            return set()

        def handler_name_is_live(reference: ast.AST) -> bool:
            containing_statement: ast.AST = reference
            while (
                parents.get(containing_statement) is not handler
                and parents.get(containing_statement) is not None
            ):
                containing_statement = parents[containing_statement]
            if containing_statement not in handler.body:
                return True
            for statement in reversed(
                handler.body[:handler.body.index(containing_statement)]
            ):
                value = None
                writes = False
                if isinstance(statement, ast.Assign):
                    writes = any(
                        handler.name in target_names(target)
                        for target in statement.targets
                    )
                    value = statement.value
                elif isinstance(statement, ast.AnnAssign):
                    writes = handler.name in target_names(statement.target)
                    value = statement.value
                elif isinstance(statement, ast.Delete):
                    writes = any(
                        handler.name in target_names(target)
                        for target in statement.targets
                    )
                if writes:
                    return bool(
                        value is not None
                        and any(
                            isinstance(item, ast.Name)
                            and isinstance(item.ctx, ast.Load)
                            and item.id == handler.name
                            for item in ast.walk(value)
                        )
                    )
            return True

        def may_resolve_to_handler(
                expression: ast.AST,
                before: tuple[int, int],
                seen: frozenset[str] = frozenset(),
        ) -> bool:
            if isinstance(expression, ast.NamedExpr):
                return may_resolve_to_handler(
                    expression.value,
                    before,
                    seen,
                )
            if isinstance(expression, ast.IfExp):
                return any(
                    may_resolve_to_handler(branch, before, seen)
                    for branch in (expression.body, expression.orelse)
                )
            if not isinstance(expression, ast.Name):
                return False
            if expression.id == handler.name:
                return handler_name_is_live(expression)
            if expression.id in seen:
                return False
            candidates = []
            for event_scope, targets, value in alias_assignments:
                if event_scope is not scope:
                    continue
                if not any(
                    expression.id in target_names(target)
                    for target in targets
                ):
                    continue
                position = (value.lineno, value.col_offset)
                if position < before:
                    candidates.append((
                        position,
                        value,
                        raised_alias_assignment_dominates(
                            value,
                            expression,
                        ),
                    ))
            definite = tuple(event for event in candidates if event[2])
            latest_definite = (
                max(definite, key=lambda item: item[0])
                if definite
                else None
            )
            cutoff = latest_definite[0] if latest_definite else (-1, -1)
            possible_values = []
            if latest_definite is not None:
                possible_values.append(latest_definite)
            possible_values.extend(
                event
                for event in candidates
                if not event[2] and event[0] > cutoff
            )
            return any(
                may_resolve_to_handler(
                    value,
                    position,
                    seen | {expression.id},
                )
                for position, value, _ in possible_values
            )

        if not may_resolve_to_handler(
            raise_node.exc,
            (raise_node.lineno, raise_node.col_offset),
        ):
            return set()
        return set(tracked_exception_handler_constructors.get(handler, ()))

    binary_protocol_methods = {
        ast.Add: ("__add__", "__radd__"),
        ast.Sub: ("__sub__", "__rsub__"),
        ast.Mult: ("__mul__", "__rmul__"),
        ast.MatMult: ("__matmul__", "__rmatmul__"),
        ast.Div: ("__truediv__", "__rtruediv__"),
        ast.FloorDiv: ("__floordiv__", "__rfloordiv__"),
        ast.Mod: ("__mod__", "__rmod__"),
        ast.Pow: ("__pow__", "__rpow__"),
        ast.LShift: ("__lshift__", "__rlshift__"),
        ast.RShift: ("__rshift__", "__rrshift__"),
        ast.BitOr: ("__or__", "__ror__"),
        ast.BitXor: ("__xor__", "__rxor__"),
        ast.BitAnd: ("__and__", "__rand__"),
    }
    inplace_protocol_methods = {
        ast.Add: "__iadd__",
        ast.Sub: "__isub__",
        ast.Mult: "__imul__",
        ast.MatMult: "__imatmul__",
        ast.Div: "__itruediv__",
        ast.FloorDiv: "__ifloordiv__",
        ast.Mod: "__imod__",
        ast.Pow: "__ipow__",
        ast.LShift: "__ilshift__",
        ast.RShift: "__irshift__",
        ast.BitOr: "__ior__",
        ast.BitXor: "__ixor__",
        ast.BitAnd: "__iand__",
    }
    comparison_protocol_methods = {
        ast.Lt: ("__lt__", "__gt__"),
        ast.LtE: ("__le__", "__ge__"),
        ast.Gt: ("__gt__", "__lt__"),
        ast.GtE: ("__ge__", "__le__"),
        ast.Eq: ("__eq__", "__eq__"),
        ast.NotEq: ("__ne__", "__ne__"),
    }

    def taint_local_protocol_method(
            receiver: ast.AST,
            method_name: str,
            arguments: tuple[ast.AST, ...],
            scope: ast.AST | None,
    ) -> bool:
        updated = False
        methods = set().union(*(
            resolve_class_methods(class_node, method_name)
            for class_node in resolve_instance_expression(receiver, scope)
        ))
        for method in methods:
            positional, _, vararg, _, _ = callable_parameter_bindings(method)
            receiver_offset = int(method_descriptor_kind(method) != "static")
            available = positional[receiver_offset:]
            newly_tracked = set()
            for index, argument in enumerate(arguments):
                if not contains_passed_tracked_binding(argument, scope):
                    continue
                if index < len(available):
                    newly_tracked.add(available[index].arg)
                elif vararg is not None:
                    newly_tracked.add(vararg.arg)
            local_bindings = scoped_tracked_bindings[method]
            if not newly_tracked.issubset(local_bindings):
                local_bindings.update(newly_tracked)
                updated = True
        return updated

    def context_manager_receiver_values(
            receiver: ast.AST,
            scope: ast.AST | None,
    ) -> tuple[set[ast.AST], bool]:
        if not isinstance(receiver, ast.Name):
            return {receiver}, True
        before = (receiver.lineno, receiver.col_offset)
        candidates = []
        for event_scope, targets, value in alias_assignments:
            if event_scope is not scope:
                continue
            if not any(
                receiver.id in target_names(target)
                for target in targets
            ):
                continue
            position = (value.lineno, value.col_offset)
            if position < before:
                candidates.append((
                    position,
                    value,
                    raised_alias_assignment_dominates(value, receiver),
                ))
        definite = tuple(event for event in candidates if event[2])
        latest_definite = (
            max(definite, key=lambda item: item[0])
            if definite
            else None
        )
        cutoff = latest_definite[0] if latest_definite else (-1, -1)
        possible_values = []
        if latest_definite is not None:
            possible_values.append(latest_definite)
        possible_values.extend(
            event
            for event in candidates
            if not event[2] and event[0] > cutoff
        )

        def is_unmodeled_binding(node: ast.AST) -> bool:
            position = (
                getattr(node, "lineno", -1),
                getattr(node, "col_offset", -1),
            )
            if not (cutoff < position < before):
                return False
            if enclosing_callable(node) is not scope:
                return False
            if is_in_unmodeled_class_namespace(node):
                return False
            if isinstance(node, ast.AugAssign):
                return receiver.id in target_names(node.target)
            if isinstance(node, ast.Delete):
                return any(
                    receiver.id in target_names(target)
                    for target in node.targets
                )
            if isinstance(node, (ast.For, ast.AsyncFor)):
                return receiver.id in target_names(node.target)
            if isinstance(node, (ast.With, ast.AsyncWith)):
                return any(
                    item.optional_vars is not None
                    and receiver.id in target_names(item.optional_vars)
                    for item in node.items
                )
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                return any(
                    (alias.asname or alias.name.split(".")[0]) == receiver.id
                    for alias in node.names
                )
            if isinstance(node, ast.ExceptHandler):
                return node.name == receiver.id
            if isinstance(node, (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            )):
                return node.name == receiver.id
            return False

        complete = bool(latest_definite) and not any(
            is_unmodeled_binding(node)
            for node in ast.walk(tree)
        )
        return {
            value for _, value, _ in possible_values
        }, complete

    def resolve_context_manager_methods(
            receiver: ast.AST,
            method_name: str,
            scope: ast.AST | None,
    ) -> set[ast.FunctionDef | ast.AsyncFunctionDef]:
        expressions, _ = context_manager_receiver_values(receiver, scope)
        return set().union(*(
            resolve_class_methods(class_node, method_name)
            for expression in expressions
            for class_node in resolve_instance_expression(expression, scope)
        )) if expressions else set()

    def taint_local_exit_method(
            receiver: ast.AST,
            method_name: str,
            constructor: ast.Call,
            scope: ast.AST | None,
    ) -> bool:
        updated = False
        for method in resolve_context_manager_methods(
            receiver,
            method_name,
            scope,
        ):
            positional, _, vararg, _, _ = callable_parameter_bindings(method)
            receiver_offset = int(method_descriptor_kind(method) != "static")
            available = positional[receiver_offset:]
            exception_index = 1
            if exception_index < len(available):
                name = available[exception_index].arg
                if name not in scoped_tracked_bindings[method]:
                    scoped_tracked_bindings[method].add(name)
                    updated = True
            elif vararg is not None:
                vararg_index = exception_index - len(available)
                vararg_length = max(0, 3 - len(available))
                slots = tracked_protocol_vararg_slots.setdefault(
                    method,
                    {},
                ).setdefault(vararg.arg, set())
                slot = (vararg_index, vararg_length)
                if slot not in slots:
                    slots.add(slot)
                    updated = True
        return updated

    def context_manager_definitely_suppresses(
            receiver: ast.AST,
            method_name: str,
            scope: ast.AST | None,
    ) -> bool:
        expressions, complete = context_manager_receiver_values(receiver, scope)
        if not complete or not expressions:
            return False

        def method_returns_literal_true(
                method: ast.FunctionDef | ast.AsyncFunctionDef,
        ) -> bool:
            statements = list(method.body)
            if (
                statements
                and isinstance(statements[0], ast.Expr)
                and isinstance(statements[0].value, ast.Constant)
                and isinstance(statements[0].value.value, str)
            ):
                statements = statements[1:]
            return bool(
                len(statements) == 1
                and isinstance(statements[0], ast.Return)
                and isinstance(statements[0].value, ast.Constant)
                and statements[0].value.value is True
            )

        def expression_definitely_suppresses(expression: ast.AST) -> bool:
            if isinstance(expression, ast.NamedExpr):
                return expression_definitely_suppresses(expression.value)
            if isinstance(expression, ast.IfExp):
                return all(
                    expression_definitely_suppresses(branch)
                    for branch in (expression.body, expression.orelse)
                )
            classes = resolve_instance_expression(expression, scope)
            if not classes:
                return False
            for class_node in classes:
                methods = resolve_class_methods(class_node, method_name)
                if not methods or not all(
                    method_returns_literal_true(method)
                    for method in methods
                ):
                    return False
            return True

        return all(
            expression_definitely_suppresses(expression)
            for expression in expressions
        )

    def update_context_exit_exception_provenance(
            raise_node: ast.Raise,
            constructor: ast.Call,
            scope: ast.AST | None,
    ) -> bool:
        """Pass a raised value to local context-manager exit callbacks."""
        updated = False
        child: ast.AST = raise_node
        parent = parents.get(child)
        safe = ast.Constant(value=None)
        while parent is not None and parent is not scope:
            if isinstance(parent, (ast.Try, ast.TryStar)) and child in parent.body:
                if any(
                    exception_handler_matches(
                        constructor.func,
                        handler.type,
                        scope,
                    )
                    for handler in parent.handlers
                ):
                    break
            if isinstance(parent, (ast.With, ast.AsyncWith)) and child in parent.body:
                method_name = (
                    "__aexit__" if isinstance(parent, ast.AsyncWith)
                    else "__exit__"
                )
                for item in reversed(parent.items):
                    if taint_local_exit_method(
                        item.context_expr,
                        method_name,
                        constructor,
                        scope,
                    ):
                        updated = True
                    if context_manager_definitely_suppresses(
                        item.context_expr,
                        method_name,
                        scope,
                    ):
                        return updated
            child = parent
            parent = parents.get(child)
        return updated

    def update_implicit_protocol_provenance(node: ast.AST) -> bool:
        scope = enclosing_callable(node)
        invocations: list[tuple[ast.AST, str, tuple[ast.AST, ...]]] = []
        if isinstance(node, ast.BinOp):
            methods = binary_protocol_methods.get(type(node.op))
            if methods is not None:
                invocations.extend((
                    (node.left, methods[0], (node.right,)),
                    (node.right, methods[1], (node.left,)),
                ))
        elif isinstance(node, ast.AugAssign):
            methods = binary_protocol_methods.get(type(node.op))
            inplace = inplace_protocol_methods.get(type(node.op))
            if inplace is not None:
                invocations.append((node.target, inplace, (node.value,)))
            if methods is not None:
                invocations.extend((
                    (node.target, methods[0], (node.value,)),
                    (node.value, methods[1], (node.target,)),
                ))
        elif isinstance(node, ast.Compare):
            left = node.left
            for operator, right in zip(node.ops, node.comparators):
                methods = comparison_protocol_methods.get(type(operator))
                if methods is not None:
                    invocations.extend((
                        (left, methods[0], (right,)),
                        (right, methods[1], (left,)),
                    ))
                elif isinstance(operator, (ast.In, ast.NotIn)):
                    invocations.append((right, "__contains__", (left,)))
                left = right
        elif isinstance(node, ast.Subscript):
            if isinstance(node.ctx, ast.Load):
                invocations.append((node.value, "__getitem__", (node.slice,)))
            elif isinstance(node.ctx, ast.Del):
                invocations.append((node.value, "__delitem__", (node.slice,)))
            elif isinstance(node.ctx, ast.Store):
                parent = parents.get(node)
                assigned_value = None
                if isinstance(parent, ast.Assign) and node in parent.targets:
                    assigned_value = parent.value
                elif isinstance(parent, ast.AnnAssign) and parent.target is node:
                    assigned_value = parent.value
                elif isinstance(parent, ast.AugAssign) and parent.target is node:
                    assigned_value = parent.value
                if assigned_value is not None:
                    invocations.append((
                        node.value,
                        "__setitem__",
                        (node.slice, assigned_value),
                    ))
        updated = False
        for receiver, method_name, arguments in invocations:
            if taint_local_protocol_method(
                receiver,
                method_name,
                arguments,
                scope,
            ):
                updated = True
        return updated

    def propagate_protocol_vararg_assignment(
            targets: list[ast.AST],
            value: ast.AST,
            scope: ast.AST | None,
    ) -> tuple[bool, bool]:
        """Preserve exact exit-argument tuple slots through local aliases."""
        source_slots = protocol_vararg_slots_for_expression(value, scope)
        if not source_slots:
            return False, False
        source_lengths = {length for _, length in source_slots}
        scope_slots = tracked_protocol_vararg_slots.setdefault(scope, {})
        scope_bindings = (
            tracked_bindings
            if scope is None
            else scoped_tracked_bindings[scope]
        )
        updated = False

        def bind_target(target: ast.AST) -> bool:
            nonlocal updated
            if isinstance(target, ast.Name):
                destination = scope_slots.setdefault(target.id, set())
                if not source_slots.issubset(destination):
                    destination.update(source_slots)
                    updated = True
                return True
            if not isinstance(target, (ast.List, ast.Tuple)):
                return False
            if len(source_lengths) != 1:
                return False
            source_length = next(iter(source_lengths))
            starred = [
                index
                for index, item in enumerate(target.elts)
                if isinstance(item, ast.Starred)
            ]
            if len(starred) > 1:
                return False
            if not starred and len(target.elts) != source_length:
                return False
            if starred and source_length < len(target.elts) - 1:
                return False
            star_index = starred[0] if starred else None
            suffix_length = (
                len(target.elts) - star_index - 1
                if star_index is not None
                else 0
            )
            for target_index, item in enumerate(target.elts):
                if isinstance(item, ast.Starred):
                    if not isinstance(item.value, ast.Name):
                        return False
                    end = source_length - suffix_length
                    projected = {
                        (tracked_index - target_index, end - target_index)
                        for tracked_index, length in source_slots
                        if length == source_length
                        and target_index <= tracked_index < end
                    }
                    if projected:
                        destination = scope_slots.setdefault(
                            item.value.id,
                            set(),
                        )
                        if not projected.issubset(destination):
                            destination.update(projected)
                            updated = True
                    continue
                source_index = target_index
                if star_index is not None and target_index > star_index:
                    source_index = source_length - (
                        len(target.elts) - target_index
                    )
                if not isinstance(item, ast.Name):
                    return False
                if any(
                    length == source_length and tracked_index == source_index
                    for tracked_index, length in source_slots
                ) and item.id not in scope_bindings:
                    scope_bindings.add(item.id)
                    updated = True
            return True

        handled = True
        for target in targets:
            handled &= bind_target(target)
        return handled, updated

    changed = True
    while changed:
        changed = False
        for raise_node in (
            node for node in ast.walk(tree)
            if isinstance(node, ast.Raise)
        ):
            scope = enclosing_callable(raise_node)
            resolved_constructors = active_reraise_constructors(
                raise_node,
                scope,
            )
            if raise_node.exc is not None:
                resolved_constructors.update(
                    resolve_raised_exception_constructors(
                        raise_node.exc,
                        scope,
                        (raise_node.lineno, raise_node.col_offset),
                    )
                )
            for constructor, payload_scope in resolved_constructors:
                positional_payload = tuple(constructor.args)
                keyword_values = tuple(
                    keyword.value for keyword in constructor.keywords
                )
                if not any(
                    contains_passed_tracked_binding(argument, payload_scope)
                    for argument in positional_payload + keyword_values
                ):
                    continue
                if update_context_exit_exception_provenance(
                    raise_node,
                    constructor,
                    scope,
                ):
                    changed = True
                for handler in matching_exception_handlers(
                    raise_node,
                    constructor.func,
                ):
                    constructors = tracked_exception_handler_constructors.setdefault(
                        handler,
                        set(),
                    )
                    constructor_payload = (constructor, payload_scope)
                    if constructor_payload not in constructors:
                        constructors.add(constructor_payload)
                        changed = True
                    if not handler.name:
                        continue
                    payloads = tracked_exception_handler_payloads.setdefault(
                        handler,
                        set(),
                    )
                    payload = (
                        positional_payload,
                        payload_scope,
                        keyword_values,
                    )
                    if payload not in payloads:
                        payloads.add(payload)
                        changed = True

        for protocol_node in ast.walk(tree):
            if update_implicit_protocol_provenance(protocol_node):
                changed = True

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
            scope = enclosing_callable(node)
            shape_handled, shape_updated = (
                propagate_protocol_vararg_assignment(
                    targets,
                    value,
                    scope,
                )
                if value is not None
                else (False, False)
            )
            if shape_updated:
                changed = True
            if shape_handled:
                continue
            if (
                value is None
                or not contains_assignment_tracked_binding(
                    value,
                    scope,
                )
            ):
                continue
            new_names = set().union(*(target_names(target) for target in targets))
            scope_bindings = (
                tracked_bindings
                if scope is None
                else scoped_tracked_bindings[scope]
            )
            if not new_names.issubset(scope_bindings):
                scope_bindings.update(new_names)
                changed = True

        for loop in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.For, ast.AsyncFor))
        ):
            if update_loop_provenance(loop):
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

        for context_node in (
            node for node in ast.walk(tree)
            if isinstance(node, (ast.With, ast.AsyncWith))
        ):
            scope = enclosing_callable(context_node)
            enter_name = (
                "__aenter__"
                if isinstance(context_node, ast.AsyncWith)
                else "__enter__"
            )
            for item in context_node.items:
                if item.optional_vars is None:
                    continue
                enter_methods = set().union(*(
                    resolve_class_methods(class_node, enter_name)
                    for class_node in resolve_instance_expression(
                        item.context_expr,
                        scope,
                    )
                ))
                if not any(
                    method in tracked_return_callables
                    for method in enter_methods
                ):
                    continue
                new_names = target_names(item.optional_vars)
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
            and higher_order_builtin_kind(node) is not None
        ):
            kind = higher_order_builtin_kind(call)
            scope = enclosing_callable(call)
            unresolved_starred = unresolved_higher_order_starred(call)
            if unresolved_starred:
                if kind == "sorted":
                    carrier_expressions = tuple(
                        argument.value
                        if isinstance(argument, ast.Starred)
                        else argument
                        for argument in call.args
                    )
                    has_tracked_carrier = any(
                        contains_direct_higher_order_input(carrier, scope)
                        for carrier in carrier_expressions
                    )
                    callback_variants = normalized_sorted_key_values(call)
                    callback_expressions = {
                        variant[0]
                        for variant in callback_variants
                        if len(variant) == 1
                    }
                    if has_tracked_carrier and callback_expressions:
                        updated, resolved = taint_higher_order_callback(
                            callback_expressions,
                            {0},
                            scope,
                        )
                        if updated:
                            changed = True
                        if (
                            not resolved
                            and not all(
                                is_definitely_none_callback(expression)
                                for expression in callback_expressions
                            )
                        ):
                            forced_higher_order_findings.add(call)
                    if (
                        has_tracked_carrier
                        and any(
                            keyword.arg is None
                            and not resolve_literal_mappings(
                                keyword.value,
                                scope,
                            )
                            for keyword in call.keywords
                        )
                    ):
                        forced_higher_order_findings.add(call)
                else:
                    definite_callback = (
                        call.args[0]
                        if call.args
                        and not isinstance(call.args[0], ast.Starred)
                        else None
                    )
                    carrier_expressions = tuple(
                        argument.value
                        if isinstance(argument, ast.Starred)
                        else argument
                        for argument in (
                            call.args[1:]
                            if definite_callback is not None
                            else call.args
                        )
                    )
                    has_tracked_carrier = any(
                        contains_direct_higher_order_input(carrier, scope)
                        for carrier in carrier_expressions
                    )
                    if has_tracked_carrier:
                        if definite_callback is None:
                            forced_higher_order_findings.add(call)
                        else:
                            tracked_indexes = (
                                {0} if kind == "filter" else set(range(64))
                            )
                            updated, resolved = taint_higher_order_callback(
                                {definite_callback},
                                tracked_indexes,
                                scope,
                            )
                            if updated:
                                changed = True
                            if not resolved:
                                forced_higher_order_findings.add(call)
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
            unresolved_starred = unresolved_higher_order_starred(call)
            if kind == "starmap":
                if unresolved_starred:
                    definite_callback = (
                        call.args[0]
                        if call.args
                        and not isinstance(call.args[0], ast.Starred)
                        else None
                    )
                    carrier_expressions = tuple(
                        argument.value
                        if isinstance(argument, ast.Starred)
                        else argument
                        for argument in (
                            call.args[1:]
                            if definite_callback is not None
                            else call.args
                        )
                    )
                    if any(
                        contains_direct_higher_order_input(carrier, scope)
                        for carrier in carrier_expressions
                    ):
                        if definite_callback is None:
                            forced_higher_order_findings.add(call)
                        else:
                            updated, resolved = taint_higher_order_callback(
                                {definite_callback},
                                set(range(64)),
                                scope,
                            )
                            if updated:
                                changed = True
                            if not resolved:
                                forced_higher_order_findings.add(call)
                for normalized_args in normalized_higher_order_args(call):
                    if len(normalized_args) != 2:
                        continue
                    tracked_indexes, unknown_shape = starmap_tracked_indexes(
                        normalized_args[1],
                        scope,
                    )
                    if unknown_shape:
                        tracked_indexes.update(range(64))
                    if not tracked_indexes:
                        continue
                    updated, resolved = taint_higher_order_callback(
                        {normalized_args[0]},
                        tracked_indexes,
                        scope,
                    )
                    if updated:
                        changed = True
                    if not resolved:
                        forced_higher_order_findings.add(call)
                continue
            if unresolved_starred:
                definite_callback = (
                    call.args[0]
                    if kind == "reduce"
                    and call.args
                    and not isinstance(call.args[0], ast.Starred)
                    else None
                )
                if kind == "list-sort":
                    carrier_expressions = (call.func.value,)
                elif kind == "reduce" and definite_callback is not None:
                    carrier_expressions = tuple(
                        argument.value
                        if isinstance(argument, ast.Starred)
                        else argument
                        for argument in call.args[1:]
                    )
                else:
                    carrier_expressions = tuple(
                        argument.value
                        if isinstance(argument, ast.Starred)
                        else argument
                        for argument in call.args
                    )
                has_unresolved_tracked_carrier = any(
                    contains_direct_higher_order_input(carrier, scope)
                    for carrier in carrier_expressions
                )
                if has_unresolved_tracked_carrier:
                    if kind == "reduce":
                        if definite_callback is None:
                            forced_higher_order_findings.add(call)
                        else:
                            updated, resolved = taint_higher_order_callback(
                                {definite_callback},
                                {0, 1},
                                scope,
                            )
                            if updated:
                                changed = True
                            if not resolved:
                                forced_higher_order_findings.add(call)
                    else:
                        callback_variants = normalized_sorted_key_values(call)
                        callback_expressions = {
                            variant[0]
                            for variant in callback_variants
                            if len(variant) == 1
                        }
                        if callback_expressions:
                            updated, resolved = taint_higher_order_callback(
                                callback_expressions,
                                {0},
                                scope,
                            )
                            if updated:
                                changed = True
                            if (
                                not resolved
                                and not all(
                                    is_definitely_none_callback(expression)
                                    for expression in callback_expressions
                                )
                            ):
                                forced_higher_order_findings.add(call)
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
            if (
                local_callable not in tracked_yield_callables
                and any(
                    yielded.value is not None
                    and contains_assignment_tracked_binding(
                        yielded.value,
                        local_callable,
                    )
                    for yielded in own_yield_nodes(local_callable)
                )
            ):
                tracked_yield_callables.add(local_callable)
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

    def statement_owner(node: ast.AST) -> ast.AST:
        owner = node
        while not isinstance(owner, ast.stmt) and parents.get(owner) is not None:
            owner = parents[owner]
        return owner

    def binding_scope_for_name(
            name: str,
            scope: ast.AST | None,
    ) -> ast.AST | None:
        while True:
            if scope is not None and name in scope_global_names[scope]:
                return None
            if scope is not None and name in scope_nonlocal_names[scope]:
                scope = callable_parents[scope]
                continue
            if name in scope_bound_names[scope]:
                return scope
            if scope is None:
                return None
            scope = callable_parents[scope]

    def latest_exclusive_alias_value(
            name: str,
            scope: ast.AST | None,
            reference: ast.AST,
    ) -> tuple[ast.AST, ast.AST | None] | None:
        lookup_scope = binding_scope_for_name(name, scope)
        reference_position = (reference.lineno, reference.col_offset)
        candidates = []
        for event_scope, targets, value in alias_assignments:
            if event_scope is not lookup_scope:
                continue
            assigned = next((
                result
                for target in targets
                for result in (assigned_value_for_name(target, value, name),)
                if result is not None
            ), None)
            if assigned is None:
                continue
            position = (assigned.lineno, assigned.col_offset)
            if (
                position < reference_position
                and raised_alias_assignment_dominates(assigned, reference)
            ):
                candidates.append((position, assigned, statement_owner(assigned)))
        if not candidates:
            return None
        _, assigned, chosen_owner = max(candidates, key=lambda item: item[0])
        cutoff = (chosen_owner.lineno, chosen_owner.col_offset)
        container = tree if lookup_scope is None else lookup_scope
        for target in ast.walk(container):
            if (
                not isinstance(target, ast.Name)
                or target.id != name
                or not isinstance(target.ctx, (ast.Store, ast.Del))
                or enclosing_callable(target) is not lookup_scope
                or is_in_unmodeled_class_namespace(target)
            ):
                continue
            owner = statement_owner(target)
            position = (owner.lineno, owner.col_offset)
            if (
                cutoff < position < reference_position
                and owner is not chosen_owner
            ):
                return None
        for candidate in ast.walk(container):
            if not hasattr(candidate, "lineno"):
                continue
            position = (candidate.lineno, candidate.col_offset)
            if not cutoff < position < reference_position:
                continue
            if (
                isinstance(candidate, ast.ExceptHandler)
                and candidate.name == name
                and enclosing_callable(candidate) is lookup_scope
            ) or (
                isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and candidate.name == name
                and enclosing_callable(candidate) is lookup_scope
            ) or (
                isinstance(candidate, (ast.Import, ast.ImportFrom))
                and enclosing_callable(candidate) is lookup_scope
                and any(
                    (
                        alias.asname
                        or (
                            alias.name
                            if isinstance(candidate, ast.ImportFrom)
                            else alias.name.split(".")[0]
                        )
                    ) == name
                    for alias in candidate.names
                )
            ):
                return None
        return assigned, lookup_scope

    def complete_local_class_expression(
            expression: ast.AST,
            scope: ast.AST | None,
            reference: ast.AST,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> tuple[set[ast.ClassDef], bool]:
        if isinstance(expression, ast.NamedExpr):
            return complete_local_class_expression(
                expression.value,
                scope,
                reference,
                seen,
            )
        if isinstance(expression, ast.IfExp):
            branches = tuple(
                complete_local_class_expression(
                    branch,
                    scope,
                    reference,
                    seen,
                )
                for branch in (expression.body, expression.orelse)
            )
            return (
                set().union(*(classes for classes, _ in branches)),
                all(complete and classes for classes, complete in branches),
            )
        if not isinstance(expression, ast.Name):
            return set(), False
        marker = (scope, expression.id)
        if marker in seen:
            return set(), False
        local_classes = resolve_scoped_classes(
            expression.id,
            scope,
            class_bindings,
        )
        declarations = {
            class_node
            for class_node in local_classes
            if class_node.name == expression.id
            and enclosing_callable(class_node) is scope
            and (class_node.lineno, class_node.col_offset)
            < (reference.lineno, reference.col_offset)
        }
        if declarations == local_classes and declarations:
            return declarations, True
        alias = latest_exclusive_alias_value(expression.id, scope, reference)
        if alias is None:
            return set(), False
        assigned, assigned_scope = alias
        return complete_local_class_expression(
            assigned,
            assigned_scope,
            assigned,
            seen | {marker},
        )

    def complete_local_instance_expression(
            expression: ast.AST,
            scope: ast.AST | None,
            reference: ast.AST,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> tuple[set[ast.ClassDef], bool]:
        if isinstance(expression, ast.Call):
            return complete_local_class_expression(
                expression.func,
                scope,
                reference,
                seen,
            )
        if isinstance(expression, ast.NamedExpr):
            return complete_local_instance_expression(
                expression.value,
                scope,
                reference,
                seen,
            )
        if isinstance(expression, ast.IfExp):
            branches = tuple(
                complete_local_instance_expression(
                    branch,
                    scope,
                    reference,
                    seen,
                )
                for branch in (expression.body, expression.orelse)
            )
            return (
                set().union(*(classes for classes, _ in branches)),
                all(complete and classes for classes, complete in branches),
            )
        if not isinstance(expression, ast.Name):
            return set(), False
        marker = (scope, expression.id)
        if marker in seen:
            return set(), False
        alias = latest_exclusive_alias_value(expression.id, scope, reference)
        if alias is None:
            return set(), False
        assigned, assigned_scope = alias
        return complete_local_instance_expression(
            assigned,
            assigned_scope,
            assigned,
            seen | {marker},
        )

    def exclusively_modeled_local_setitem(
            target: ast.Subscript,
            scope: ast.AST | None,
    ) -> bool:
        classes, complete = complete_local_instance_expression(
            target.value,
            scope,
            target,
        )
        if not complete or not classes:
            return False
        if classes != resolve_instance_expression(target.value, scope):
            return False
        for class_node in classes:
            methods = resolve_class_methods(class_node, "__setitem__")
            if not methods:
                return False
            if local_c3_mro(class_node) is None and not class_methods[
                class_node
            ].get("__setitem__"):
                return False
        return True

    def generic_persistent_assignment_escape(
            target: ast.AST,
            value: ast.AST,
            scope: ast.AST | None,
            *,
            direct: bool,
    ) -> bool:
        if isinstance(target, ast.Attribute):
            return carries_state_escape_value(value, scope)
        if isinstance(target, ast.Subscript):
            carries_argument = (
                carries_state_escape_value(value, scope)
                or carries_state_escape_value(target.slice, scope)
            )
            return carries_argument and not (
                direct and exclusively_modeled_local_setitem(target, scope)
            )
        if isinstance(target, ast.Starred):
            return generic_persistent_assignment_escape(
                target.value,
                value,
                scope,
                direct=False,
            )
        if isinstance(target, (ast.List, ast.Tuple)):
            return any(
                generic_persistent_assignment_escape(
                    item,
                    value,
                    scope,
                    direct=False,
                )
                for item in target.elts
            )
        return False

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

    def flow_sensitive_literal_container(
            expression: ast.AST,
            scope: ast.AST | None,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> tuple[ast.List | ast.Tuple | ast.Dict, ast.AST | None] | None:
        if isinstance(expression, (ast.List, ast.Tuple, ast.Dict)):
            return expression, scope
        if isinstance(expression, ast.Subscript):
            resolved = flow_sensitive_literal_container(
                expression.value,
                scope,
                seen,
            )
            if resolved is None or not isinstance(expression.slice, ast.Constant):
                return None
            container, container_scope = resolved
            selected = None
            key = expression.slice.value
            if isinstance(container, (ast.List, ast.Tuple)) and isinstance(key, int):
                if -len(container.elts) <= key < len(container.elts):
                    selected = container.elts[key]
            elif isinstance(container, ast.Dict):
                for dict_key, dict_value in reversed(tuple(zip(
                    container.keys,
                    container.values,
                ))):
                    if (
                        isinstance(dict_key, ast.Constant)
                        and type(dict_key.value) is type(key)
                        and dict_key.value == key
                    ):
                        selected = dict_value
                        break
            return (
                flow_sensitive_literal_container(
                    selected,
                    container_scope,
                    seen,
                )
                if selected is not None
                else None
            )
        if not isinstance(expression, ast.Name):
            return None
        lookup_scope = scope
        while True:
            if lookup_scope is not None and expression.id in scope_global_names[lookup_scope]:
                lookup_scope = None
            elif (
                lookup_scope is not None
                and expression.id in scope_nonlocal_names[lookup_scope]
            ):
                lookup_scope = callable_parents[lookup_scope]
                continue
            if expression.id in scope_bound_names[lookup_scope]:
                break
            if lookup_scope is None:
                return None
            lookup_scope = callable_parents[lookup_scope]
        alias_key = (lookup_scope, expression.id)
        if alias_key in seen:
            return None
        container = tree if lookup_scope is None else lookup_scope
        candidate_body = container.body if hasattr(container, "body") else []
        body = candidate_body if isinstance(candidate_body, list) else []
        direct_child: ast.AST = expression
        while (
            parents.get(direct_child) is not container
            and parents.get(direct_child) is not None
        ):
            direct_child = parents[direct_child]
        before_index = body.index(direct_child) if direct_child in body else len(body)
        for statement in reversed(body[:before_index]):
            assigned = None
            assigned_scope = lookup_scope
            is_binding = False
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    assigned = assigned_value_for_name(
                        target,
                        statement.value,
                        expression.id,
                    )
                    if assigned is not None:
                        is_binding = True
                        break
                    if expression.id in target_names(target):
                        resolved_value = flow_sensitive_literal_container(
                            statement.value,
                            lookup_scope,
                            seen | {alias_key},
                        )
                        if resolved_value is not None:
                            value_container, assigned_scope = resolved_value
                            assigned = assigned_value_for_name(
                                target,
                                value_container,
                                expression.id,
                            )
                            is_binding = assigned is not None
                            if is_binding:
                                break
            elif isinstance(statement, ast.AnnAssign):
                is_binding = expression.id in target_names(statement.target)
                assigned = statement.value if is_binding else None
            elif isinstance(statement, (ast.AugAssign, ast.Delete)):
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Delete)
                    else [statement.target]
                )
                is_binding = any(
                    expression.id in target_names(target)
                    for target in targets
                )
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                is_binding = any(
                    item.optional_vars is not None
                    and expression.id in target_names(item.optional_vars)
                    for item in statement.items
                )
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                is_binding = statement.name == expression.id
            elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                bound_names = {
                    alias.asname
                    or (
                        alias.name
                        if isinstance(statement, ast.ImportFrom)
                        else alias.name.split(".")[0]
                    )
                    for alias in statement.names
                }
                is_binding = expression.id in bound_names
            if not is_binding:
                continue
            if assigned is None:
                return None
            return flow_sensitive_literal_container(
                assigned,
                assigned_scope,
                seen | {alias_key},
            )
        return None

    def flow_sensitive_container_reference(
            expression: ast.AST,
            scope: ast.AST | None,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> tuple[
        ast.List | ast.Tuple | ast.Dict,
        tuple[object, ...],
        ast.AST | None,
    ] | None:
        if isinstance(expression, (ast.List, ast.Tuple, ast.Dict)):
            return expression, (), scope
        if isinstance(expression, ast.Subscript):
            if not isinstance(expression.slice, ast.Constant):
                return None
            resolved = flow_sensitive_container_reference(
                expression.value,
                scope,
                seen,
            )
            if resolved is None:
                return None
            root, path, root_scope = resolved
            return root, path + (expression.slice.value,), root_scope
        if not isinstance(expression, ast.Name):
            return None
        lookup_scope = scope
        while True:
            if lookup_scope is not None and expression.id in scope_global_names[lookup_scope]:
                lookup_scope = None
            elif (
                lookup_scope is not None
                and expression.id in scope_nonlocal_names[lookup_scope]
            ):
                lookup_scope = callable_parents[lookup_scope]
                continue
            if expression.id in scope_bound_names[lookup_scope]:
                break
            if lookup_scope is None:
                return None
            lookup_scope = callable_parents[lookup_scope]
        alias_key = (lookup_scope, expression.id)
        if alias_key in seen:
            return None
        container = tree if lookup_scope is None else lookup_scope
        candidate_body = container.body if hasattr(container, "body") else []
        body = candidate_body if isinstance(candidate_body, list) else []
        direct_child: ast.AST = expression
        while (
            parents.get(direct_child) is not container
            and parents.get(direct_child) is not None
        ):
            direct_child = parents[direct_child]
        before_index = body.index(direct_child) if direct_child in body else len(body)
        for statement in reversed(body[:before_index]):
            assigned = None
            assigned_scope = lookup_scope
            is_binding = False
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    assigned = assigned_value_for_name(
                        target,
                        statement.value,
                        expression.id,
                    )
                    if assigned is None and expression.id in target_names(target):
                        resolved_value = flow_sensitive_literal_container(
                            statement.value,
                            lookup_scope,
                            seen | {alias_key},
                        )
                        if resolved_value is not None:
                            value_container, assigned_scope = resolved_value
                            assigned = assigned_value_for_name(
                                target,
                                value_container,
                                expression.id,
                            )
                    if assigned is not None:
                        is_binding = True
                        break
            elif isinstance(statement, ast.AnnAssign):
                is_binding = expression.id in target_names(statement.target)
                assigned = statement.value if is_binding else None
            elif isinstance(statement, (ast.AugAssign, ast.Delete)):
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Delete)
                    else [statement.target]
                )
                is_binding = any(
                    expression.id in target_names(target)
                    for target in targets
                )
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                is_binding = any(
                    item.optional_vars is not None
                    and expression.id in target_names(item.optional_vars)
                    for item in statement.items
                )
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                is_binding = statement.name == expression.id
            elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                bound_names = {
                    alias.asname
                    or (
                        alias.name
                        if isinstance(statement, ast.ImportFrom)
                        else alias.name.split(".")[0]
                    )
                    for alias in statement.names
                }
                is_binding = expression.id in bound_names
            if not is_binding:
                continue
            if assigned is None:
                return None
            return flow_sensitive_container_reference(
                assigned,
                assigned_scope,
                seen | {alias_key},
            )
        return None

    def flow_sensitive_container_references(
            expression: ast.AST,
            scope: ast.AST | None,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> set[tuple[
        ast.List | ast.Tuple | ast.Dict,
        tuple[object, ...],
        ast.AST | None,
    ]]:
        references = set()
        direct = flow_sensitive_container_reference(expression, scope, seen)
        if direct is not None:
            references.add(direct)

        suffix = []
        base = expression
        while isinstance(base, ast.Subscript):
            if not isinstance(base.slice, ast.Constant):
                return references
            suffix.append(base.slice.value)
            base = base.value
        if not isinstance(base, ast.Name):
            return references
        suffix_path = tuple(reversed(suffix))
        lookup_scope = scope
        while True:
            if lookup_scope is not None and base.id in scope_global_names[lookup_scope]:
                lookup_scope = None
            elif lookup_scope is not None and base.id in scope_nonlocal_names[lookup_scope]:
                lookup_scope = callable_parents[lookup_scope]
                continue
            if base.id in scope_bound_names[lookup_scope]:
                break
            if lookup_scope is None:
                return references
            lookup_scope = callable_parents[lookup_scope]
        container = tree if lookup_scope is None else lookup_scope
        candidate_body = container.body if hasattr(container, "body") else []
        body = candidate_body if isinstance(candidate_body, list) else []
        direct_child: ast.AST = expression
        while (
            parents.get(direct_child) is not container
            and parents.get(direct_child) is not None
        ):
            direct_child = parents[direct_child]
        before_index = body.index(direct_child) if direct_child in body else len(body)
        cutoff = (-1, -1)
        for statement in body[:before_index]:
            if (
                isinstance(statement, ast.Assign)
                and any(base.id in target_names(target) for target in statement.targets)
            ) or (
                isinstance(statement, (ast.AnnAssign, ast.AugAssign))
                and base.id in target_names(statement.target)
            ) or (
                isinstance(statement, ast.Delete)
                and any(base.id in target_names(target) for target in statement.targets)
            ) or (
                isinstance(statement, (ast.With, ast.AsyncWith))
                and any(
                    item.optional_vars is not None
                    and base.id in target_names(item.optional_vars)
                    for item in statement.items
                )
            ) or (
                isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and statement.name == base.id
            ):
                cutoff = (statement.lineno, statement.col_offset)

        query_position = (expression.lineno, expression.col_offset)
        for target in ast.walk(container):
            if (
                not isinstance(target, ast.Name)
                or target.id != base.id
                or not isinstance(target.ctx, ast.Store)
                or enclosing_callable(target) is not lookup_scope
            ):
                continue
            position = (target.lineno, target.col_offset)
            if not cutoff < position < query_position:
                continue
            owner: ast.AST = target
            while not isinstance(owner, ast.stmt) and parents.get(owner) is not None:
                owner = parents[owner]
            if owner in body:
                continue
            assigned = None
            if isinstance(owner, ast.Assign):
                for owner_target in owner.targets:
                    assigned = assigned_value_for_name(
                        owner_target,
                        owner.value,
                        base.id,
                    )
                    if assigned is not None:
                        break
            elif isinstance(owner, (ast.AnnAssign, ast.NamedExpr)):
                assigned = assigned_value_for_name(
                    owner.target,
                    owner.value,
                    base.id,
                )
            if assigned is None:
                continue
            alternate = flow_sensitive_container_reference(
                assigned,
                lookup_scope,
                seen | {(lookup_scope, base.id)},
            )
            if alternate is None:
                continue
            root, path, root_scope = alternate
            references.add((root, path + suffix_path, root_scope))
        return references

    def select_constant_container_path(
            expression: ast.AST,
            scope: ast.AST | None,
            path: tuple[object, ...],
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> tuple[ast.AST, ast.AST | None] | None:
        current = expression
        current_scope = scope
        for key in path:
            resolved = flow_sensitive_literal_container(
                current,
                current_scope,
                seen,
            )
            if resolved is None:
                return None
            container, current_scope = resolved
            selected = None
            if isinstance(container, (ast.List, ast.Tuple)) and isinstance(key, int):
                if -len(container.elts) <= key < len(container.elts):
                    selected = container.elts[key]
            elif isinstance(container, ast.Dict):
                for dict_key, dict_value in reversed(tuple(zip(
                    container.keys,
                    container.values,
                ))):
                    if (
                        isinstance(dict_key, ast.Constant)
                        and dict_key.value == key
                    ):
                        selected = dict_value
                        break
            if selected is None:
                return None
            current = selected
        return current, current_scope

    def flow_sensitive_subscript_values(
            expression: ast.Subscript,
            scope: ast.AST | None,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> set[tuple[ast.AST, ast.AST | None]]:
        queries = flow_sensitive_container_references(expression, scope, seen)
        if not queries:
            return set()

        def definitely_precedes(owner: ast.stmt, reference: ast.AST) -> bool:
            owner_parent = parents.get(owner)
            if owner_parent is None:
                return False
            for field_name in ("body", "orelse", "finalbody"):
                block = getattr(owner_parent, field_name, None)
                if not isinstance(block, list) or owner not in block:
                    continue
                reference_child = reference
                while (
                    parents.get(reference_child) is not owner_parent
                    and parents.get(reference_child) is not None
                ):
                    reference_child = parents[reference_child]
                if (
                    reference_child in block
                    and block.index(owner) < block.index(reference_child)
                ):
                    return True
            return False

        def delete_replacement(
                root: ast.AST,
                root_scope: ast.AST | None,
                target_path: tuple[object, ...],
                query_path: tuple[object, ...],
        ) -> tuple[bool, tuple[ast.AST, ast.AST | None] | None]:
            if not target_path:
                return False, None
            parent_path = target_path[:-1]
            if (
                len(query_path) <= len(parent_path)
                or query_path[:len(parent_path)] != parent_path
            ):
                return False, None
            parent_value = select_constant_container_path(
                root,
                root_scope,
                parent_path,
                seen,
            )
            if parent_value is None:
                return False, None
            parent_expression, parent_scope = parent_value
            resolved_parent = flow_sensitive_literal_container(
                parent_expression,
                parent_scope,
                seen,
            )
            if resolved_parent is None:
                return False, None
            parent_container, parent_scope = resolved_parent
            deleted_key = target_path[-1]
            query_key = query_path[len(parent_path)]
            if isinstance(parent_container, ast.Dict):
                return (
                    deleted_key == query_key,
                    None,
                )
            if not (
                isinstance(parent_container, (ast.List, ast.Tuple))
                and isinstance(deleted_key, int)
                and isinstance(query_key, int)
            ):
                return False, None
            values = list(parent_container.elts)
            delete_index = deleted_key if deleted_key >= 0 else len(values) + deleted_key
            if not 0 <= delete_index < len(values):
                return True, None
            del values[delete_index]
            query_index = query_key if query_key >= 0 else len(values) + query_key
            if not 0 <= query_index < len(values):
                return True, None
            selected = values[query_index]
            return True, select_constant_container_path(
                selected,
                parent_scope,
                query_path[len(parent_path) + 1:],
                seen,
            )

        all_possible_values = set()
        query_position = (expression.lineno, expression.col_offset)
        for root, query_path, root_scope in queries:
            initial = select_constant_container_path(
                root,
                root_scope,
                query_path,
                seen,
            )
            possible_values = {initial} if initial is not None else set()
            events = []
            for owner in ast.walk(tree):
                value = None
                targets = []
                is_delete = False
                if isinstance(owner, ast.Assign):
                    value = owner.value
                    targets = owner.targets
                elif isinstance(owner, ast.AnnAssign):
                    value = owner.value
                    targets = [owner.target]
                elif isinstance(owner, ast.AugAssign):
                    value = owner.value
                    targets = [owner.target]
                elif isinstance(owner, ast.Delete):
                    targets = owner.targets
                    is_delete = True
                else:
                    continue
                owner_position = (owner.lineno, owner.col_offset)
                if owner_position >= query_position:
                    continue
                for target in targets:
                    if not isinstance(target, ast.Subscript):
                        continue
                    target_scope = enclosing_callable(target)
                    if target_scope not in {scope, root_scope}:
                        continue
                    target_references = flow_sensitive_container_references(
                        target,
                        target_scope,
                        seen,
                    )
                    if not target_references:
                        continue
                    replacements = set()
                    affecting_count = 0
                    for target_root, target_path, _ in target_references:
                        if target_root is not root:
                            continue
                        if is_delete:
                            affects, replacement = delete_replacement(
                                root,
                                root_scope,
                                target_path,
                                query_path,
                            )
                            if not affects:
                                continue
                        else:
                            if (
                                len(target_path) > len(query_path)
                                or query_path[:len(target_path)] != target_path
                            ):
                                continue
                            replacement = (
                                select_constant_container_path(
                                    value,
                                    target_scope,
                                    query_path[len(target_path):],
                                    seen,
                                )
                                if value is not None
                                else None
                            )
                        affecting_count += 1
                        if replacement is not None:
                            replacements.add(replacement)
                    if not affecting_count:
                        continue
                    must_affect = affecting_count == len(target_references)
                    events.append((
                        owner_position,
                        definitely_precedes(owner, expression) and must_affect,
                        is_delete,
                        replacements,
                        isinstance(owner, ast.AugAssign),
                    ))

            for _, definite, is_delete, replacements, is_augmented in sorted(
                events,
                key=lambda event: event[0],
            ):
                if definite and not is_augmented:
                    possible_values = set(replacements)
                elif not is_delete:
                    possible_values.update(replacements)
                else:
                    possible_values.update(replacements)
            all_possible_values.update(possible_values)
        return all_possible_values

    def flow_sensitive_import_origins(
            expression: ast.AST,
            scope: ast.AST | None,
            seen: frozenset[tuple[ast.AST | None, str]] = frozenset(),
    ) -> set[str]:
        if isinstance(expression, (ast.NamedExpr, ast.Starred)):
            return flow_sensitive_import_origins(expression.value, scope, seen)
        if isinstance(expression, ast.IfExp):
            return (
                flow_sensitive_import_origins(expression.body, scope, seen)
                | flow_sensitive_import_origins(expression.orelse, scope, seen)
            )
        if isinstance(expression, ast.Call):
            return flow_sensitive_import_origins(expression.func, scope, seen)
        if isinstance(expression, ast.Attribute):
            return {
                f"{origin}.{expression.attr}"
                for origin in flow_sensitive_import_origins(
                    expression.value,
                    scope,
                    seen,
                )
            }
        if isinstance(expression, ast.Subscript):
            selected_values = flow_sensitive_subscript_values(
                expression,
                scope,
                seen,
            )
            return set().union(*(
                flow_sensitive_import_origins(
                    selected,
                    selected_scope,
                    seen,
                )
                for selected, selected_scope in selected_values
            )) if selected_values else set()
        if not isinstance(expression, ast.Name):
            return set()

        child: ast.AST = expression
        lexical_parent = parents.get(child)
        while lexical_parent is not None and lexical_parent is not scope:
            if (
                isinstance(lexical_parent, (ast.For, ast.AsyncFor))
                and child in lexical_parent.body
                and expression.id in target_names(lexical_parent.target)
            ):
                return set()
            if (
                isinstance(lexical_parent, (ast.With, ast.AsyncWith))
                and child in lexical_parent.body
                and any(
                    item.optional_vars is not None
                    and expression.id in target_names(item.optional_vars)
                    for item in lexical_parent.items
                )
            ):
                return set()
            if (
                isinstance(lexical_parent, ast.ExceptHandler)
                and child in lexical_parent.body
                and lexical_parent.name == expression.id
            ):
                return set()
            if isinstance(lexical_parent, (
                ast.ListComp,
                ast.SetComp,
                ast.GeneratorExp,
                ast.DictComp,
            )):
                generators = lexical_parent.generators
                if any(
                    expression.id in target_names(generator.target)
                    and not (
                        expression is generator.iter
                        or any(
                            expression is descendant
                            for descendant in ast.walk(generator.iter)
                        )
                    )
                    for generator in generators
                ):
                    return set()
            if isinstance(lexical_parent, (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.Lambda,
            )):
                break
            child = lexical_parent
            lexical_parent = parents.get(child)

        lookup_scope = scope
        while True:
            if lookup_scope is not None and expression.id in scope_global_names[lookup_scope]:
                lookup_scope = None
            elif (
                lookup_scope is not None
                and expression.id in scope_nonlocal_names[lookup_scope]
            ):
                lookup_scope = callable_parents[lookup_scope]
                continue
            if expression.id in scope_bound_names[lookup_scope]:
                break
            if lookup_scope is None:
                return set(resolve_import_origins(expression))
            lookup_scope = callable_parents[lookup_scope]

        alias_key = (lookup_scope, expression.id)
        if alias_key in seen:
            return set()
        container = tree if lookup_scope is None else lookup_scope
        candidate_body = container.body if hasattr(container, "body") else []
        body = candidate_body if isinstance(candidate_body, list) else []
        direct_child: ast.AST = expression
        while (
            parents.get(direct_child) is not container
            and parents.get(direct_child) is not None
        ):
            direct_child = parents[direct_child]
        before_index = (
            body.index(direct_child)
            if direct_child in body
            else len(body)
        )

        def conditional_assignment_origins_after(
                cutoff: tuple[int, int],
        ) -> set[str]:
            reference_position = (expression.lineno, expression.col_offset)
            origins = set()
            for candidate in ast.walk(container):
                if not isinstance(candidate, (ast.Import, ast.ImportFrom)):
                    continue
                position = (candidate.lineno, candidate.col_offset)
                if not cutoff < position < reference_position:
                    continue
                if (
                    candidate in body
                    or enclosing_callable(candidate) is not lookup_scope
                    or is_in_unmodeled_class_namespace(candidate)
                ):
                    continue
                for alias in candidate.names:
                    bound_name = (
                        alias.asname
                        or (
                            alias.name
                            if isinstance(candidate, ast.ImportFrom)
                            else alias.name.split(".", 1)[0]
                        )
                    )
                    if bound_name != expression.id:
                        continue
                    if (
                        isinstance(candidate, ast.ImportFrom)
                        and candidate.level == 0
                        and candidate.module
                    ):
                        origins.add(f"{candidate.module}.{alias.name}")
                    elif isinstance(candidate, ast.Import):
                        origins.add(
                            alias.name
                            if alias.asname
                            else alias.name.split(".", 1)[0]
                        )
            for target in ast.walk(container):
                if (
                    not isinstance(target, ast.Name)
                    or target.id != expression.id
                    or not isinstance(target.ctx, ast.Store)
                    or enclosing_callable(target) is not lookup_scope
                    or is_in_unmodeled_class_namespace(target)
                ):
                    continue
                position = (target.lineno, target.col_offset)
                if not cutoff < position < reference_position:
                    continue
                owner: ast.AST = target
                while (
                    not isinstance(owner, ast.stmt)
                    and parents.get(owner) is not None
                ):
                    owner = parents[owner]
                if owner in body:
                    continue
                assigned = None
                if isinstance(owner, ast.Assign):
                    for assignment_target in owner.targets:
                        assigned = assigned_value_for_name(
                            assignment_target,
                            owner.value,
                            expression.id,
                        )
                        if assigned is not None:
                            break
                elif isinstance(owner, ast.AnnAssign) and owner.value is not None:
                    assigned = assigned_value_for_name(
                        owner.target,
                        owner.value,
                        expression.id,
                    )
                if assigned is not None:
                    origins.update(flow_sensitive_import_origins(
                        assigned,
                        lookup_scope,
                        seen | {alias_key},
                    ))
            return origins

        for statement in reversed(body[:before_index]):
            assigned: ast.AST | None = None
            assigned_scope = lookup_scope
            is_binding = False
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    if (alias.asname or alias.name.split(".")[0]) == expression.id:
                        return {
                            alias.name
                            if alias.asname
                            else alias.name.split(".")[0]
                        } | conditional_assignment_origins_after(
                            (statement.lineno, statement.col_offset)
                        )
            elif isinstance(statement, ast.ImportFrom):
                if statement.level == 0 and statement.module:
                    for alias in statement.names:
                        if (alias.asname or alias.name) == expression.id:
                            return {
                                f"{statement.module}.{alias.name}"
                            } | conditional_assignment_origins_after(
                                (statement.lineno, statement.col_offset)
                            )
            elif isinstance(statement, ast.Assign):
                for target in statement.targets:
                    assigned = assigned_value_for_name(
                        target,
                        statement.value,
                        expression.id,
                    )
                    if assigned is not None:
                        is_binding = True
                        break
                    if expression.id in target_names(target):
                        resolved_value = flow_sensitive_literal_container(
                            statement.value,
                            lookup_scope,
                            seen | {alias_key},
                        )
                        if resolved_value is not None:
                            value_container, assigned_scope = resolved_value
                            assigned = assigned_value_for_name(
                                target,
                                value_container,
                                expression.id,
                            )
                            is_binding = assigned is not None
                            if is_binding:
                                break
            elif isinstance(statement, ast.AnnAssign):
                is_binding = expression.id in target_names(statement.target)
                if is_binding:
                    assigned = statement.value
            elif isinstance(statement, (ast.AugAssign, ast.Delete)):
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Delete)
                    else [statement.target]
                )
                is_binding = any(
                    expression.id in target_names(target)
                    for target in targets
                )
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                is_binding = any(
                    item.optional_vars is not None
                    and expression.id in target_names(item.optional_vars)
                    for item in statement.items
                )
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                is_binding = statement.name == expression.id
            if not is_binding:
                continue
            if assigned is None:
                base_origins = set()
            else:
                base_origins = flow_sensitive_import_origins(
                    assigned,
                    assigned_scope,
                    seen | {alias_key},
                )
            return base_origins | conditional_assignment_origins_after(
                (statement.lineno, statement.col_offset)
            )

        if lookup_scope is not None and expression.id in {
            argument.arg
            for argument in (
                lookup_scope.args.posonlyargs
                + lookup_scope.args.args
                + lookup_scope.args.kwonlyargs
            )
        }:
            return set()
        return set(resolve_import_origins(expression))

    findings = []
    for node in ast.walk(tree):
        if node in forced_higher_order_findings or node in forced_iterable_findings:
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
                    qualified_name in (
                        KNOWN_CONCURRENCY_FULL_IMPORT_NAMES - {"pydoc.browse"}
                    )
                    for qualified_name in qualified_import_attribute_names(node)
                )
            )
        ):
            findings.append(node)
        elif (
            isinstance(node, ast.Call)
            and EXECUTABLE_DESERIALIZER_FULL_IMPORT_NAMES.intersection(
                flow_sensitive_import_origins(
                    node.func,
                    enclosing_callable(node),
                )
            )
        ):
            findings.append(node)
        elif (
            isinstance(node, ast.Call)
            and "pydoc.browse" in flow_sensitive_import_origins(
                node.func,
                enclosing_callable(node),
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
                and any(
                    generic_persistent_assignment_escape(
                        target,
                        value,
                        enclosing_callable(node),
                        direct=True,
                    )
                    for target in targets
                )
            ):
                findings.append(node)
        elif (
            isinstance(node, ast.AugAssign)
            and contains_persistent_target(node.target)
            and (
                carries_state_escape_value(
                    node.value,
                    enclosing_callable(node),
                )
                or (
                    isinstance(node.target, ast.Subscript)
                    and carries_state_escape_value(
                        node.target.slice,
                        enclosing_callable(node),
                    )
                )
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
                "from pydoc import browse as open_browser\n"
                "open_browser(0)\n",
                ("pydoc", "browse"),
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
                "import pydoc as p\nopen_browser = p.browse\n"
                "open_browser(0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "safe, open_browser = harmless, p.browse\n"
                "open_browser(0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [harmless, p.browse]\n"
                "handlers[1](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = (p.browse, harmless)\n"
                "open_browser = handlers[0]\n"
                "open_browser(0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = {'open': p.browse}\n"
                "handlers['open'](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "modules = [p]\n"
                "modules[0].browse(0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [[p.browse]]\n"
                "handlers[0][0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = {'group': [p.browse]}\n"
                "handlers['group'][0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [[p.browse]]\n"
                "inner = handlers[0]\n"
                "inner[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "launch = p.browse\n"
                "for launch in values:\n"
                "    pass\n"
                "launch(0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [harmless]\n"
                "handlers[0] = p.browse\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = {'open': harmless}\n"
                "alias = handlers\n"
                "alias['open'] = p.browse\n"
                "handlers['open'](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = {'group': [harmless]}\n"
                "inner = handlers['group']\n"
                "inner[0] = p.browse\n"
                "handlers['group'][0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [p.browse]\n"
                "if enabled:\n"
                "    handlers[0] = harmless\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [harmless]\n"
                "if enabled:\n"
                "    handlers[0] = p.browse\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [p.browse]\n"
                "for _ in values:\n"
                "    handlers[0] = harmless\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [harmless]\n"
                "for _ in values:\n"
                "    handlers[0] = p.browse\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = {'open': harmless, 'open': p.browse}\n"
                "handlers['open'](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [harmless]\n"
                "if enabled:\n"
                "    handlers = [p.browse]\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [p.browse]\n"
                "other = [harmless]\n"
                "alias = handlers\n"
                "if enabled:\n"
                "    alias = other\n"
                "alias[0] = harmless\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = [harmless, p.browse]\n"
                "del handlers[0]\n"
                "handlers[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = ([p.browse],)\n"
                "(inner,) = handlers\n"
                "inner[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = {'group': ([p.browse],)}\n"
                "(inner,) = handlers['group']\n"
                "inner[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = (harmless, p.browse)\n"
                "first, *rest = handlers\n"
                "rest[0](0)\n",
                {"p": "pydoc"},
            ),
            (
                "import pydoc as p\n"
                "handlers = (harmless, p.browse)\n"
                "selected, selected = handlers\n"
                "selected(0)\n",
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

        shadowed_browse_source = (
            "import pydoc as p\n"
            "def harmless(p):\n"
            "    return p.browse(0)\n"
            "harmless(None)\n"
        )
        self.assertFalse(
            sensitive_module_reexports(
                ast.parse(shadowed_browse_source),
                {"p": "pydoc"},
            ),
            "a local receiver must shadow the imported pydoc alias",
        )

        for safe_source in (
            (
                "import pydoc as docs\n"
                "docs = harmless\n"
                "docs.browse(0)\n"
            ),
            (
                "import pydoc as docs\n"
                "danger, safe = docs.browse, harmless\n"
                "safe(0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = [docs.browse]\n"
                "handlers = [harmless]\n"
                "handlers[0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = (docs.browse, harmless)\n"
                "handlers[1](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "def harmless(docs):\n"
                "    handlers = [docs.browse]\n"
                "    return handlers[0](0)\n"
                "harmless(None)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = [[docs.browse]]\n"
                "handlers = [[harmless]]\n"
                "handlers[0][0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = [[docs.browse]]\n"
                "inner = handlers[0]\n"
                "inner = [harmless]\n"
                "inner[0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = [docs.browse]\n"
                "handlers[0] = harmless\n"
                "handlers[0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = {'open': docs.browse}\n"
                "alias = handlers\n"
                "alias['open'] = harmless\n"
                "handlers['open'](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = {'group': [docs.browse]}\n"
                "inner = handlers['group']\n"
                "inner[0] = harmless\n"
                "handlers['group'][0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = [docs.browse]\n"
                "del handlers[0]\n"
                "handlers[0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = {'open': docs.browse, 'open': harmless}\n"
                "handlers['open'](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = [docs.browse, harmless]\n"
                "del handlers[0]\n"
                "handlers[0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = ([harmless],)\n"
                "(inner,) = handlers\n"
                "inner[0](0)\n"
            ),
            (
                "import pydoc as docs\n"
                "handlers = (docs.browse, harmless)\n"
                "selected, selected = handlers\n"
                "selected(0)\n"
            ),
        ):
            with self.subTest(safe_pydoc_flow=safe_source):
                self.assertFalse(
                    sensitive_module_reexports(
                        ast.parse(safe_source),
                        {"docs": "pydoc"},
                    ),
                    "a killed or uncalled pydoc browse alias must stay safe",
                )

        example_browse_container = (
            "import example as module\n"
            "handlers = {'group': [[module.browse]]}\n"
            "handlers['group'][0][0](0)\n"
        )
        self.assertFalse(
            sensitive_module_reexports(
                ast.parse(example_browse_container),
                {"module": "example"},
            ),
            "an unrelated browse function must remain safe in a container",
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
            "for-iterable": (
                "for value in [p]:\n"
                "    value.os.fork()\n"
            ),
            "for-destructured-iterable": (
                "for left, (middle, *rest) in [(None, (p, p))]:\n"
                "    middle.os.fork()\n"
            ),
            "for-starred-destructuring": (
                "for left, *rest in [(None, p)]:\n"
                "    rest[0].os.fork()\n"
            ),
            "for-local-return-iterable": (
                "def wrap(value):\n"
                "    return [value]\n"
                "for value in wrap(p):\n"
                "    value.os.fork()\n"
            ),
            "for-generator-expression-wrapper": (
                "for value in (item for item in [p]):\n"
                "    value.os.fork()\n"
            ),
            "for-set-wrapper": (
                "for value in {p}:\n"
                "    value.os.fork()\n"
            ),
            "for-builtin-iter-wrapper": (
                "for value in iter([p]):\n"
                "    value.os.fork()\n"
            ),
            "for-list-comprehension-wrapper": (
                "for value in [item for item in [p]]:\n"
                "    value.os.fork()\n"
            ),
            "for-local-generator-alias": (
                "def rows(value):\n"
                "    yield value\n"
                "stream = rows(p)\n"
                "for value in stream:\n"
                "    value.os.fork()\n"
            ),
            "for-unordered-destructured-set": (
                "for left, right in [{None, p}]:\n"
                "    left.os.fork()\n"
            ),
            "async-for-iterable": (
                "async def rows(value):\n"
                "    yield value\n"
                "async def run():\n"
                "    async for value in rows(p):\n"
                "        value.os.fork()\n"
            ),
            "async-for-local-generator-alias": (
                "async def rows(value):\n"
                "    yield value\n"
                "async def run():\n"
                "    stream = rows(p)\n"
                "    async for value in stream:\n"
                "        value.os.fork()\n"
            ),
            "async-for-builtin-aiter-wrapper": (
                "async def rows(value):\n"
                "    yield value\n"
                "async def run():\n"
                "    async for value in aiter(rows(p)):\n"
                "        value.os.fork()\n"
            ),
            "for-persistent-target": (
                "for holder.module in [p]:\n"
                "    pass\n"
            ),
            "for-safe-kill-then-tracked-rebind": (
                "original = p\n"
                "for p in [None]:\n"
                "    p = original\n"
                "    p.os.fork()\n"
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
            "sorted-generator-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted(*(item for item in ([p],)), key=invoke)\n"
            ),
            "map-generator-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "map(invoke, *(item for item in ([p],)))\n"
            ),
            "filter-generator-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "filter(invoke, *(item for item in ([p],)))\n"
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
            "starmap-position": (
                "from itertools import starmap\n"
                "def invoke(left, right):\n"
                "    right.os.fork()\n"
                "starmap(invoke, [(None, p)])\n"
            ),
            "starmap-alias-bound-method": (
                "import itertools as tools\n"
                "class Runner:\n"
                "    def invoke(self, left, right):\n"
                "        right.os.fork()\n"
                "apply = tools.starmap\n"
                "apply(Runner().invoke, [(None, p)])\n"
            ),
            "starmap-unresolved-callback": (
                "from itertools import starmap\n"
                "starmap(external_callback, [(p,)])\n"
            ),
            "starmap-generator-row-alias": (
                "from itertools import starmap\n"
                "def invoke(left, right):\n"
                "    right.os.fork()\n"
                "rows = (row for row in [(None, p)])\n"
                "starmap(invoke, rows)\n"
            ),
            "starmap-nonidentity-generator-row": (
                "from itertools import starmap\n"
                "def invoke(left, right):\n"
                "    right.os.fork()\n"
                "row = (None, p)\n"
                "starmap(invoke, (row for _ in (0,)))\n"
            ),
            "starmap-local-generator-alias": (
                "from itertools import starmap\n"
                "def invoke(left, right):\n"
                "    right.os.fork()\n"
                "def rows(value):\n"
                "    yield (None, value)\n"
                "stream = rows(p)\n"
                "starmap(invoke, stream)\n"
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
            "safe-for-iterable": (
                "for value in [None]:\n"
                "    value.os.fork()\n"
            ),
            "for-overwrites-import-with-safe-value": (
                "for p in [None]:\n"
                "    p.os.fork()\n"
            ),
            "for-overwrites-import-in-destructuring": (
                "for other, p in [(None, None)]:\n"
                "    p.os.fork()\n"
            ),
            "for-body-overwrites-tracked-value": (
                "for p in [p]:\n"
                "    p = None\n"
                "    p.os.fork()\n"
            ),
            "killed-iterable-alias": (
                "stream = [p]\n"
                "stream = [None]\n"
                "for value in stream:\n"
                "    value.os.fork()\n"
            ),
            "killed-builtin-iter-alias": (
                "walk = iter\n"
                "walk = lambda values: [None]\n"
                "for value in walk([p]):\n"
                "    value.os.fork()\n"
            ),
            "for-safe-overwrite-propagates-to-local": (
                "for p in [None]:\n"
                "    local = p\n"
                "    local.os.fork()\n"
            ),
            "safe-for-local-shadow": (
                "def harmless(p):\n"
                "    for value in [p]:\n"
                "        value.os.fork()\n"
                "harmless(None)\n"
            ),
            "safe-for-destructured-position": (
                "for left, right in [(None, p)]:\n"
                "    left.os.fork()\n"
            ),
            "safe-generator-transform": (
                "for value in (None for item in [p]):\n"
                "    value.os.fork()\n"
            ),
            "safe-local-generator-alias": (
                "def rows(value):\n"
                "    yield None\n"
                "stream = rows(p)\n"
                "for value in stream:\n"
                "    value.os.fork()\n"
            ),
            "safe-set-wrapper": (
                "for value in {None}:\n"
                "    value.os.fork()\n"
            ),
            "shadowed-iter-wrapper": (
                "def iter(values):\n"
                "    return [None]\n"
                "for value in iter([p]):\n"
                "    value.os.fork()\n"
            ),
            "shadowed-aiter-wrapper": (
                "def aiter(values):\n"
                "    return safe_stream\n"
                "async def rows(value):\n"
                "    yield value\n"
                "async def run():\n"
                "    async for value in aiter(rows(p)):\n"
                "        value.os.fork()\n"
            ),
            "safe-async-for-iterable": (
                "async def rows(value):\n"
                "    yield None\n"
                "async def run():\n"
                "    async for value in rows(p):\n"
                "        value.os.fork()\n"
            ),
            "class-loop-target-does-not-leak-to-module": (
                "class Holder:\n"
                "    for value in [p]:\n"
                "        pass\n"
                "value.os.fork()\n"
            ),
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
            "sorted-generator-callback-ignores-item": (
                "def ignore(value):\n"
                "    return None\n"
                "sorted(*(item for item in ([p],)), key=ignore)\n"
            ),
            "safe-sorted-generator-star": (
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "sorted(*(item for item in ([None],)), key=invoke)\n"
            ),
            "tracked-map-callback-is-not-carrier": (
                "map(p, *(item for item in ([None],)))\n"
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
            "starmap-position-precision": (
                "from itertools import starmap\n"
                "def invoke(left, right):\n"
                "    left.os.fork()\n"
                "starmap(invoke, [(None, p)])\n"
            ),
            "safe-starmap-iterable": (
                "from itertools import starmap\n"
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "starmap(invoke, [(None,)])\n"
            ),
            "tracked-starmap-callback-is-not-carrier": (
                "from itertools import starmap\n"
                "starmap(p, [(None,)])\n"
            ),
            "shadowed-starmap": (
                "def starmap(callback, rows):\n"
                "    return None\n"
                "def invoke(value):\n"
                "    value.os.fork()\n"
                "starmap(invoke, [(p,)])\n"
            ),
            "starmap-callback-ignores-item": (
                "from itertools import starmap\n"
                "def ignore(value):\n"
                "    return None\n"
                "starmap(ignore, [(p,)])\n"
            ),
            "safe-starmap-generator-row": (
                "from itertools import starmap\n"
                "def invoke(left, right):\n"
                "    right.os.fork()\n"
                "row = (None, None)\n"
                "starmap(invoke, (row for _ in (0,)))\n"
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
            "metaclass-call-store": (
                "class Meta(type):\n"
                "    def __call__(cls, value):\n"
                "        cls.module = value\n"
                "class Holder(metaclass=Meta):\n"
                "    pass\n"
                "Holder(p)\n"
            ),
            "inherited-metaclass-call-alias-keyword": (
                "class Meta(type):\n"
                "    @classmethod\n"
                "    def __call__(meta, cls, value):\n"
                "        value.os.fork()\n"
                "class Base(metaclass=Meta):\n"
                "    pass\n"
                "class Holder(Base):\n"
                "    pass\n"
                "Constructor = Holder\n"
                "Constructor(value=p)\n"
            ),
            "static-metaclass-call-star": (
                "class Meta(type):\n"
                "    @staticmethod\n"
                "    def __call__(value):\n"
                "        value.os.fork()\n"
                "class Holder(metaclass=Meta):\n"
                "    pass\n"
                "Holder(*(p,))\n"
            ),
            "with-enter-return": (
                "class Context:\n"
                "    def __enter__(self):\n"
                "        return p\n"
                "with Context() as value:\n"
                "    value.os.fork()\n"
            ),
            "with-enter-destructuring-and-alias": (
                "class Context:\n"
                "    def __enter__(self):\n"
                "        return (p, p)\n"
                "manager = Context()\n"
                "with manager as (left, *rest):\n"
                "    rest[0].os.fork()\n"
            ),
            "with-enter-multiple-items": (
                "class Safe:\n"
                "    def __enter__(self):\n"
                "        return None\n"
                "class Context:\n"
                "    def __enter__(self):\n"
                "        return p\n"
                "with Safe() as left, Context() as right:\n"
                "    right.os.fork()\n"
            ),
            "async-with-enter-return": (
                "class Context:\n"
                "    async def __aenter__(self):\n"
                "        return p\n"
                "async def run():\n"
                "    async with Context() as value:\n"
                "        value.os.fork()\n"
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
            "metaclass-receiver-only": (
                "class Meta(type):\n"
                "    def __call__(cls, value):\n"
                "        cls.module = cls\n"
                "class Holder(metaclass=Meta):\n"
                "    pass\n"
                "Holder(p)\n"
            ),
            "metaclass-call-overrides-dangerous-init": (
                "class Meta(type):\n"
                "    def __call__(cls, value):\n"
                "        return None\n"
                "class Holder(metaclass=Meta):\n"
                "    def __init__(self, value):\n"
                "        self.module = value\n"
                "Holder(p)\n"
            ),
            "with-enter-safe-return": (
                "class Context:\n"
                "    def __enter__(self):\n"
                "        return None\n"
                "with Context() as value:\n"
                "    value.os.fork()\n"
            ),
            "with-nested-return-does-not-escape": (
                "class Context:\n"
                "    def __enter__(self):\n"
                "        def nested():\n"
                "            return p\n"
                "        return None\n"
                "with Context() as value:\n"
                "    value.os.fork()\n"
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

    def test_deserializer_exception_and_protocol_guards_are_flow_sensitive(self):
        deserializer_positives = (
            "import pickle\npickle.loads(blob)\n",
            "from pickle import load as decode\ndecode(stream)\n",
            (
                "import pickle as codec\n"
                "decode = codec.loads\n"
                "alias = decode\n"
                "alias(blob)\n"
            ),
            "import _pickle\n_pickle.loads(blob)\n",
            "import dill\ndill.load(stream)\n",
            "import cloudpickle\ncloudpickle.loads(blob)\n",
            "import joblib\njoblib.load(path)\n",
            "import pandas\npandas.read_pickle(path)\n",
            "import yaml\nyaml.unsafe_load(blob)\n",
            (
                "import shelve\n"
                "with shelve.open(path) as database:\n"
                "    payload = database['payload']\n"
            ),
            (
                "from shelve import open as open_database\n"
                "with open_database(path) as database:\n"
                "    payload = database['payload']\n"
            ),
            (
                "import shelve as storage\n"
                "open_database = storage.open\n"
                "alias = open_database\n"
                "with alias(path) as database:\n"
                "    payload = database['payload']\n"
            ),
            (
                "open_database = harmless\n"
                "if enabled:\n"
                "    from shelve import open as open_database\n"
                "open_database(path)\n"
            ),
            (
                "storage = harmless\n"
                "if enabled:\n"
                "    import shelve as storage\n"
                "storage.open(path)\n"
            ),
            "import pickle\npickle.Unpickler(stream).load()\n",
            (
                "import pickle\n"
                "decode = pickle.Unpickler(stream).load\n"
                "decode()\n"
            ),
            (
                "import pickle\n"
                "decode = harmless\n"
                "if enabled:\n"
                "    decode = pickle.loads\n"
                "decode(blob)\n"
            ),
            (
                "import pickle\n"
                "decode = pickle.loads\n"
                "if enabled:\n"
                "    decode = harmless\n"
                "decode(blob)\n"
            ),
        )
        for source in deserializer_positives:
            with self.subTest(executable_deserializer=source.strip()):
                self.assertTrue(
                    sensitive_module_reexports(ast.parse(source), {}),
                )

        deserializer_negatives = (
            "import json\njson.loads(blob)\n",
            "import pickle\npickle.dumps(blob)\n",
            "import example\nexample.loads(blob)\n",
            (
                "import pickle\n"
                "decode = pickle.loads\n"
                "decode = harmless\n"
                "decode(blob)\n"
            ),
            (
                "import pickle\n"
                "def run(pickle):\n"
                "    return pickle.loads(blob)\n"
            ),
            (
                "from pickle import loads as decode\n"
                "for decode in [harmless]:\n"
                "    decode(blob)\n"
            ),
            (
                "from pickle import loads as decode\n"
                "with context() as decode:\n"
                "    decode(blob)\n"
            ),
            (
                "from pickle import loads as decode\n"
                "try:\n"
                "    pass\n"
                "except Exception as decode:\n"
                "    decode(blob)\n"
            ),
            (
                "from pickle import loads as decode\n"
                "[decode(blob) for decode in [harmless]]\n"
            ),
            "import pickle\ndecode = pickle.loads\n",
            "import shelve\nreference = shelve.open\n",
            (
                "import shelve\n"
                "open_database = shelve.open\n"
                "open_database = harmless\n"
                "open_database(path)\n"
            ),
            (
                "import shelve\n"
                "def run(shelve):\n"
                "    return shelve.open(path)\n"
            ),
            "import example\nexample.open(path)\n",
            "open(path)\n",
        )
        for source in deserializer_negatives:
            with self.subTest(safe_deserializer_shape=source.strip()):
                self.assertFalse(
                    sensitive_module_reexports(ast.parse(source), {}),
                )

        prefix = "from shutil import fnmatch as p\n"
        exception_positives = (
            (
                "try:\n"
                "    raise RuntimeError(p)\n"
                "except RuntimeError as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "failure = RuntimeError(p)\n"
                "try:\n"
                "    raise failure\n"
                "except RuntimeError as error:\n"
                "    payload = error.args[0]\n"
                "    payload.os.fork()\n"
            ),
            (
                "try:\n"
                "    raise RuntimeError(None, p)\n"
                "except Exception as error:\n"
                "    error.args[1].os.fork()\n"
            ),
            (
                "try:\n"
                "    raise RuntimeError(p)\n"
                "except (ValueError, RuntimeError) as error:\n"
                "    alias = error\n"
                "    alias.args[0].os.fork()\n"
            ),
            (
                "failure = RuntimeError(p)\n"
                "if enabled:\n"
                "    failure = RuntimeError(None)\n"
                "try:\n"
                "    raise failure\n"
                "except RuntimeError as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "try:\n"
                "    raise (RuntimeError(p) if enabled else RuntimeError(None))\n"
                "except RuntimeError as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "class Failure(Exception):\n"
                "    pass\n"
                "try:\n"
                "    raise Failure(payload=p)\n"
                "except Failure as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Base:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "class Context(Base):\n"
                "    pass\n"
                "manager = Context()\n"
                "with manager:\n"
                "    failure = RuntimeError(p)\n"
                "    raise failure\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, *parts):\n"
                "        parts[1].args[0].os.fork()\n"
                "try:\n"
                "    with Context():\n"
                "        raise RuntimeError(p)\n"
                "except RuntimeError:\n"
                "    pass\n"
            ),
            (
                "class AsyncContext:\n"
                "    async def __aexit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "async def run():\n"
                "    async with AsyncContext():\n"
                "        raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError:\n"
                "        raise\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError as error:\n"
                "        raise error\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError as error:\n"
                "        alias = error\n"
                "        raise alias\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError as error:\n"
                "        raise (alias := error)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError as error:\n"
                "        alias = error\n"
                "        error = RuntimeError(None)\n"
                "        raise alias\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, *parts):\n"
                "        alias = parts\n"
                "        alias[1].args[0].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, *parts):\n"
                "        typ, error, traceback = parts\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, *rest):\n"
                "        alias = rest\n"
                "        alias[0].args[0].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Outer:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "class Inner:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        return False\n"
                "with Outer(), Inner():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Left:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "class Right:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        return True\n"
                "manager = Right()\n"
                "if enabled:\n"
                "    manager = external\n"
                "with Left(), manager:\n"
                "    raise RuntimeError(p)\n"
            ),
        )
        for body in exception_positives:
            with self.subTest(exception_payload=body.strip()):
                self.assertTrue(
                    sensitive_module_reexports(
                        ast.parse(prefix + body),
                        {"p": "shutil.fnmatch"},
                    )
                )

        exception_negatives = (
            (
                "try:\n"
                "    raise RuntimeError(p)\n"
                "except ValueError as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "failure = RuntimeError(None)\n"
                "if enabled:\n"
                "    failure = RuntimeError(p)\n"
                "failure = RuntimeError(None)\n"
                "try:\n"
                "    raise failure\n"
                "except RuntimeError as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "try:\n"
                "    raise RuntimeError('safe')\n"
                "except RuntimeError as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "try:\n"
                "    raise RuntimeError(None, p)\n"
                "except RuntimeError as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "try:\n"
                "    raise RuntimeError(p)\n"
                "except RuntimeError as error:\n"
                "    error = harmless\n"
                "    error.os.fork()\n"
            ),
            (
                "try:\n"
                "    raise RuntimeError(p)\n"
                "except RuntimeError:\n"
                "    pass\n"
                "except Exception as error:\n"
                "    error.args[0].os.fork()\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError('safe')\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        typ.os.fork()\n"
                "        traceback.os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError:\n"
                "        pass\n"
            ),
            (
                "class Context:\n"
                "    async def __aexit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "raise RuntimeError(p)\n"
            ),
            (
                "class Failure(Exception):\n"
                "    pass\n"
                "class Child(Failure):\n"
                "    pass\n"
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise Child(p)\n"
                "    except Failure:\n"
                "        pass\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, *parts):\n"
                "        parts[0].os.fork()\n"
                "        parts[2].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, *rest):\n"
                "        rest[1].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Outer:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "class Inner:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        return True\n"
                "with Outer(), Inner():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "manager = Context()\n"
                "manager = external\n"
                "with manager:\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error = typ\n"
                "        error.os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError as error:\n"
                "        error = RuntimeError(None)\n"
                "        raise error\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError as error:\n"
                "        alias = error\n"
                "        alias = RuntimeError(None)\n"
                "        raise alias\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        raise RuntimeError(p)\n"
                "    except RuntimeError as error:\n"
                "        error = RuntimeError(None)\n"
                "        alias = error\n"
                "        raise alias\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, *parts):\n"
                "        alias = parts\n"
                "        alias[0].os.fork()\n"
                "        alias[2].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, *parts):\n"
                "        typ, error, traceback = parts\n"
                "        typ.os.fork()\n"
                "        traceback.os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, *parts):\n"
                "        alias = parts\n"
                "        alias = (None, None, None)\n"
                "        alias[1].os.fork()\n"
                "with Context():\n"
                "    raise RuntimeError(p)\n"
            ),
            (
                "class Outer:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "class Inner:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        return True\n"
                "with Outer():\n"
                "    with Inner():\n"
                "        raise RuntimeError(p)\n"
            ),
            (
                "class Context:\n"
                "    def __exit__(self, typ, error, traceback):\n"
                "        error.args[0].os.fork()\n"
                "with Context():\n"
                "    try:\n"
                "        try:\n"
                "            raise RuntimeError(p)\n"
                "        except RuntimeError as error:\n"
                "            alias = error\n"
                "            raise alias\n"
                "    except RuntimeError:\n"
                "        pass\n"
            ),
        )
        for body in exception_negatives:
            with self.subTest(safe_exception_flow=body.strip()):
                self.assertFalse(
                    sensitive_module_reexports(
                        ast.parse(prefix + body),
                        {"p": "shutil.fnmatch"},
                    )
                )

        protocol_positives = (
            (
                "class Runner:\n"
                "    def __eq__(self, value):\n"
                "        value.os.fork()\n"
                "Runner() == p\n"
            ),
            (
                "class Base:\n"
                "    @staticmethod\n"
                "    def __lt__(value):\n"
                "        value.os.fork()\n"
                "class Runner(Base):\n"
                "    pass\n"
                "Runner() < p\n"
            ),
            (
                "class Runner:\n"
                "    def __add__(self, value):\n"
                "        value.os.fork()\n"
                "Runner() + p\n"
            ),
            (
                "class Runner:\n"
                "    def __radd__(self, value):\n"
                "        value.os.fork()\n"
                "p + Runner()\n"
            ),
            (
                "class Runner:\n"
                "    def __getitem__(self, key):\n"
                "        key.os.fork()\n"
                "Runner()[p]\n"
            ),
            (
                "class Runner:\n"
                "    def __setitem__(self, key, value):\n"
                "        value.os.fork()\n"
                "Runner()[None] = p\n"
            ),
            (
                "class Runner:\n"
                "    def __contains__(self, value):\n"
                "        value.os.fork()\n"
                "p in Runner()\n"
            ),
            (
                "class Base:\n"
                "    def __iter__(self):\n"
                "        yield p\n"
                "class Runner(Base):\n"
                "    pass\n"
                "for value in Runner():\n"
                "    value.os.fork()\n"
            ),
            "external[p] = None\n",
            (
                "class Runner:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "(Runner() if enabled else external)[None] = p\n"
            ),
            (
                "class Runner:\n"
                "    pass\n"
                "Runner()[None] = p\n"
            ),
            (
                "class Runner:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "[Runner()[None]] = [p]\n"
            ),
            (
                "class Runner:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "Runner()[None] += p\n"
            ),
        )
        for body in protocol_positives:
            with self.subTest(implicit_protocol=body.strip()):
                self.assertTrue(
                    sensitive_module_reexports(
                        ast.parse(prefix + body),
                        {"p": "shutil.fnmatch"},
                    )
                )

        protocol_negatives = (
            (
                "class Runner:\n"
                "    def __eq__(self, value):\n"
                "        return value\n"
                "Runner() == p\n"
            ),
            (
                "class Runner:\n"
                "    def __radd__(self, value):\n"
                "        self.os.fork()\n"
                "p + Runner()\n"
            ),
            (
                "class Runner:\n"
                "    def __getitem__(self, key):\n"
                "        key.os.fork()\n"
                "Runner()[None]\n"
            ),
            (
                "class Runner:\n"
                "    def __iter__(self):\n"
                "        yield None\n"
                "for value in Runner():\n"
                "    value.os.fork()\n"
            ),
            (
                "class Runner:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "Runner()[None] = p\n"
            ),
            (
                "class Runner:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "runner = Runner()\n"
                "runner[None] = p\n"
            ),
            (
                "class A:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "class B:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "(A() if enabled else B())[None] = p\n"
            ),
            (
                "class Base:\n"
                "    def __setitem__(self, key, value):\n"
                "        return None\n"
                "class Runner(Base):\n"
                "    pass\n"
                "Runner()[None] = p\n"
            ),
        )
        for body in protocol_negatives:
            with self.subTest(safe_protocol_operand=body.strip()):
                self.assertFalse(
                    sensitive_module_reexports(
                        ast.parse(prefix + body),
                        {"p": "shutil.fnmatch"},
                    )
                )

    def test_execute_integrity_guard_rejects_shadows_and_relocations(self):
        valid_source = (
            "import json\n"
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
            "            manifests = existing(day)\n"
            "            manifest = {\"replay_run_id\": \"known\", "
            "\"dataset_digest\": \"d\", \"configuration_digest\": \"c\", "
            "\"frame_count\": 1}\n"
            "            run_id = str(manifest[\"replay_run_id\"]) if manifest "
            "else f\"h2d-{day.isoformat()}\"\n"
            "            dataset_digest = manifest.get(\"dataset_digest\")\n"
            "            configuration_digest = "
            "manifest.get(\"configuration_digest\")\n"
            "            frame_count = manifest.get(\"frame_count\")\n"
            "            h1 = run_json([], \"H1\")\n"
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
            "execute-entry-return-before-dispatch": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    return {}\n    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-exit-before-dispatch": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    sys.exit(0)\n    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-unbounded-while": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    while True:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-unknown-while": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    while ready:\n"
                    "        work()\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-unknown-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in stream:\n"
                    "        work(ignored)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-starred-literal-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in [*stream]:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-unpacked-dict-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in {**mapping}:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-mixed-starred-literal-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in [*(1, 2), *stream]:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-mixed-unpacked-dict-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in {**{'a': 1}, **mapping}:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-generator-starred-literal-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in "
                    "[*(item for item in iter(int, 1))]:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-nested-unknown-starred-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in [[*stream]]:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-starred-nested-unknown-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in [*(1, [*stream])]:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-dict-value-unknown-starred-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in {'key': [*stream]}:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-invalid-finite-dict-unpack-for": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    for ignored in {**[]}:\n"
                    "        pass\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-generator-expression": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = any(False for ignored in iter(int, 1))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-generator-unknown-first-source": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    deferred = (item for item in stream)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-list-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(iter(int, 1))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-tuple-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = tuple(iter(int, 1))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-set-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = set(iter(int, 1))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-frozenset-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = frozenset(iter(int, 1))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-sorted-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = sorted(iter(int, 1), key=None, reverse=False)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-sum-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = sum(iter(int, 1), start=0)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-min-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = min(iter(int, 1), key=None)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-max-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = max(iter(int, 1), default=None)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-dict-unbounded-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = dict(iter(int, 1), safe=None)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-sorted-static-star-unbounded": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = sorted(*(stream,), **{'reverse': False})\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-dict-unsafe-keyword-value": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = dict(payload=[*stream])\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-dict-unsafe-mapped-keyword-value": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = dict(**{'payload': [*stream]})\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-sorted-unsafe-key": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = sorted([1], key=[*stream])\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-min-multiarg-unsafe-key": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = min(1, 2, key=[*stream])\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-min-invalid-unsafe-argument": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = min([*stream], other)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-tuple-invalid-unsafe-argument": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = tuple([*stream], bad=1)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-list-invalid-unsafe-argument": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list([*stream], other)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-dict-invalid-unsafe-argument": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = dict([*stream], other)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-sum-invalid-unsafe-argument": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = sum([*stream], 0, 1)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-list-unknown-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(stream)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-any-unknown-iterator": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = any(stream)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-shadowed-days-consumer": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [list(days) for days in [stream]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-shadowed-days-iter-consumer": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [list(iter(days)) for days in [stream]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-list-unbounded-empty-expansions": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(iter(int, 1), *(), **{})\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-list-unbounded-static-star": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(*(iter(int, 1),))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-comprehension-list-body": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [list(stream) for ignored in [1]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-rebound-days-consumer": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    days = stream\n"
                    "    consumed = list(days)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-list-unknown-star-expansion": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(iter(int, 1), *unknown)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-list-unknown-mapping-expansion": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(iter(int, 1), **unknown)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-dead-module-list-shadow": (
                "if False:\n"
                "    list = lambda values: values\n"
                + valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(iter(int, 1))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-killed-module-list-shadow": (
                "list = lambda values: values\n"
                "del list\n"
                + valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(iter(int, 1))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-comprehension-any-filter": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [ignored for ignored in [1] "
                    "if any(item for item in stream)]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-comprehension-all-filter": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [ignored for ignored in [1] "
                    "if all(item for item in stream)]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-all-empty-keeps-body-live": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [[*stream] for ignored in [1] "
                    "if all(item for item in [])]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-shadowed-any-empty-not-folded": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    any = lambda values: True\n"
                    "    consumed = [[*stream] for ignored in [1] "
                    "if any(item for item in [])]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-negated-any-empty-keeps-body-live": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [[*stream] for ignored in [1] "
                    "if not any(item for item in [])]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-any-empty-or-evaluates-unsafe-rhs": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [ignored for ignored in [1] "
                    "if any(item for item in []) or [*stream]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-all-empty-and-evaluates-comprehension": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = all(item for item in []) and "
                    "[item for item in stream]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-consumed-generator-starred-body": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list([*stream] for ignored in [1])\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-consumed-generator-later-source": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(item for ignored in [1] "
                    "for item in stream)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-consumed-generator-filter": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = list(ignored for ignored in [1] "
                    "if any(item for item in stream))\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-unbounded-list-comprehension": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [ignored for ignored in stream]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-comprehension-starred-body": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = [[*stream] for ignored in [1]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-dict-comprehension-starred-value": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = "
                    "{ignored: [*stream] for ignored in [1]}\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-comprehension-nested-starred-body": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = "
                    "[consume([*stream]) for ignored in [1]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-comprehension-call-starred-body": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = "
                    "[consume(*stream) for ignored in [1]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-entry-eager-comprehension-call-dict-unpack": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    consumed = "
                    "[consume(**mapping) for ignored in [1]]\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-default-exit-with-future-annotations": (
                "from __future__ import annotations\n"
                + valid_source.replace(
                    "    for day in days:\n",
                    "    def helper(value=sys.exit(1)):\n"
                    "        return value\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-async-default-exit-with-future-annotations": (
                "from __future__ import annotations\n"
                + valid_source.replace(
                    "    for day in days:\n",
                    "    async def helper(value=sys.exit(1)):\n"
                    "        return value\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-default-exit-alias": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    halt = sys.exit\n"
                    "    def helper(value=halt(1)):\n"
                    "        return value\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-destructured-exit-alias": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    halt, other = (sys.exit, None)\n"
                    "    halt(1)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-conditionally-killed-exit-alias": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    halt = sys.exit\n"
                    "    if enabled:\n"
                    "        halt = safe\n"
                    "    halt(1)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "execute-loop-killed-exit-alias": (
                valid_source.replace(
                    "    for day in days:\n",
                    "    halt = sys.exit\n"
                    "    for _ in ():\n"
                    "        halt = safe\n"
                    "    halt(1)\n"
                    "    for day in days:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "day-prefix-return-before-dispatch": (
                valid_source.replace(
                    "            manifests = existing(day)\n",
                    "            return {}\n"
                    "            manifests = existing(day)\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "day-prefix-assert-before-dispatch": (
                valid_source.replace(
                    "            manifests = existing(day)\n",
                    "            assert ready\n"
                    "            manifests = existing(day)\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "day-prefix-explicit-exit-before-dispatch": (
                valid_source.replace(
                    "            manifests = existing(day)\n",
                    "            parser.exit(1)\n"
                    "            manifests = existing(day)\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "day-prefix-unbounded-while": (
                valid_source.replace(
                    "            manifests = existing(day)\n",
                    "            while True:\n"
                    "                pass\n"
                    "            manifests = existing(day)\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "day-loop-break-before-dispatch": (
                valid_source.replace(
                    "        try:\n",
                    "        break\n        try:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "day-loop-continue-before-dispatch": (
                valid_source.replace(
                    "        try:\n",
                    "        continue\n        try:\n",
                    1,
                ),
                "execute-pre-dispatch-termination",
            ),
            "existing-rebinding": (
                valid_source.replace(
                    "    execute_count = len(days)\n",
                    "    existing = None\n"
                    "    execute_count = len(days)\n",
                    1,
                ),
                "execute-existing-binding",
            ),
            "existing-call-replacement": (
                valid_source.replace(
                    "            manifests = existing(day)\n",
                    "            manifests = ()\n",
                    1,
                ),
                "execute-existing-call",
            ),
            "nested-nonlocal-existing": (
                valid_source.replace(
                    "    execute_count = len(days)\n",
                    "    def mutate():\n"
                    "        nonlocal existing\n"
                    "        existing = None\n"
                    "    execute_count = len(days)\n",
                    1,
                ),
                "execute-existing-binding",
            ),
            "nested-nonlocal-lineage": (
                valid_source.replace(
                    "            dataset_digest = manifest.get",
                    "            def mutate():\n"
                    "                nonlocal run_id\n"
                    "                run_id = None\n"
                    "            dataset_digest = manifest.get",
                    1,
                ),
                "execute-lineage-binding",
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
            "module-print-binding": (
                "print = sink\n" + valid_source,
                "main-output-call-target",
            ),
            "main-print-binding": (
                valid_source.replace(
                    exact_call,
                    "    print = sink\n" + exact_call,
                    1,
                ),
                "main-output-call-target",
            ),
            "json-import-alias": (
                valid_source.replace("import json\n", "import json as codec\n", 1),
                "main-output-call-target",
            ),
            "module-json-rebinding": (
                valid_source.replace(
                    "def _run_json",
                    "json = codec\ndef _run_json",
                    1,
                ),
                "main-output-call-target",
            ),
            "module-json-dumps-store": (
                valid_source.replace(
                    "def _run_json",
                    "json.dumps = serializer\ndef _run_json",
                    1,
                ),
                "main-output-call-target",
            ),
            "module-json-dumps-delete": (
                valid_source.replace(
                    "def _run_json",
                    "del json.dumps\ndef _run_json",
                    1,
                ),
                "main-output-call-target",
            ),
            "module-json-dumps-augmented-store": (
                valid_source.replace(
                    "def _run_json",
                    "json.dumps += serializer\ndef _run_json",
                    1,
                ),
                "main-output-call-target",
            ),
            "module-json-alias-dumps-store": (
                valid_source.replace(
                    "def _run_json",
                    "codec = json\ncodec.dumps = serializer\ndef _run_json",
                    1,
                ),
                "main-output-call-target",
            ),
            "module-json-alias-dumps-delete": (
                valid_source.replace(
                    "def _run_json",
                    "codec = json\ndel codec.dumps\ndef _run_json",
                    1,
                ),
                "main-output-call-target",
            ),
            "nested-json-alias-dumps-store": (
                valid_source.replace(
                    "def main(argv=None):",
                    "def mutate_json():\n"
                    "    codec = json\n"
                    "    codec.dumps = serializer\n"
                    "def main(argv=None):",
                    1,
                ),
                "main-output-call-target",
            ),
            "nested-json-destructured-alias-delete": (
                valid_source.replace(
                    "def main(argv=None):",
                    "def mutate_json():\n"
                    "    codec, other = json, None\n"
                    "    del codec.dumps\n"
                    "def main(argv=None):",
                    1,
                ),
                "main-output-call-target",
            ),
            "nested-json-conditional-alias-store": (
                valid_source.replace(
                    "def main(argv=None):",
                    "def mutate_json():\n"
                    "    codec = json\n"
                    "    if enabled:\n"
                    "        codec = FakeJson()\n"
                    "    codec.dumps = serializer\n"
                    "def main(argv=None):",
                    1,
                ),
                "main-output-call-target",
            ),
            "nested-json-default-alias-store": (
                valid_source.replace(
                    "def main(argv=None):",
                    "def mutate_json(codec=json):\n"
                    "    codec.dumps = serializer\n"
                    "def main(argv=None):",
                    1,
                ),
                "main-output-call-target",
            ),
            "nested-json-augassign-alias-store": (
                valid_source.replace(
                    "def main(argv=None):",
                    "def mutate_json():\n"
                    "    codec = json\n"
                    "    codec += Wrapper()\n"
                    "    codec.dumps = serializer\n"
                    "def main(argv=None):",
                    1,
                ),
                "main-output-call-target",
            ),
            "nested-global-output-targets": (
                valid_source.replace(
                    exact_call,
                    "    def mutate_targets():\n"
                    "        global print, json\n"
                    "        print = json = None\n"
                    + exact_call,
                    1,
                ),
                "main-output-call-target",
            ),
            "nested-nonlocal-output": (
                valid_source.replace(
                    "    print(json.dumps(output, sort_keys=True, ",
                    "    def mutate_output():\n"
                    "        nonlocal output\n"
                    "        output = {}\n"
                    "    print(json.dumps(output, sort_keys=True, ",
                    1,
                ),
                "main-output-binding",
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
            "    def nested_output_helpers():\n"
            "        print = json = None\n"
            "        return print, json\n",
            "    def shadowed_json_module(json):\n"
            "        json.dumps = None\n"
            "        del json.dumps\n",
            "    def locally_imported_json_shadow():\n"
            "        import local_json as json\n"
            "        json.dumps = None\n",
            "    def killed_local_json_import():\n"
            "        import json\n"
            "        json = FakeJson()\n"
            "        json.dumps = None\n",
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
            "    def nested_bindings(run_json, existing, day, run_id, dataset_digest, "
            "configuration_digest, frame_count):\n"
            "        return None\n"
            "    shadows = [None for run_json in () for existing in () for day in () "
            "for run_id in () for dataset_digest in () "
            "for configuration_digest in () for frame_count in ()]\n"
            "    return {\"count\": execute_count, ",
            1,
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(safe_execute_shadows)),
            "nested and comprehension-target shadows must remain local",
        )

        safe_json_alias_rebind = valid_source.replace(
            "def _run_json",
            "codec = json\ncodec = FakeJson()\ncodec.dumps = None\n"
            "unrelated.dumps = None\ndef _run_json",
            1,
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(safe_json_alias_rebind)),
            "a killed json alias and unrelated dumps attribute must stay safe",
        )
        safe_nested_json_aliases = valid_source.replace(
            "def main(argv=None):",
            "def safe_json_aliases():\n"
            "    codec = json\n"
            "    codec = FakeJson()\n"
            "    codec.dumps = None\n"
            "def safe_fake_json():\n"
            "    json = FakeJson()\n"
            "    codec = json\n"
            "    codec.dumps = None\n"
            "def main(argv=None):",
            1,
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(safe_nested_json_aliases)),
            "killed and locally fake nested json aliases must stay safe",
        )

        for safe_prefix in (
            (
                "    def uncalled():\n"
                "        while True:\n"
                "            pass\n"
                "        return any(False for item in iter(int, 1))\n"
                "    for day in days:\n"
            ),
            (
                "    if False:\n"
                "        while True:\n"
                "            pass\n"
                "    for day in days:\n"
            ),
            (
                "    while True:\n"
                "        break\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in [1, 2]:\n"
                "        pass\n"
                "    finite = any(False for ignored in ())\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in [*(1, 2)]:\n"
                "        pass\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in (*(1, 2),):\n"
                "        pass\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in {*(1, 2)}:\n"
                "        pass\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in {**{'a': 1}}:\n"
                "        pass\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in [[*(1, 2)]]:\n"
                "        pass\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in [*(1, [*(2, 3)])]:\n"
                "        pass\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in {'key': [*(1, 2)]}:\n"
                "        pass\n"
                "    for day in days:\n"
            ),
            (
                "    for ignored in [*()]:\n"
                "        while True:\n"
                "            pass\n"
                "    for day in days:\n"
            ),
            (
                "    finite = [[*(1, 2)] for ignored in [1]]\n"
                "    finite_dict = "
                "{ignored: [*(1, 2)] for ignored in [1]}\n"
                "    for day in days:\n"
            ),
            (
                "    dead = [[*stream] for ignored in []]\n"
                "    filtered = "
                "{ignored: [*stream] for ignored in [1] if False}\n"
                "    for day in days:\n"
            ),
            (
                "    dead = "
                "[[*stream] for ignored in [] for item in stream]\n"
                "    deferred = ([*stream] for ignored in [1])\n"
                "    for day in days:\n"
            ),
            (
                "    dead_nested = "
                "[[[*stream] for item in [1]] for ignored in []]\n"
                "    dead_unbounded = "
                "[[item for item in stream] for ignored in []]\n"
                "    for day in days:\n"
            ),
            (
                "    deferred_nested = "
                "([[*stream] for item in [1]] for ignored in [1])\n"
                "    deferred_unbounded = "
                "([item for item in stream] for ignored in [1])\n"
                "    for day in days:\n"
            ),
            (
                "    deferred_body = ([*stream] for ignored in [1])\n"
                "    deferred_later = "
                "(item for ignored in [1] for item in stream)\n"
                "    deferred_filter = "
                "(ignored for ignored in [1] "
                "if any(item for item in stream))\n"
                "    for day in days:\n"
            ),
            (
                "    consumed_empty = "
                "list([*stream] for ignored in [])\n"
                "    consumed_filtered = "
                "list([*stream] for ignored in [1] if False)\n"
                "    consumed_dead_later = "
                "list(item for ignored in [] for item in stream)\n"
                "    for day in days:\n"
            ),
            (
                "    eager_empty_any = "
                "[ignored for ignored in [1] if any(item for item in [])]\n"
                "    eager_finite_all = "
                "[ignored for ignored in [1] if all(item for item in [1])]\n"
                "    drained_dead_any = "
                "list(ignored for ignored in [1] "
                "if any(item for item in [] for later in stream))\n"
                "    for day in days:\n"
            ),
            (
                "    eager_dead_any_body = "
                "[[*stream] for ignored in [1] "
                "if any(item for item in [])]\n"
                "    drained_dead_any_body = "
                "list([*stream] for ignored in [1] "
                "if any(item for item in []))\n"
                "    for day in days:\n"
            ),
            (
                "    dead_composed_any = "
                "[[*stream] for ignored in [1] "
                "if any(item for item in []) and ready]\n"
                "    dead_any_choice = "
                "[[*stream] for ignored in [1] "
                "if ([*stream] if any(item for item in []) else [])]\n"
                "    dead_negated_all = "
                "[[*stream] for ignored in [1] "
                "if not all(item for item in [])]\n"
                "    all_short_circuit = "
                "[ignored for ignored in [1] "
                "if all(item for item in []) or [*stream]]\n"
                "    for day in days:\n"
            ),
            (
                "    dead_outer_any_choice = "
                "([item for item in stream] "
                "if any(value for value in []) else [])\n"
                "    dead_outer_any_and = "
                "(any(value for value in []) and "
                "[item for item in stream])\n"
                "    dead_outer_all_or = "
                "(all(value for value in []) or "
                "[item for item in stream])\n"
                "    dead_outer_not_all = "
                "([item for item in stream] "
                "if not all(value for value in []) else [])\n"
                "    for day in days:\n"
            ),
            (
                "    any = lambda value: False\n"
                "    shadowed_any = "
                "[ignored for ignored in [1] "
                "if any(item for seed in [1] for item in stream)]\n"
                "    for day in days:\n"
            ),
            (
                "    list = lambda value: value\n"
                "    shadowed_consumer = "
                "list([*stream] for ignored in [1])\n"
                "    shadowed_iterator_consumer = list(iter(int, 1))\n"
                "    for day in days:\n"
            ),
            (
                "    tuple = set = frozenset = sorted = sum = "
                "min = max = dict = lambda *values, **options: values\n"
                "    shadowed_tuple = tuple(stream)\n"
                "    shadowed_set = set(stream)\n"
                "    shadowed_frozenset = frozenset(stream)\n"
                "    shadowed_sorted = sorted(stream)\n"
                "    shadowed_sum = sum(stream)\n"
                "    shadowed_min = min(stream)\n"
                "    shadowed_max = max(stream)\n"
                "    shadowed_dict = dict(stream)\n"
                "    for day in days:\n"
            ),
            (
                "    finite_list = list([1, 2])\n"
                "    finite_any = any([])\n"
                "    protected_days = list(days)\n"
                "    finite_iter = list(iter([1, 2]))\n"
                "    protected_days_iter = list(iter(days))\n"
                "    finite_static_star = list(*([1, 2],), **{})\n"
                "    recursively_empty_expansions = "
                "list(iter([1, 2]), *[*()], **{**{}})\n"
                "    dead_consumer = False and list(stream)\n"
                "    for day in days:\n"
            ),
            (
                "    finite_tuple = tuple([1, 2])\n"
                "    finite_set = set([1, 2])\n"
                "    finite_frozenset = frozenset([1, 2])\n"
                "    finite_sorted = sorted([2, 1], **{'reverse': False})\n"
                "    finite_sum = sum([1, 2], start=0)\n"
                "    finite_min = min([1, 2], key=None)\n"
                "    finite_max = max([1, 2], default=None)\n"
                "    finite_dict = dict([('a', 1)], safe=2)\n"
                "    protected_tuple = tuple(days)\n"
                "    multi_min_is_data = min(stream, harmless)\n"
                "    multi_max_is_data = max(stream, harmless)\n"
                "    dict_keyword_value_is_data = dict(values=stream)\n"
                "    finite_empty_dict_star = tuple(*{})\n"
                "    finite_empty_string_star = tuple(*'')\n"
                "    finite_dict_key_star = tuple(*{'x': 1})\n"
                "    finite_dict_consumer_star = dict(*{'x': 1})\n"
                "    duplicate_sorted_key = "
                "sorted(iter(int, 1), key=None, **{'key': None})\n"
                "    duplicate_dict_key = "
                "dict(iter(int, 1), a=1, **{'a': 2})\n"
                "    nonstring_sorted_keyword = "
                "sorted(iter(int, 1), **{1: 2})\n"
                "    nonstring_dict_keyword = dict(**{1: 2})\n"
                "    for day in days:\n"
            ),
            (
                "    bounded_star_all = all(*days)\n"
                "    bounded_star_any = any(*days)\n"
                "    bounded_star_tuple = tuple(*days)\n"
                "    bounded_star_list = list(*days)\n"
                "    bounded_star_set = set(*days)\n"
                "    bounded_star_frozenset = frozenset(*days)\n"
                "    bounded_star_sorted = sorted(*days)\n"
                "    bounded_star_sum = sum(*days)\n"
                "    bounded_star_min = min(*days)\n"
                "    bounded_star_max = max(*days)\n"
                "    bounded_star_dict = dict(*days)\n"
                "    bounded_iter_star = tuple(*iter(days))\n"
                "    bounded_nested_star = list(*[*days])\n"
                "    for day in days:\n"
            ),
            (
                "    deferred_consumer_body = "
                "(list(stream) for ignored in [1])\n"
                "    if any(item for item in []):\n"
                "        dead_folded_consumer = list(stream)\n"
                "    while any(item for item in []):\n"
                "        dead_folded_loop_consumer = list(stream)\n"
                "    for day in days:\n"
            ),
            (
                "    class SafeConsumer:\n"
                "        list = lambda values: values\n"
                "        value = list(stream)\n"
                "    for day in days:\n"
            ),
            (
                "    target_shadowed_consumer = "
                "[list([*stream] for ignored in [1]) "
                "for list in [lambda value: value]]\n"
                "    invalid_consumer_shape = "
                "list(([*stream] for ignored in [1]), unexpected=True)\n"
                "    for day in days:\n"
            ),
            (
                "    safe_call_unpacks = "
                "[consume(*(1, 2), **{'key': 1}) for ignored in [1]]\n"
                "    dead_choice = "
                "[([*stream] if False else []) for ignored in [1]]\n"
                "    dead_bool = "
                "[(False and [*stream]) for ignored in [1]]\n"
                "    for day in days:\n"
            ),
            (
                "    dead_nested_choice = "
                "[([item for item in stream] if False else []) "
                "for ignored in [1]]\n"
                "    dead_nested_bool = "
                "[(False and [item for item in stream]) "
                "for ignored in [1]]\n"
                "    for day in days:\n"
            ),
            (
                "    dead_later_generator = "
                "[item for ignored in [] "
                "for item in [value for value in stream]]\n"
                "    filtered_later_generator = "
                "[item for ignored in [1] if False "
                "for item in [value for value in stream]]\n"
                "    for day in days:\n"
            ),
            (
                "    filtered_later_condition = "
                "[ignored for ignored in [1] if False "
                "if any(value for value in stream)]\n"
                "    for day in days:\n"
            ),
            (
                "    dead_outer_choice = "
                "([item for item in stream] if False else [])\n"
                "    dead_outer_and = "
                "(False and [item for item in stream])\n"
                "    dead_outer_or = "
                "(True or [item for item in stream])\n"
                "    for day in days:\n"
            ),
            (
                "    for day in days:\n"
                "        for ignored in ():\n"
                "            break\n"
            ),
        ):
            with self.subTest(safe_execute_prefix=safe_prefix.strip()):
                self.assertFalse(
                    execute_integrity_violations(ast.parse(
                        valid_source.replace(
                            "    for day in days:\n",
                            safe_prefix,
                            1,
                        )
                    )),
                    "uncalled returns and inner-loop breaks cannot skip dispatch",
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
        safe_deferred_execute_annotation = (
            "from __future__ import annotations\n"
            + valid_source.replace(
                "    for day in days:\n",
                "    def annotated(value: sys.exit(1)):\n"
                "        sys.exit(1)\n"
                "    for day in days:\n",
                1,
            )
        )
        self.assertFalse(
            execute_integrity_violations(
                ast.parse(safe_deferred_execute_annotation)
            ),
            "deferred annotations and uncalled nested bodies do not execute",
        )

        safe_killed_exit_alias = valid_source.replace(
            "    for day in days:\n",
            "    halt = sys.exit\n"
            "    halt = safe\n"
            "    def helper(value=halt(1)):\n"
            "        return value\n"
            "    for day in days:\n",
            1,
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(safe_killed_exit_alias)),
            "a killed exit alias must not poison a later default",
        )
        safe_direct_exit_alias_kill = valid_source.replace(
            "    for day in days:\n",
            "    halt = sys.exit\n"
            "    halt = safe\n"
            "    halt(1)\n"
            "    for day in days:\n",
            1,
        )
        self.assertFalse(
            execute_integrity_violations(ast.parse(safe_direct_exit_alias_kill)),
            "an unconditional safe rebind must kill an earlier exit alias",
        )

    def test_h2c_score_receipt_guard_and_success_tail_are_exact(self):
        source = BATCH.read_text(encoding="utf-8")
        self.assertFalse(
            h2c_score_receipt_suffix_violations(ast.parse(source)),
        )
        guard_source = (
            "            if (len(scoring.get(\"metrics\", ())) != 72 or\n"
            "                    scoring.get(\"forecast_count\") != expected_forecasts or\n"
            "                    scoring.get(\"dataset_digest\") != dataset_digest or\n"
            "                    scoring.get(\"configuration_digest\") != configuration_digest):\n"
            "                raise StageFailure(\"H2C_SCORE\", \"SCORING_RECEIPT_MISMATCH\", scoring)\n"
        )
        self.assertIn(guard_source, source)
        score_dispatch_source = (
            "            scoring = run_json([py, \"-m\", "
            "\"quant.historical_outcomes\", \"score\", run_id], \"H2C_SCORE\")\n"
        )
        self.assertIn(score_dispatch_source, source)
        day_loop_source = "    for day in days:\n"
        known_source = "            known = bool(manifests)\n"
        manifest_source = (
            "            manifest = manifests[0] if known else None\n"
        )
        self.assertIn(day_loop_source, source)
        self.assertIn(known_source, source)
        self.assertIn(manifest_source, source)
        mutations = {
            "deleted-guard": source.replace(guard_source, "", 1),
            "weakened-metric-count": source.replace(
                "len(scoring.get(\"metrics\", ())) != 72",
                "len(scoring.get(\"metrics\", ())) != 71",
                1,
            ),
            "changed-failure-reason": source.replace(
                "\"SCORING_RECEIPT_MISMATCH\", scoring",
                "\"SCORING_MISMATCH\", scoring",
                1,
            ),
            "state-before-guard": source.replace(
                guard_source,
                "            state = \"COMPLETED\"\n" + guard_source,
                1,
            ),
            "duplicate-scoring-binding": source.replace(
                guard_source,
                "            scoring = dict(scoring)\n" + guard_source,
                1,
            ),
            "emission-before-guard": source.replace(
                guard_source,
                "            receipt[\"sessions\"].append(item)\n" + guard_source,
                1,
            ),
            "pre-score-state-binding": source.replace(
                score_dispatch_source,
                "            state = \"COMPLETED\"\n" + score_dispatch_source,
                1,
            ),
            "pre-score-completed-append": source.replace(
                score_dispatch_source,
                "            receipt[\"completed\"].append(day.isoformat())\n"
                + score_dispatch_source,
                1,
            ),
            "pre-score-success-alias": source.replace(
                score_dispatch_source,
                "            success = receipt[\"skipped\"]\n"
                "            success.append(day.isoformat())\n"
                + score_dispatch_source,
                1,
            ),
            "pre-score-item-state-subscript": source.replace(
                score_dispatch_source,
                "            item[\"state\"] = \"SKIPPED_VERIFIED\"\n"
                + score_dispatch_source,
                1,
            ),
            "pre-score-item-state-mapping": source.replace(
                score_dispatch_source,
                "            item.update({\"state\": \"COMPLETED\"})\n"
                + score_dispatch_source,
                1,
            ),
            "pre-score-extra-session": source.replace(
                score_dispatch_source,
                "            receipt[\"sessions\"].append(item)\n"
                + score_dispatch_source,
                1,
            ),
            "failure-handler-state-change": source.replace(
                "item.update(state=\"FAILED\", failed_stage=stage, reason=reason,",
                "item.update(state=\"COMPLETED\", failed_stage=stage, reason=reason,",
                1,
            ),
            "module-len-shadow": source.replace(
                "import argparse\n",
                "import argparse\nlen = lambda value: 72\n",
                1,
            ),
            "module-len-import": source.replace(
                "import argparse\n",
                "import argparse\nfrom builtins import len\n",
                1,
            ),
            "module-len-import-then-rebind": source.replace(
                "import argparse\n",
                "import argparse\nfrom builtins import len\n"
                "len = lambda value: 72\n",
                1,
            ),
            "execute-len-shadow": source.replace(
                day_loop_source,
                "    len = lambda value: 72\n" + day_loop_source,
                1,
            ),
            "execute-len-parameter": source.replace(
                "def execute(days: tuple[date, ...], *, continue_on_failure: bool,\n",
                "def execute(days: tuple[date, ...], *, len=len, "
                "continue_on_failure: bool,\n",
                1,
            ),
            "execute-len-import": source.replace(
                day_loop_source,
                "    from builtins import len\n" + day_loop_source,
                1,
            ),
            "execute-len-match-capture": source.replace(
                day_loop_source,
                "    match object():\n"
                "        case len:\n"
                "            pass\n"
                + day_loop_source,
                1,
            ),
            "execute-len-star-match-capture": source.replace(
                day_loop_source,
                "    match object():\n"
                "        case [*len]:\n"
                "            pass\n"
                + day_loop_source,
                1,
            ),
            "execute-len-mapping-match-capture": source.replace(
                day_loop_source,
                "    match object():\n"
                "        case {**len}:\n"
                "            pass\n"
                + day_loop_source,
                1,
            ),
            "execute-len-comprehension-walrus": source.replace(
                day_loop_source,
                "    [(len := replacement) for _ in ()]\n" + day_loop_source,
                1,
            ),
            "execute-len-type-parameter": source.replace(
                "def execute(days: tuple[date, ...], *, continue_on_failure: bool,\n",
                "def execute[len](days: tuple[date, ...], *, "
                "continue_on_failure: bool,\n",
                1,
            ),
            "execute-len-type-var-tuple": source.replace(
                "def execute(days: tuple[date, ...], *, continue_on_failure: bool,\n",
                "def execute[*len](days: tuple[date, ...], *, "
                "continue_on_failure: bool,\n",
                1,
            ),
            "execute-len-param-spec": source.replace(
                "def execute(days: tuple[date, ...], *, continue_on_failure: bool,\n",
                "def execute[**len](days: tuple[date, ...], *, "
                "continue_on_failure: bool,\n",
                1,
            ),
            "known-value-forged": source.replace(
                known_source,
                "            known = False\n",
                1,
            ),
            "known-rebound": source.replace(
                manifest_source,
                "            known = False\n" + manifest_source,
                1,
            ),
            "manifests-rebound": source.replace(
                known_source,
                "            manifests = ()\n" + known_source,
                1,
            ),
            "manifests-alias-effect": source.replace(
                known_source,
                "            alias = manifests\n"
                "            alias.clear()\n"
                + known_source,
                1,
            ),
            "known-alias-effect": source.replace(
                manifest_source,
                manifest_source + "            alias = known\n",
                1,
            ),
            "known-bool-module-shadow": source.replace(
                "import argparse\n",
                "import argparse\nbool = lambda value: False\n",
                1,
            ),
            "known-bool-import-then-rebind": source.replace(
                "import argparse\n",
                "import argparse\nfrom builtins import bool\n"
                "bool = lambda value: False\n",
                1,
            ),
            "known-bool-local-shadow": source.replace(
                day_loop_source,
                "    bool = lambda value: False\n" + day_loop_source,
                1,
            ),
            "known-nested-nonlocal": source.replace(
                manifest_source,
                manifest_source
                + "            def mutate():\n"
                "                nonlocal known\n"
                "                known = False\n",
                1,
            ),
            "known-default-walrus": source.replace(
                manifest_source,
                manifest_source
                + "            def helper(value=(known := False)):\n"
                "                return value\n",
                1,
            ),
            "known-lambda-default-walrus": source.replace(
                manifest_source,
                manifest_source
                + "            helper = lambda value=(known := False): value\n",
                1,
            ),
            "known-decorator-walrus": source.replace(
                manifest_source,
                manifest_source
                + "            @((known := decorate))\n"
                "            def helper():\n"
                "                pass\n",
                1,
            ),
            "known-class-base-walrus": source.replace(
                manifest_source,
                manifest_source
                + "            class Helper((known := object)):\n"
                "                pass\n",
                1,
            ),
            "manifests-conflict-else-default-walrus": source.replace(
                "            if len(manifests) > 1:\n"
                "                raise StageFailure(\"EXISTING\", "
                "\"CONFLICTING_SESSION_RUNS\")\n",
                "            if len(manifests) > 1:\n"
                "                raise StageFailure(\"EXISTING\", "
                "\"CONFLICTING_SESSION_RUNS\")\n"
                "            else:\n"
                "                def helper(value=(manifests := [])):\n"
                "                    return value\n",
                1,
            ),
            "manifests-reflective-clear": source.replace(
                manifest_source,
                manifest_source
                + "            locals()['manifests'].clear()\n",
                1,
            ),
            "known-h1-polarity": source.replace(
                "            if not known:\n",
                "            if known:\n",
                1,
            ),
            "known-h1-bool-wrapper": source.replace(
                "            if not known:\n",
                "            if not bool(known):\n",
                1,
            ),
            "known-h1-comparison": source.replace(
                "            if not known:\n",
                "            if known is False:\n",
                1,
            ),
            "known-h1-decoy": source.replace(
                "            if not known:\n",
                "            if False:\n",
                1,
            ).replace(
                score_dispatch_source,
                "            if not known:\n"
                "                pass\n"
                + score_dispatch_source,
                1,
            ),
            "known-eager-argument-annotation": source.replace(
                "from __future__ import annotations\n",
                "",
                1,
            ).replace(
                manifest_source,
                manifest_source
                + "            def helper(value: (known := False)):\n"
                "                return value\n",
                1,
            ),
            "known-eager-return-annotation": source.replace(
                "from __future__ import annotations\n",
                "",
                1,
            ).replace(
                manifest_source,
                manifest_source
                + "            def helper() -> (known := False):\n"
                "                return None\n",
                1,
            ),
            "lineage-eager-vararg-annotations": source.replace(
                "from __future__ import annotations\n",
                "",
                1,
            ).replace(
                manifest_source,
                manifest_source
                + "            def helper(*values: (known := False), "
                "**options: (manifests := ())):\n"
                "                return values, options\n",
                1,
            ),
            "known-nonlocal-through-comprehension-target": source.replace(
                manifest_source,
                manifest_source
                + "            def outer():\n"
                "                [known for known in ()]\n"
                "                def inner():\n"
                "                    nonlocal known\n"
                "                    known = False\n",
                1,
            ),
        }
        for mutation, mutated_source in mutations.items():
            with self.subTest(score_receipt_mutation=mutation):
                self.assertTrue(
                    h2c_score_receipt_suffix_violations(
                        ast.parse(mutated_source)
                    )
                )

        safe_prefixes = {
            "nested-len-parameter": (
                "    def helper(len):\n"
                "        return len\n"
            ),
            "comprehension-len-target": (
                "    [len(value) for len in ()]\n"
            ),
            "leftmost-comprehension-builtin-len": (
                "    [None for len in len(())]\n"
            ),
            "class-local-len-walrus": (
                "    class Holder:\n"
                "        (len := replacement)\n"
            ),
            "bare-global-len": "    global len\n",
            "nested-known-manifests": (
                "            def helper():\n"
                "                known = False\n"
                "                manifests = ()\n"
                "                return known, manifests\n"
            ),
            "comprehension-known-manifests": (
                "            [known for known in ()]\n"
                "            [manifests for manifests in ()]\n"
            ),
            "class-known-manifests": (
                "            class Holder:\n"
                "                known = False\n"
                "                manifests = ()\n"
            ),
            "class-walrus-known-manifests": (
                "            class Holder:\n"
                "                (known := False)\n"
                "                (manifests := ())\n"
            ),
            "uncalled-lambda-known-body": (
                "            helper = lambda: (known := False)\n"
            ),
            "nested-nonlocal-known-manifests-owned-locally": (
                "            def outer():\n"
                "                known = True\n"
                "                manifests = ()\n"
                "                def inner():\n"
                "                    nonlocal known, manifests\n"
                "                    known = False\n"
                "                    manifests = []\n"
            ),
            "nested-nonlocal-known-owned-by-definition": (
                "            def outer():\n"
                "                def known():\n"
                "                    return True\n"
                "                import example as manifests\n"
                "                def inner():\n"
                "                    nonlocal known, manifests\n"
                "                    known = False\n"
                "                    manifests = []\n"
            ),
            "nested-nonlocal-known-manifests-owned-by-evaluated-headers": (
                "            def outer():\n"
                "                def helper(value=(known := True)):\n"
                "                    return value\n"
                "                @((manifests := decorate))\n"
                "                def decorated():\n"
                "                    pass\n"
                "                class Base((known := object)):\n"
                "                    pass\n"
                "                def inner():\n"
                "                    nonlocal known, manifests\n"
                "                    known = False\n"
                "                    manifests = []\n"
            ),
            "nested-class-known-manifests-declarations-do-not-change-owner": (
                "            def outer():\n"
                "                known = True\n"
                "                manifests = ()\n"
                "                class Local:\n"
                "                    global known\n"
                "                    nonlocal manifests\n"
                "                def inner():\n"
                "                    nonlocal known, manifests\n"
                "                    known = False\n"
                "                    manifests = []\n"
            ),
        }
        for safe_case, insertion in safe_prefixes.items():
            protects_known = "known" in safe_case or "manifests" in safe_case
            anchor = manifest_source if protects_known else day_loop_source
            replacement = (
                anchor + insertion if protects_known else insertion + anchor
            )
            safe_source = source.replace(anchor, replacement, 1)
            with self.subTest(score_receipt_precision=safe_case):
                self.assertFalse(
                    h2c_score_receipt_suffix_violations(
                        ast.parse(safe_source)
                    )
                )

        reformatted = ast.unparse(ast.parse(source))
        self.assertFalse(
            h2c_score_receipt_suffix_violations(ast.parse(reformatted)),
            "format-only changes must preserve the structural receipt contract",
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
        self.assertFalse(
            h2c_score_receipt_suffix_violations(tree),
            "the final H2C score receipt guard or success emission drifted",
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
