from __future__ import annotations

from functools import lru_cache

from ..formats import STRIP_CHOICES
from .runtime.policy import DetectionPolicy
from .formats import POLICY_BUILDERS


def _build_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    if strip_mode not in STRIP_CHOICES:
        raise ValueError(f"Unsupported strip policy: {strip_mode}")
    try:
        build_policy = POLICY_BUILDERS[format_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported format policy: {format_id}") from exc
    return build_policy(strip_mode)


@lru_cache(maxsize=None)
def get_detection_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    return _build_policy(format_id, strip_mode)


__all__ = ["get_detection_policy"]
