from __future__ import annotations

from typing import Any

from ..formats import FORMAT_CHOICES
from .format_modules import import_format_module
from .parameter_aggregate import FormatParameters


def base_medium_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    params: dict[str, Any] = {
        "score_full_width_cv": 0.012,
        "content_profile_min_run_ratio": 0.18,
        "separator_model_grid_credit": 0.18,
        "separator_model_equal_credit": 0.04,
        "separator_gate_profile": "all_internal_gaps_hard",
        "nearby_score_multiplier": 1.28,
        "calibrate_separator_weight": 0.36,
        "calibrate_geometry_weight": 0.32,
        "calibrate_content_weight": 0.32,
        "wide_gap_retry_enabled": False,
        "nearby_active_correction": False,
        "lucky_pass_risk_enabled": False,
        "leading_grid_failure_enabled": False,
    }
    params.update(overrides)
    return FormatParameters(format_name, **params)


def format_parameters(format_name: str) -> FormatParameters:
    if format_name not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format parameters: {format_name}")
    module = import_format_module(format_name)
    return module.parameters()

__all__ = [
    "base_medium_format_parameters",
    "format_parameters",
]
