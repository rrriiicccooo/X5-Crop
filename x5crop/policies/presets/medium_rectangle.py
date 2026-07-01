from __future__ import annotations

from .base import FormatParameters, base_medium_format_parameters


FORMAT_ID = '120-645'


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        separator_first_outer_enabled=True,
        separator_first_outer_min_score=0.60,
        separator_first_outer_band_score=0.38,
        separator_first_outer_spacing_min_ratio=0.84,
        separator_first_outer_spacing_max_ratio=1.20,
        separator_first_outer_frame_error_max=0.14,
        separator_first_outer_max_width_ratio=0.090,
        separator_first_outer_gap_max_width_ratio=0.080,
        separator_first_outer_band_candidates=10,
        separator_first_outer_pair_candidates=3,
        separator_first_outer_max_candidates=8,
        long_axis_edge_anchor_outer_enabled=False,
        long_axis_edge_anchor_outer_mode="fallback",
        long_axis_edge_anchor_ratio_extras=(0.04, 0.08),
        long_axis_edge_anchor_max_candidates=4,
    )
