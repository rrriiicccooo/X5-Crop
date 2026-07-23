from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import MISSING, dataclass, fields, is_dataclass
import importlib
import inspect
from importlib.util import resolve_name
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "x5crop"

RUNTIME_ROOTS = frozenset({"x5crop.entry.cli"})
STANDALONE_ROOTS = frozenset({"x5crop.configuration.consistency"})
STANDALONE_TOOL_ROOTS = frozenset(
    {
        "tools.build_release",
        "tools.build_standalone",
        "tools.regression.frame_slot_reference",
        "tools.regression.sample_expectations",
        "tools.regression.sample_validation",
        "tools.regression.compare",
    }
)

REFLECTED_READ_MODEL_PREFIXES = (
    "x5crop.domain",
    "x5crop.detection.evidence",
    "x5crop.detection.physical",
    "x5crop.detection.candidate.assessment",
    "x5crop.detection.candidate.selection.model",
    "x5crop.detection.geometry_resolution",
)

SOURCE_LAYER_PREFIXES: dict[str, tuple[str, ...]] = {
    "core": (
        "x5crop",
        "x5crop.app_info",
        "x5crop.domain",
        "x5crop.run_config",
        "x5crop.run_status",
        "x5crop.strip_modes",
        "x5crop.utils",
    ),
    "entry": ("x5crop.entry",),
    "runtime": ("x5crop.runtime",),
    "formats": ("x5crop.formats",),
    "configuration": ("x5crop.configuration",),
    "cache": ("x5crop.cache",),
    "geometry": ("x5crop.geometry",),
    "image": ("x5crop.image",),
    "io": ("x5crop.io",),
    "detection": ("x5crop.detection",),
    "output": ("x5crop.output",),
    "export": ("x5crop.export",),
    "report": ("x5crop.report",),
    "debug": ("x5crop.debug",),
}


@dataclass(frozen=True)
class SourceModule:
    name: str
    path: Path

    @property
    def package(self) -> str:
        if self.path.name == "__init__.py":
            return self.name
        return self.name.rpartition(".")[0]


def source_modules() -> dict[str, SourceModule]:
    modules: dict[str, SourceModule] = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        name = ".".join(parts)
        modules[name] = SourceModule(name=name, path=path)
    return modules


def parsed_source(module: SourceModule) -> ast.Module:
    return ast.parse(module.path.read_text(encoding="utf-8"), filename=str(module.path))


def duplicate_top_level_symbols() -> list[str]:
    offenders: list[str] = []
    modules = tuple(source_modules().values()) + tuple(_tool_modules().values())
    for module in modules:
        definitions: dict[str, list[int]] = {}
        for node in parsed_source(module).body:
            if not isinstance(
                node,
                (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue
            definitions.setdefault(node.name, []).append(node.lineno)
        offenders.extend(
            f"{module.name}:{name}:{','.join(str(line) for line in lines)}"
            for name, lines in definitions.items()
            if len(lines) > 1
        )
    return sorted(offenders)


def _known_module(name: str, modules: dict[str, SourceModule]) -> str | None:
    if name in modules:
        return name
    parts = name.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
    return None


def imported_source_modules(
    module: SourceModule,
    modules: dict[str, SourceModule],
) -> frozenset[str]:
    imported: set[str] = set()
    for node in ast.walk(parsed_source(module)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                known = _known_module(alias.name, modules)
                if known is not None:
                    imported.add(known)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level:
            relative = "." * node.level + (node.module or "")
            base = resolve_name(relative, module.package)
        else:
            base = node.module or ""

        known_base = _known_module(base, modules)
        if known_base is not None:
            imported.add(known_base)
        for alias in node.names:
            if alias.name == "*":
                continue
            candidate = f"{base}.{alias.name}" if base else alias.name
            if candidate in modules:
                imported.add(candidate)
    return frozenset(imported)


def source_import_graph() -> dict[str, frozenset[str]]:
    modules = source_modules()
    return {
        name: imported_source_modules(module, modules)
        for name, module in modules.items()
    }


def modules_importing_external(package_name: str) -> list[str]:
    importers: list[str] = []
    for module in source_modules().values():
        for node in ast.walk(parsed_source(module)):
            imported = False
            if isinstance(node, ast.Import):
                imported = any(
                    alias.name == package_name
                    or alias.name.startswith(f"{package_name}.")
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported = bool(
                    node.module == package_name
                    or (node.module or "").startswith(f"{package_name}.")
                )
            if imported:
                importers.append(module.name)
                break
    return sorted(importers)


def unreferenced_enum_members(
    module_name: str,
    enum_name: str,
) -> list[str]:
    modules = source_modules()
    module = modules[module_name]
    enum_node = next(
        node
        for node in parsed_source(module).body
        if isinstance(node, ast.ClassDef) and node.name == enum_name
    )
    members = {
        target.id
        for statement in enum_node.body
        if isinstance(statement, ast.Assign)
        for target in statement.targets
        if isinstance(target, ast.Name)
    }
    referenced = {
        node.attr
        for source_module in modules.values()
        for node in ast.walk(parsed_source(source_module))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == enum_name
    }
    return sorted(members - referenced)


def source_layer_import_graph() -> dict[str, frozenset[str]]:
    graph: dict[str, set[str]] = {
        layer: set() for layer in SOURCE_LAYER_PREFIXES
    }
    for source, targets in source_import_graph().items():
        source_layers = source_layer_memberships(source)
        if len(source_layers) != 1:
            continue
        source_layer = source_layers[0]
        for target in targets:
            target_layers = source_layer_memberships(target)
            if len(target_layers) == 1 and target_layers[0] != source_layer:
                graph[source_layer].add(target_layers[0])
    return {
        layer: frozenset(targets)
        for layer, targets in graph.items()
    }


def source_layer_memberships(module_name: str) -> tuple[str, ...]:
    return tuple(
        layer
        for layer, prefixes in SOURCE_LAYER_PREFIXES.items()
        if module_has_prefix(module_name, prefixes)
        and not (
            layer == "core"
            and module_name.startswith("x5crop.")
            and module_name not in prefixes
        )
    )


def module_has_prefix(module: str, prefixes: Iterable[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def forbidden_import_edges(
    source_prefixes: Iterable[str],
    target_prefixes: Iterable[str],
) -> list[tuple[str, str]]:
    return sorted(
        (source, target)
        for source, targets in source_import_graph().items()
        if module_has_prefix(source, source_prefixes)
        for target in targets
        if module_has_prefix(target, target_prefixes)
    )


def pass_through_classes() -> list[str]:
    offenders: list[str] = []
    for module in source_modules().values():
        for node in parsed_source(module).body:
            if not isinstance(node, ast.ClassDef) or not node.bases:
                continue
            statements = [
                statement
                for statement in node.body
                if not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
            ]
            if not statements or all(isinstance(statement, ast.Pass) for statement in statements):
                offenders.append(f"{module.name}.{node.name}")
    return sorted(offenders)


def _argument_root_name(argument: ast.expr) -> str | None:
    while isinstance(argument, ast.Attribute):
        argument = argument.value
    return argument.id if isinstance(argument, ast.Name) else None


def _pass_through_functions(modules: Iterable[SourceModule]) -> list[str]:
    offenders: list[str] = []
    for module in modules:
        for node in parsed_source(module).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_") or node.name == "main":
                continue
            statements = [
                statement
                for statement in node.body
                if not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
            ]
            if len(statements) != 1:
                continue
            statement = statements[0]
            call = (
                statement.value
                if isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                else statement.value
                if isinstance(statement, ast.Return)
                and isinstance(statement.value, ast.Call)
                else None
            )
            if call is None or call.keywords:
                continue
            parameters = tuple(
                argument.arg
                for argument in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
            )
            forwarded = tuple(
                root_name
                for argument in call.args
                if (root_name := _argument_root_name(argument)) is not None
            )
            if len(forwarded) == len(call.args) and forwarded == parameters:
                offenders.append(f"{module.name}:{node.lineno}:{node.name}")
    return sorted(offenders)


def pass_through_source_functions() -> list[str]:
    return _pass_through_functions(source_modules().values())


def duplicate_dataclass_models(
    left_prefix: str,
    right_prefix: str,
) -> list[tuple[str, str]]:
    models: dict[tuple[str, ...], list[str]] = {}
    for module in source_modules().values():
        if not module_has_prefix(module.name, (left_prefix, right_prefix)):
            continue
        for node in parsed_source(module).body:
            if not isinstance(node, ast.ClassDef):
                continue
            is_dataclass = any(
                (isinstance(decorator, ast.Name) and decorator.id == "dataclass")
                or (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "dataclass"
                )
                for decorator in node.decorator_list
            )
            if not is_dataclass:
                continue
            field_names = tuple(
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
            )
            if field_names:
                models.setdefault(field_names, []).append(f"{module.name}.{node.name}")

    offenders: list[tuple[str, str]] = []
    for names in models.values():
        left = [name for name in names if module_has_prefix(name, (left_prefix,))]
        right = [name for name in names if module_has_prefix(name, (right_prefix,))]
        offenders.extend((left_name, right_name) for left_name in left for right_name in right)
    return sorted(offenders)


def unreferenced_top_level_symbols() -> list[str]:
    modules = source_modules()
    references: set[tuple[str, str]] = set()
    for module in modules.values():
        tree = parsed_source(module)
        module_aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                references.add((module.name, node.id))
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id in module_aliases
            ):
                references.add((module_aliases[node.value.id], node.attr))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in modules:
                        module_aliases[alias.asname or alias.name.split(".")[0]] = (
                            alias.name
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative = "." * node.level + (node.module or "")
                    base = resolve_name(relative, module.package)
                else:
                    base = node.module or ""
                for alias in node.names:
                    references.add((base, alias.name))
                    imported_module = f"{base}.{alias.name}" if base else alias.name
                    if imported_module in modules:
                        module_aliases[alias.asname or alias.name] = imported_module

    tools_root = PROJECT_ROOT / "tools"
    for path in tools_root.rglob("*.py"):
        module_name = ".".join(path.relative_to(PROJECT_ROOT).with_suffix("").parts)
        package = module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level:
                relative = "." * node.level + (node.module or "")
                base = resolve_name(relative, package)
            else:
                base = node.module or ""
            for alias in node.names:
                references.add((base, alias.name))

    unreferenced: list[str] = []
    for module in modules.values():
        for node in parsed_source(module).body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name == "main":
                continue
            if (module.name, node.name) not in references:
                unreferenced.append(f"{module.name}.{node.name}")
    return sorted(unreferenced)


def unreferenced_public_assignments() -> list[str]:
    modules = source_modules()
    references: set[tuple[str, str]] = set()
    for module in modules.values():
        tree = parsed_source(module)
        module_aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                references.add((module.name, node.id))
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id in module_aliases
            ):
                references.add((module_aliases[node.value.id], node.attr))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in modules:
                        module_aliases[alias.asname or alias.name.split(".")[0]] = (
                            alias.name
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative = "." * node.level + (node.module or "")
                    base = resolve_name(relative, module.package)
                else:
                    base = node.module or ""
                for alias in node.names:
                    references.add((base, alias.name))
                    imported_module = f"{base}.{alias.name}" if base else alias.name
                    if imported_module in modules:
                        module_aliases[alias.asname or alias.name] = imported_module

    for path in (PROJECT_ROOT / "tools").rglob("*.py"):
        module_name = ".".join(path.relative_to(PROJECT_ROOT).with_suffix("").parts)
        package = module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level:
                relative = "." * node.level + (node.module or "")
                base = resolve_name(relative, package)
            else:
                base = node.module or ""
            for alias in node.names:
                references.add((base, alias.name))

    offenders: list[str] = []
    for module in modules.values():
        for node in parsed_source(module).body:
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if not isinstance(target, ast.Name) or target.id.startswith("_"):
                    continue
                if (module.name, target.id) not in references:
                    offenders.append(f"{module.name}.{target.id}")
    return sorted(offenders)


def unreferenced_public_symbols() -> list[str]:
    return [
        symbol
        for symbol in unreferenced_top_level_symbols()
        if not symbol.rpartition(".")[2].startswith("_")
    ]


def modules_with_export_lists() -> list[str]:
    offenders: list[str] = []
    for module in source_modules().values():
        for node in parsed_source(module).body:
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                offenders.append(module.name)
    return sorted(offenders)


def functions_with_unused_parameters() -> list[str]:
    offenders: list[str] = []
    for module in source_modules().values():
        for node in ast.walk(parsed_source(module)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            if node.args.vararg is not None:
                arguments.append(node.args.vararg)
            if node.args.kwarg is not None:
                arguments.append(node.args.kwarg)
            loaded_names = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
            }
            unused = [
                argument.arg
                for argument in arguments
                if argument.arg not in {"self", "cls"}
                and argument.arg not in loaded_names
            ]
            if unused:
                offenders.append(
                    f"{module.name}:{node.lineno}:{node.name}({', '.join(unused)})"
                )
    return sorted(offenders)


def functions_with_unused_local_assignments() -> list[str]:
    offenders: list[str] = []
    for module in source_modules().values():
        for node in ast.walk(parsed_source(module)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            stored = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Store)
                and not child.id.startswith("_")
            }
            loaded = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
            }
            unused = sorted(stored - loaded)
            if unused:
                offenders.append(
                    f"{module.name}:{node.lineno}:{node.name}({', '.join(unused)})"
                )
    return sorted(offenders)


def functions_with_untyped_parameters() -> list[str]:
    offenders: list[str] = []
    for module in source_modules().values():
        for node in ast.walk(parsed_source(module)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            missing = [
                argument.arg
                for argument in arguments
                if argument.arg not in {"self", "cls"}
                and argument.annotation is None
            ]
            if missing:
                offenders.append(
                    f"{module.name}:{node.lineno}:{node.name}({', '.join(missing)})"
                )
    return sorted(offenders)


def invalid_dataclass_default_factories(module_prefix: str) -> list[str]:
    offenders: list[str] = []
    for module_name in source_modules():
        if not module_has_prefix(module_name, (module_prefix,)):
            continue
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if not isinstance(value, type) or not is_dataclass(value):
                continue
            for model_field in fields(value):
                if model_field.default_factory is MISSING:
                    continue
                try:
                    signature = inspect.signature(model_field.default_factory)
                except (TypeError, ValueError):
                    continue
                required = [
                    parameter.name
                    for parameter in signature.parameters.values()
                    if parameter.default is inspect.Parameter.empty
                    and parameter.kind
                    not in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                ]
                if required:
                    offenders.append(
                        f"{module_name}.{value.__name__}.{model_field.name}({', '.join(required)})"
                    )
    return sorted(set(offenders))


def unreferenced_dataclass_fields() -> list[str]:
    modules = source_modules()
    used_names: set[str] = set()
    for module in modules.values():
        for node in ast.walk(parsed_source(module)):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                used_names.add(node.attr)

    reflected_dataclasses = {
        "FrameSizeMm",
        "ModePolicy",
    }

    offenders: list[str] = []
    for module in modules.values():
        if module_has_prefix(module.name, REFLECTED_READ_MODEL_PREFIXES):
            continue
        for node in parsed_source(module).body:
            if not isinstance(node, ast.ClassDef):
                continue
            is_dataclass = any(
                (
                    isinstance(decorator, ast.Name)
                    and decorator.id == "dataclass"
                )
                or (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "dataclass"
                )
                for decorator in node.decorator_list
            )
            if not is_dataclass:
                continue
            if node.name in reflected_dataclasses:
                continue
            for statement in node.body:
                if not (
                    isinstance(statement, ast.AnnAssign)
                    and isinstance(statement.target, ast.Name)
                ):
                    continue
                field_name = statement.target.id
                if field_name not in used_names:
                    offenders.append(f"{module.name}.{node.name}.{field_name}")
    return sorted(offenders)


def _unused_imports(modules: Iterable[SourceModule]) -> list[str]:
    offenders: list[str] = []
    for module in modules:
        tree = parsed_source(module)
        loaded_names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        for node in tree.body:
            if isinstance(node, ast.Import):
                aliases = (
                    (alias.asname or alias.name.split(".")[0], node.lineno)
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
                aliases = (
                    (alias.asname or alias.name, node.lineno)
                    for alias in node.names
                    if alias.name != "*"
                )
            else:
                continue
            for name, line_number in aliases:
                if name not in loaded_names:
                    offenders.append(f"{module.name}:{line_number}:{name}")
    return sorted(offenders)


def unused_imports() -> list[str]:
    return _unused_imports(source_modules().values())


def unused_tool_imports() -> list[str]:
    return _unused_imports(_tool_modules().values())


def unreferenced_methods() -> list[str]:
    modules = source_modules()
    referenced_attributes = {
        node.attr
        for module in modules.values()
        for node in ast.walk(parsed_source(module))
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
    }
    offenders: list[str] = []
    for module in modules.values():
        for class_node in parsed_source(module).body:
            if not isinstance(class_node, ast.ClassDef):
                continue
            for node in class_node.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name.startswith("__") or node.name in referenced_attributes:
                    continue
                offenders.append(f"{module.name}.{class_node.name}.{node.name}")
    return sorted(offenders)


def reachable_source_modules(roots: Iterable[str]) -> frozenset[str]:
    graph = source_import_graph()
    pending = list(roots)
    reached: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reached or name not in graph:
            continue
        reached.add(name)
        pending.extend(graph[name] - reached)

    for name in tuple(reached):
        parts = name.split(".")
        for index in range(1, len(parts)):
            package = ".".join(parts[:index])
            if package in graph:
                reached.add(package)
    return frozenset(reached)


def standalone_tool_modules() -> frozenset[str]:
    modules: set[str] = set()
    for path in sorted((PROJECT_ROOT / "tools").rglob("*.py")):
        if "tests" in path.relative_to(PROJECT_ROOT / "tools").parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "main"
            for node in tree.body
        ):
            modules.add(".".join(path.relative_to(PROJECT_ROOT).with_suffix("").parts))
    return frozenset(modules)


def _tool_modules() -> dict[str, SourceModule]:
    modules: dict[str, SourceModule] = {}
    for path in sorted((PROJECT_ROOT / "tools").rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        name = ".".join(parts)
        modules[name] = SourceModule(name=name, path=path)
    return modules


def unreferenced_tool_helpers() -> list[str]:
    modules = _tool_modules()
    references: set[tuple[str, str]] = set()
    for module in modules.values():
        tree = parsed_source(module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                references.add((module.name, node.id))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative = "." * node.level + (node.module or "")
                    base = resolve_name(relative, module.package)
                else:
                    base = node.module or ""
                for alias in node.names:
                    references.add((base, alias.name))

    offenders: list[str] = []
    for module in modules.values():
        is_test_module = module.path.name.startswith("test_")
        for node in parsed_source(module).body:
            if not isinstance(
                node,
                (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue
            if node.name.startswith("_") or node.name == "main":
                continue
            if is_test_module and isinstance(node, ast.ClassDef):
                continue
            if (module.name, node.name) not in references:
                offenders.append(f"{module.name}.{node.name}")
    return sorted(offenders)


def unreferenced_tool_assignments() -> list[str]:
    modules = _tool_modules()
    loaded_names: set[tuple[str, str]] = set()
    for module in modules.values():
        for node in ast.walk(parsed_source(module)):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loaded_names.add((module.name, node.id))

    offenders: list[str] = []
    for module in modules.values():
        for node in parsed_source(module).body:
            targets: tuple[ast.expr, ...]
            if isinstance(node, ast.Assign):
                targets = tuple(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = (node.target,)
            else:
                continue
            for target in targets:
                if not isinstance(target, ast.Name) or not target.id.startswith("_"):
                    continue
                if (module.name, target.id) not in loaded_names:
                    offenders.append(f"{module.name}:{node.lineno}:{target.id}")
    return sorted(offenders)


def pass_through_tool_functions() -> list[str]:
    return _pass_through_functions(_tool_modules().values())
