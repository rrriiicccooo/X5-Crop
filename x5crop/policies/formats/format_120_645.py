from __future__ import annotations

from ..assembly.format_presets import build_policy_from_format
from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_medium_format_parameters

FORMAT_ID = "120-645"


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        separator_outer_min_score=0.60,
        separator_outer_band_score=0.38,
        separator_outer_spacing_min_ratio=0.84,
        separator_outer_spacing_max_ratio=1.20,
        separator_outer_frame_error_max=0.14,
        separator_outer_max_width_ratio=0.090,
        separator_outer_gap_max_width_ratio=0.080,
        separator_outer_band_candidates=10,
        separator_outer_pair_candidates=3,
        separator_outer_max_candidates=8,
        partial_edge_ratio_extras=(0.04, 0.08),
        partial_edge_max_candidates=4,
    )


def build_policy(strip_mode: str):
    return build_policy_from_format(FORMAT_ID, parameters, strip_mode)
