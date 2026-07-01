#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a single-file X5_Crop.py for user-facing releases."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "x5crop"


def module_name_for_path(path: Path) -> str:
    relative = path.relative_to(ROOT)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def read_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        sources[module_name_for_path(path)] = path.read_text(encoding="utf-8")
    return sources


def package_names() -> set[str]:
    return {
        module_name_for_path(path)
        for path in PACKAGE_ROOT.rglob("__init__.py")
    }


def build_standalone_text(sources: dict[str, str], packages: set[str]) -> str:
    module_items = ",\n".join(
        f"    {module_name!r}: {source!r}" for module_name, source in sources.items()
    )
    package_items = ",\n".join(f"    {package!r}" for package in sorted(packages))
    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone release build of X5 Crop.

This file is generated from the modular V4 source tree. It embeds the internal
``x5crop`` package so end users can keep using one script plus one launcher.
Do not edit this generated file directly; edit ``x5crop/`` and rebuild.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys


_X5_EMBEDDED_SOURCES = {{
{module_items}
}}

_X5_EMBEDDED_PACKAGES = {{
{package_items}
}}


class _X5EmbeddedImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname not in _X5_EMBEDDED_SOURCES:
            return None
        return importlib.machinery.ModuleSpec(
            fullname,
            self,
            is_package=fullname in _X5_EMBEDDED_PACKAGES,
        )

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        name = module.__name__
        module.__file__ = f"<{{name}}>"
        if name in _X5_EMBEDDED_PACKAGES:
            module.__package__ = name
            module.__path__ = []
        else:
            module.__package__ = name.rsplit(".", 1)[0]
        code = compile(_X5_EMBEDDED_SOURCES[name], module.__file__, "exec")
        exec(code, module.__dict__)


def _x5_bootstrap() -> None:
    if not any(isinstance(finder, _X5EmbeddedImporter) for finder in sys.meta_path):
        sys.meta_path.insert(0, _X5EmbeddedImporter())


_x5_bootstrap()


if __name__ == "__main__":
    from x5crop.cli import main

    raise SystemExit(main())
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a standalone X5_Crop.py from the modular V4 source tree."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "X5_Crop.py",
        help="Output path for the generated standalone script.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_standalone_text(read_sources(), package_names()), encoding="utf-8")
    output.chmod(0o755)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
