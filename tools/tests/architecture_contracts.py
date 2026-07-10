from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "x5crop"

RUNTIME_ROOTS = frozenset({"x5crop.entry.cli"})
STANDALONE_ROOTS = frozenset({"x5crop.policies.consistency"})
STANDALONE_TOOL_ROOTS = frozenset(
    {
        "tools.build_standalone",
        "tools.regression.compare",
        "tools.regression.reference_classify",
    }
)


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


def public_top_level_symbols(node_type: type[ast.AST]) -> dict[str, list[str]]:
    symbols: dict[str, list[str]] = {}
    for module in source_modules().values():
        for node in parsed_source(module).body:
            if isinstance(node, node_type) and not node.name.startswith("_"):
                symbols.setdefault(node.name, []).append(module.name)
    return symbols


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


def unreferenced_top_level_symbols() -> list[str]:
    modules = source_modules()
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
        "SeparatorGapHint",
    }

    offenders: list[str] = []
    for module in modules.values():
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


def unused_imports() -> list[str]:
    offenders: list[str] = []
    for module in source_modules().values():
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


def source_paths(*roots: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for root in roots
        for path in sorted(root.rglob("*.py"))
    )


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


def text_offenders(paths: Iterable[Path], banned: Iterable[str]) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for term in banned:
            if term in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")
    return offenders
