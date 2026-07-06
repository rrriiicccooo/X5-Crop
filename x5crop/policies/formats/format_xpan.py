from __future__ import annotations

from ..assembly.format_presets import build_policy_from_format
from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_format_parameters

FORMAT_ID = "xpan"


def parameters() -> FormatParameters:
    return base_format_parameters(
        FORMAT_ID,
        outer_align_long_margin_ratio=0.008,
        outer_align_long_margin_cap_ratio=0.012,
        content_profile_min_run_ratio=0.24,
        separator_outer_min_score=0.66,
        separator_outer_band_score=0.44,
        separator_outer_spacing_min_ratio=0.86,
        separator_outer_spacing_max_ratio=1.16,
        separator_outer_frame_error_max=0.10,
        separator_outer_max_width_ratio=0.045,
        separator_outer_gap_max_width_ratio=0.060,
        separator_outer_source_candidates=1,
        separator_outer_band_candidates=8,
        separator_outer_pair_candidates=3,
        separator_outer_max_candidates=4,
        partial_edge_ratio_extras=(0.03, 0.06),
        partial_edge_max_candidates=4,
    )


def build_policy(strip_mode: str):
    return build_policy_from_format(FORMAT_ID, parameters, strip_mode)


def full_policy():
    return build_policy("full")


def partial_policy():
    return build_policy("partial")
