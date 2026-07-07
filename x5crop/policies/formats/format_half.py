from __future__ import annotations

from ..assembly.format_presets import build_policy_from_format
from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_format_parameters

FORMAT_ID = "half"


def parameters() -> FormatParameters:
    return base_format_parameters(
        FORMAT_ID,
        content_profile_min_run_ratio=0.16,
        separator_width_profile_max_width_ratio=0.100,
        separator_outer_min_score=0.68,
        separator_outer_band_score=0.48,
        separator_outer_spacing_min_ratio=0.90,
        separator_outer_spacing_max_ratio=1.12,
        separator_outer_frame_error_max=0.08,
        separator_outer_max_width_ratio=0.055,
        separator_outer_gap_max_width_ratio=0.055,
        separator_outer_source_candidates=1,
        separator_outer_band_candidates=14,
        separator_outer_pair_candidates=2,
        separator_outer_max_candidates=4,
        partial_edge_ratio_extras=(0.04, 0.06),
        partial_edge_max_candidates=4,
    )


def build_policy(strip_mode: str):
    return build_policy_from_format(FORMAT_ID, parameters, strip_mode)
