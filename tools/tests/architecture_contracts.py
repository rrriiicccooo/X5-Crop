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


def text_offenders(paths: Iterable[Path], banned: Iterable[str]) -> list[str]:
    offenders: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for term in banned:
            if term in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {term}")
    return offenders
