from __future__ import annotations

from .base import FormatParameters


FORMAT_ID = 'xpan'


def parameters() -> FormatParameters:
    return FormatParameters(
        "xpan",
        outer_align_long_margin_ratio=0.008,
        outer_align_long_margin_cap_ratio=0.012,
        content_profile_min_run_ratio=0.24,
        separator_model_grid_credit=0.20,
        separator_model_equal_credit=0.06,
        separator_gate_profile="all_internal_gaps_hard",
        wide_gap_retry_enabled=False,
        partial_auto_include_default_count=True,
        separator_first_partial_mode="always",
        nearby_active_correction=False,
        lucky_pass_risk_enabled=False,
        leading_grid_failure_enabled=False,
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.66,
        separator_first_outer_band_score=0.44,
        separator_first_outer_spacing_min_ratio=0.86,
        separator_first_outer_spacing_max_ratio=1.16,
        separator_first_outer_frame_error_max=0.10,
        separator_first_outer_max_width_ratio=0.045,
        separator_first_outer_gap_max_width_ratio=0.060,
        separator_first_outer_source_candidates=1,
        separator_first_outer_band_candidates=8,
        separator_first_outer_pair_candidates=3,
        separator_first_outer_max_candidates=4,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_partial_enabled=True,
        long_axis_edge_anchor_partial_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.03, 0.06),
        long_axis_edge_anchor_max_candidates=4,
    )
