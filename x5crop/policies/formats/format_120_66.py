from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_medium_format_parameters

FORMAT_ID = "120-66"


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        gap_max_width_max=720,
        separator_width_profile_max_width_ratio=0.140,
        short_axis_geometry_correction_min_error=0.24,
        partial_edge_ratio_extras=(0.06, 0.10),
        partial_edge_max_candidates=6,
        separator_full_width_outer_max_candidates=8,
        separator_full_width_outer_margin_ratios=(0.00, 0.018, 0.035, 0.055),
        separator_full_width_outer_source_candidates=3,
    )
