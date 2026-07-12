from __future__ import annotations

from functools import lru_cache

from ..formats import FORMAT_CHOICES, format_spec
from ..strip_modes import STRIP_MODES
from .assembly.factory import build_detection_policy
from .parameters.aggregate import FormatParameters
from .runtime.policy import DetectionPolicy


def _build_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    if strip_mode not in STRIP_MODES:
        raise ValueError(f"Unsupported strip policy: {strip_mode}")
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format policy: {format_id}")
    spec = format_spec(format_id)
    return build_detection_policy(spec, FormatParameters(), strip_mode)


@lru_cache(maxsize=None)
def get_detection_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    return _build_policy(format_id, strip_mode)
