from __future__ import annotations

from .base import FormatParameters, base_medium_format_parameters


FORMAT_ID = '120-66'


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        score_outer_max_area=1.0,
        score_outer_too_large=1.0,
        score_outer_too_large_cap=0.86,
        calibrate_hard_full_confidence_floor=0.86,
        partial_auto_include_default_count=True,
        gap_max_width_max=720,
        wide_gap_retry_enabled=True,
        wide_gap_retry_max_width_ratio=0.140,
        wide_gap_min_mean=0.90,
        wide_gap_min_prominence=0.015,
        separator_gate_edge_pair_min_score_without_wide=1.0,
        separator_gate_edge_pair_min_score_with_wide=0.0,
        separator_gate_min_wide_gaps_for_auto=0,
        partial_safe_extra_frames_min_wide_like_gaps=2,
        partial_safe_extra_frames_leading_content_check=True,
        partial_safe_extra_frames_frame_content_check=True,
        short_axis_aspect_retry_enabled=True,
        short_axis_aspect_retry_min_error=0.24,
        short_axis_aspect_retry_target_aspect=1.0,
        floating_outer_full_enabled=False,
        floating_outer_partial_enabled=True,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_partial_enabled=True,
        long_axis_edge_anchor_partial_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.06, 0.10),
        long_axis_edge_anchor_max_candidates=6,
        separator_first_outer_enabled=True,
        separator_first_outer_mode="fallback",
        separator_first_partial_enabled=True,
        separator_first_partial_mode="always",
        separator_geometry_outer_partial_mode="conditional",
        separator_geometry_outer_count=3,
        separator_geometry_outer_max_candidates=8,
        separator_geometry_outer_margin_ratios=(0.00, 0.018, 0.035, 0.055),
        separator_geometry_outer_source_candidates=3,
    )
