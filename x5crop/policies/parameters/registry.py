from __future__ import annotations

from typing import Any

from ...formats import FORMAT_CHOICES
from ..formats.modules import import_format_module
from ..separator_gate_profiles import SEPARATOR_GATE_PROFILE_ALL_INTERNAL_GAPS_HARD
from .aggregate import FormatParameters


def base_medium_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    params: dict[str, Any] = {
        "score_full_width_cv": 0.012,
        "content_profile_min_run_ratio": 0.18,
        "separator_model_grid_credit": 0.18,
        "separator_model_equal_credit": 0.04,
        "separator_gate_profile": SEPARATOR_GATE_PROFILE_ALL_INTERNAL_GAPS_HARD,
        "nearby_score_multiplier": 1.28,
        "calibrate_separator_weight": 0.36,
        "calibrate_geometry_weight": 0.32,
        "calibrate_content_weight": 0.32,
        "nearby_active_refinement": False,
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
