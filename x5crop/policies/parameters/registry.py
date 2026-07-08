from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...formats import FORMAT_CHOICES
from .aggregate import FormatParameters
from .ownership import split_format_parameter_overrides


FORMAT_OVERRIDE_PARAMETER_PATHS = {
    "content_profile_min_run_ratio": ("content_profile", "min_run_ratio"),
    "gap_max_width_max": ("gap_search", "max_width_max"),
    "outer_align_long_margin_ratio": ("content_containment_correction", "long_margin_ratio"),
    "outer_align_long_margin_cap_ratio": ("content_containment_correction", "long_margin_cap_ratio"),
    "outer_align_short_excess_ratio": ("content_containment_correction", "short_excess_ratio"),
    "outer_align_short_requires_hard_anchors": ("content_containment_correction", "short_requires_hard_anchors"),
    "outer_align_short_content_height_max": ("content_containment_correction", "short_content_height_max"),
    "partial_edge_ratio_extras": ("edge_anchored_content_position", "ratio_extras"),
    "partial_edge_max_candidates": ("edge_anchored_content_position", "max_candidates"),
    "separator_outer_min_score": ("separator_outer_band", "min_score"),
    "separator_outer_band_score": ("separator_outer_band", "band_score"),
    "separator_outer_spacing_min_ratio": ("separator_outer_band", "spacing_min_ratio"),
    "separator_outer_spacing_max_ratio": ("separator_outer_band", "spacing_max_ratio"),
    "separator_outer_frame_error_max": ("separator_outer_band", "frame_error_max"),
    "separator_outer_max_width_ratio": ("separator_outer_band", "max_width_ratio"),
    "separator_outer_gap_max_width_ratio": ("outer_strategy", "separator_gap_search_max_width_ratio"),
    "separator_outer_source_candidates": ("separator_outer_band", "source_candidate_count"),
    "separator_outer_band_candidates": ("separator_outer_band", "band_candidate_count"),
    "separator_outer_pair_candidates": ("separator_outer_band", "pair_candidate_count"),
    "separator_outer_max_candidates": ("separator_outer_band", "max_candidates"),
    "separator_width_profile_max_width_ratio": ("separator_width_profile", "max_width_ratio"),
    "separator_full_width_outer_margin_ratios": ("separator_full_width_outer", "margin_ratios"),
    "separator_full_width_outer_max_candidates": ("separator_full_width_outer", "max_candidates"),
    "separator_full_width_outer_source_candidates": ("separator_full_width_outer", "source_candidate_count"),
    "short_axis_geometry_correction_min_error": ("short_axis_geometry_correction", "min_error"),
}


def _with_parameter_override(params: FormatParameters, key: str, value: Any) -> FormatParameters:
    group_name, field_name = FORMAT_OVERRIDE_PARAMETER_PATHS[key]
    group = getattr(params, group_name)
    return replace(params, **{group_name: replace(group, **{field_name: value})})


def base_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    layers = split_format_parameter_overrides(overrides)
    params = FormatParameters(format_name)
    for key, value in layers.as_dict().items():
        params = _with_parameter_override(params, key, value)
    return params


def base_medium_format_parameters(format_name: str, **overrides: Any) -> FormatParameters:
    params: dict[str, Any] = {
        "content_profile_min_run_ratio": 0.18,
    }
    params.update(overrides)
    return base_format_parameters(format_name, **params)


def format_parameters(format_name: str) -> FormatParameters:
    if format_name not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format parameters: {format_name}")
    from ..formats import PARAMETER_FACTORIES

    try:
        parameters = PARAMETER_FACTORIES[format_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported format parameters: {format_name}") from exc
    return parameters()

__all__ = [
    "FORMAT_OVERRIDE_PARAMETER_PATHS",
    "base_format_parameters",
    "base_medium_format_parameters",
    "format_parameters",
]
