from __future__ import annotations

from functools import lru_cache

from ..formats import STRIP_CHOICES
from .base import DetectionPolicy
from .format_modules import import_format_module


def _build_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    if strip_mode not in STRIP_CHOICES:
        raise ValueError(f"Unsupported strip policy: {strip_mode}")
    module = import_format_module(format_id)
    return module.build_policy(strip_mode)


@lru_cache(maxsize=None)
def get_detection_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    return _build_policy(format_id, strip_mode)


__all__ = ["get_detection_policy"]
