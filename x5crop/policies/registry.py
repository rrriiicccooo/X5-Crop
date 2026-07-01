from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from ..formats import FORMAT_CHOICES, STRIP_CHOICES
from .base import DetectionPolicy


def _format_module_name(format_id: str) -> str:
    return f"format_{format_id.replace('-', '_')}"


def _policy_module(format_id: str):
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format policy: {format_id}")
    return import_module(f"{__package__}.{_format_module_name(format_id)}")


def _build_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    if strip_mode not in STRIP_CHOICES:
        raise ValueError(f"Unsupported strip policy: {strip_mode}")
    module = _policy_module(format_id)
    return module.build_policy(strip_mode)


@lru_cache(maxsize=None)
def get_detection_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    return _build_policy(format_id, strip_mode)


__all__ = ["get_detection_policy"]
