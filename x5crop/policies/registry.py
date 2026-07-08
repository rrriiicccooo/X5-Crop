from __future__ import annotations

from functools import lru_cache

from ..formats import STRIP_CHOICES
from .assembly.format_presets import build_policy_from_format
from .runtime.policy import DetectionPolicy
from .formats import PARAMETER_FACTORIES


def _build_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    if strip_mode not in STRIP_CHOICES:
        raise ValueError(f"Unsupported strip policy: {strip_mode}")
    try:
        parameter_factory = PARAMETER_FACTORIES[format_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported format policy: {format_id}") from exc
    return build_policy_from_format(format_id, parameter_factory, strip_mode)


@lru_cache(maxsize=None)
def get_detection_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    return _build_policy(format_id, strip_mode)


__all__ = ["get_detection_policy"]
