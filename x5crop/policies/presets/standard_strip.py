from __future__ import annotations

from .base import FormatParameters


FORMAT_ID = '135'


def parameters() -> FormatParameters:
    return FormatParameters(
        "135",
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.72,
        separator_first_outer_band_score=0.52,
        separator_first_outer_spacing_min_ratio=0.92,
        separator_first_outer_spacing_max_ratio=1.10,
        separator_first_outer_frame_error_max=0.07,
        separator_first_outer_max_width_ratio=0.050,
        separator_first_outer_gap_max_width_ratio=0.060,
        separator_first_outer_source_candidates=1,
        separator_first_outer_band_candidates=12,
        separator_first_outer_pair_candidates=2,
        separator_first_outer_max_candidates=4,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.02, 0.04),
        long_axis_edge_anchor_max_candidates=4,
    )
