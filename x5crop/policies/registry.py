from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from ..format_specs import FORMAT_CHOICES, STRIP_CHOICES
from .base import DetectionPolicy

FORMAT_POLICY_MODULES = {
    "135": "standard_strip",
    "135-dual": "parallel_lane",
    "half": "dense_half_frame",
    "xpan": "panoramic_strip",
    "120-645": "medium_rectangle",
    "120-66": "medium_square",
    "120-67": "medium_wide",
}


def policy_module(format_id: str):
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format policy: {format_id}")
    try:
        module_name = FORMAT_POLICY_MODULES[format_id]
    except KeyError as exc:
        raise ValueError(f"No policy module registered for format: {format_id}") from exc
    return import_module(f"{__package__}.{module_name}")


def build_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    if strip_mode not in STRIP_CHOICES:
        raise ValueError(f"Unsupported strip policy: {strip_mode}")
    module = policy_module(format_id)
    return module.build_policy(strip_mode)


@lru_cache(maxsize=None)
def get_detection_policy(format_id: str, strip_mode: str) -> DetectionPolicy:
    return build_policy(format_id, strip_mode)


def policy_report_detail(format_id: str, strip_mode: str) -> dict:
    return get_detection_policy(format_id, strip_mode).report_detail()
