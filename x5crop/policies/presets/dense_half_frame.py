from __future__ import annotations

from .base import FormatParameters


FORMAT_ID = 'half'


def parameters() -> FormatParameters:
    return FormatParameters(
        "half",
        score_full_width_cv=0.008,
        content_profile_min_run_ratio=0.16,
        separator_model_grid_credit=0.25,
        separator_model_equal_credit=0.08,
        separator_gate_profile="geometry_support",
        wide_gap_retry_enabled=True,
        wide_gap_retry_max_width_ratio=0.100,
        nearby_active_correction=False,
        lucky_pass_risk_enabled=False,
        leading_grid_failure_enabled=False,
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.68,
        separator_first_outer_band_score=0.48,
        separator_first_outer_spacing_min_ratio=0.90,
        separator_first_outer_spacing_max_ratio=1.12,
        separator_first_outer_frame_error_max=0.08,
        separator_first_outer_max_width_ratio=0.055,
        separator_first_outer_gap_max_width_ratio=0.055,
        separator_first_outer_source_candidates=1,
        separator_first_outer_band_candidates=14,
        separator_first_outer_pair_candidates=2,
        separator_first_outer_max_candidates=4,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.04, 0.06),
        long_axis_edge_anchor_max_candidates=4,
    )
