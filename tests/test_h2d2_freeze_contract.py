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
BASELINE_BUNDLE_SHA256 = "0f6f714d74b516e7966cc1bdc56478e85491b7c31805129a86e06ab3a462de87"
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


def lexical_import_origins(
        tree: ast.Module,
        *,
        include_from_imports: bool = False,
        propagate_aliases: bool = False,
) -> tuple[dict[ast.AST, ast.AST], object]:
    """Resolve import bindings without leaking aliases across lexical scopes."""
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
                return frozenset()
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
            scope_bound_names[scope].update(
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            scope_bound_names[scope].update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            )
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
    for class_node in class_nodes:
        for statement in class_node.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_methods[class_node].setdefault(
                    statement.name,
                    set(),
                ).add(statement)

    def method_descriptor_kind(
            method: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        decorator_names = {
            decorator.id
            if isinstance(decorator, ast.Name)
            else decorator.attr
            if isinstance(decorator, ast.Attribute)
            else ""
            for decorator in method.decorator_list
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
            for method in class_methods[class_node].get(node.attr, ()):
                resolved.add((
                    method,
                    method_descriptor_kind(method) == "class",
                ))
        for class_node in resolve_instance_expression(node.value, scope):
            for method in class_methods[class_node].get(node.attr, ()):
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

    def contains_tracked_binding(
            node: ast.AST,
            scope: ast.AST | None = None,
    ) -> bool:
        active_bindings = set(tracked_bindings)
        while scope is not None:
            active_bindings.update(scoped_tracked_bindings[scope])
            scope = callable_parents[scope]
        return any(
            isinstance(item, ast.Name)
            and isinstance(item.ctx, ast.Load)
            and item.id in active_bindings
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
        active_bindings = set(tracked_bindings)
        while scope is not None:
            active_bindings.update(scoped_tracked_bindings[scope])
            scope = callable_parents[scope]
        return any(
            isinstance(item, ast.Name)
            and isinstance(item.ctx, ast.Load)
            and item.id in active_bindings
            and item not in callable_references
            for item in ast.walk(node)
        )

    def contains_assignment_tracked_binding(
            node: ast.AST,
            scope: ast.AST | None,
    ) -> bool:
        direct_local_return = (
            isinstance(node, ast.Call)
            and any(
                local_callable in tracked_return_callables
                for local_callable, _ in local_call_targets(node)
            )
        )
        return direct_local_return or (
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
            and local_call_targets(node)
        ):
            for local_callable, bound_receiver in local_call_targets(call):
                (
                    positional,
                    named,
                    vararg,
                    kwarg,
                    defaults,
                ) = callable_parameter_bindings(local_callable)
                newly_tracked = {
                    parameter.arg
                    for parameter, default in defaults
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
                                and name == positional[0].arg
                            )
                        )
                        if kwarg is not None:
                            newly_tracked.add(kwarg.arg)
                    elif keyword.arg in named:
                        newly_tracked.add(named[keyword.arg].arg)
                    elif kwarg is not None:
                        newly_tracked.add(kwarg.arg)
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

    findings = []
    for node in ast.walk(tree):
        if (
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
            and node.args
            and contains_tracked_binding(
                node.args[0],
                enclosing_callable(node),
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
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"exit", "quit"}
            )
            self.assertFalse(
                early_exit_calls,
                "exit or quit cannot skip a later stage dispatch",
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
