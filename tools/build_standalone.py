#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a single-file X5_Crop.py for user-facing releases.

The source tree stays modular in V4, but Release packages should remain simple:
users only need the generated X5_Crop.py plus the platform launcher.
"""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MODULES = [
    "x5crop.common",
    "x5crop.evidence",
    "x5crop.io",
    "x5crop.geometry",
    "x5crop.detection.pipeline",
    "x5crop.deskew",
    "x5crop.debug.render",
    "x5crop.reports",
    "x5crop.cli",
]


def module_path(module_name: str) -> Path:
    parts = module_name.split(".")
    return ROOT.joinpath(*parts).with_suffix(".py")


def read_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for module_name in MODULES:
        path = module_path(module_name)
        sources[module_name] = path.read_text(encoding="utf-8")
    return sources


def build_standalone_text(sources: dict[str, str]) -> str:
    module_items = ",\n".join(
        f"    {module_name!r}: {source!r}" for module_name, source in sources.items()
    )
    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone release build of X5 Crop.

This file is generated from the modular V4 source tree. It embeds the internal
``x5crop`` package so end users can keep using one script plus one launcher.
Do not edit this generated file directly; edit ``x5crop/`` and rebuild.
"""

from __future__ import annotations

import sys
import types


_X5_EMBEDDED_SOURCES = {{
{module_items}
}}


def _x5_make_package(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = __file__
    module.__package__ = name
    module.__path__ = []
    sys.modules[name] = module
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        parent = sys.modules[parent_name]
        setattr(parent, child_name, module)
    return module


def _x5_load_module(name: str, source: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = __file__
    module.__package__ = name.rsplit(".", 1)[0]
    sys.modules[name] = module
    parent_name, child_name = name.rsplit(".", 1)
    parent = sys.modules[parent_name]
    setattr(parent, child_name, module)
    code = compile(source, f"<{{name}}>", "exec")
    exec(code, module.__dict__)
    return module


def _x5_bootstrap() -> None:
    if "x5crop.cli" in sys.modules:
        return
    _x5_make_package("x5crop")
    _x5_make_package("x5crop.detection")
    _x5_make_package("x5crop.debug")
    for module_name, source in _X5_EMBEDDED_SOURCES.items():
        _x5_load_module(module_name, source)
    package = sys.modules["x5crop"]
    common = sys.modules["x5crop.common"]
    package.SCRIPT_NAME = common.SCRIPT_NAME
    package.VERSION = common.VERSION


_x5_bootstrap()


if __name__ == "__main__":
    raise SystemExit(sys.modules["x5crop.cli"].main())
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
    output.write_text(build_standalone_text(read_sources()), encoding="utf-8")
    output.chmod(0o755)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
