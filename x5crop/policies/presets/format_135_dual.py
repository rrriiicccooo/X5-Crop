from __future__ import annotations

from .base import FormatParameters


FORMAT_ID = '135-dual'


def parameters() -> FormatParameters:
    return FormatParameters(
        "135-dual",
        separator_gate_profile="all_internal_gaps_hard",
        wide_gap_retry_enabled=False,
        nearby_active_correction=False,
        lucky_pass_risk_enabled=False,
        leading_grid_failure_enabled=False,
        outer_retry_enabled=False,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_partial_enabled=False,
        separator_first_partial_enabled=False,
        floating_outer_partial_enabled=False,
        wide_gap_retry_partial_enabled=False,
        partial_safe_extra_frames_enabled=False,
    )
