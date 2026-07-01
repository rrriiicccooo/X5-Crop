from __future__ import annotations

from functools import lru_cache
from importlib import import_module

from ..format_specs import FORMAT_CHOICES, STRIP_CHOICES
from .base import DetectionPolicy

FORMAT_POLICY_MODULES = {
    "135": "format_135",
    "135-dual": "format_135_dual",
    "half": "format_half",
    "xpan": "format_xpan",
    "120-645": "format_120_645",
    "120-66": "format_120_66",
    "120-67": "format_120_67",
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
