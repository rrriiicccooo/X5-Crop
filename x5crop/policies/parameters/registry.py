from __future__ import annotations

from typing import Any

from ...formats import FORMAT_CHOICES
from ..formats.modules import import_format_module
from .aggregate import FormatParameters


def _format_behavior_parameter_defaults(format_name: str) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    if format_name in {
        "135-dual",
        "half",
        "xpan",
        "120-645",
        "120-66",
        "120-67",
    }:
        defaults.update(
            lucky_pass_risk_enabled=False,
            leading_grid_failure_enabled=False,
        )
    if format_name == "135-dual":
        defaults.update(
            separator_width_profile_enabled=False,
            separator_width_profile_partial_enabled=False,
            partial_safe_extra_frames_enabled=False,
        )
    if format_name == "half":
        defaults.update(
            score_full_width_cv=0.008,
            separator_model_grid_credit=0.25,
            separator_model_equal_credit=0.08,
        )
    if format_name == "xpan":
        defaults.update(
            partial_auto_include_default_count=True,
            separator_model_grid_credit=0.20,
            separator_model_equal_credit=0.06,
        )
    if format_name == "120-66":
        defaults.update(
            score_outer_max_area=1.0,
            score_outer_too_large=1.0,
            score_outer_too_large_cap=0.86,
            calibrate_hard_full_confidence_floor=0.86,
            partial_auto_include_default_count=True,
            separator_gate_edge_pair_min_score_without_broad_width=1.0,
            separator_gate_edge_pair_min_score_with_broad_width=0.0,
            separator_gate_min_broad_separator_width_gaps_for_auto=0,
            partial_safe_extra_frames_min_broad_separator_width_gaps=2,
            partial_safe_extra_frames_leading_content_check=True,
            partial_safe_extra_frames_frame_content_check=True,
        )
    if format_name == "120-67":
        defaults.update(
            score_outer_too_large=0.995,
            score_outer_too_large_cap=0.86,
            calibrate_hard_full_confidence_floor=0.86,
        )
    return defaults


def base_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    params = _format_behavior_parameter_defaults(format_name)
    params.update(overrides)
    return FormatParameters(format_name, **params)


def base_medium_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    params: dict[str, Any] = {
        "score_full_width_cv": 0.012,
        "content_profile_min_run_ratio": 0.18,
        "separator_model_grid_credit": 0.18,
        "separator_model_equal_credit": 0.04,
        "nearby_score_multiplier": 1.28,
        "calibrate_separator_weight": 0.36,
        "calibrate_geometry_weight": 0.32,
        "calibrate_content_weight": 0.32,
    }
    params.update(overrides)
    return base_format_parameters(format_name, **params)


def format_parameters(format_name: str) -> FormatParameters:
    if format_name not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format parameters: {format_name}")
    module = import_format_module(format_name)
    return module.parameters()

__all__ = [
    "base_format_parameters",
    "base_medium_format_parameters",
    "format_parameters",
]
