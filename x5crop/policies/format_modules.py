from __future__ import annotations

from importlib import import_module
from types import ModuleType

from ..formats import FORMAT_CHOICES


def format_module_name(format_id: str) -> str:
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format policy: {format_id}")
    return f"format_{format_id.replace('-', '_')}"


def import_format_module(format_id: str) -> ModuleType:
    return import_module(f"{__package__}.{format_module_name(format_id)}")


__all__ = [
    "format_module_name",
    "import_format_module",
]
