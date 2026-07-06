from __future__ import annotations

from ..assembly.format_presets import build_policy_from_format
from ..parameters.aggregate import FormatParameters
from ..parameters.registry import base_medium_format_parameters

FORMAT_ID = "120-67"


def parameters() -> FormatParameters:
    return base_medium_format_parameters(
        FORMAT_ID,
        separator_width_profile_max_width_ratio=0.090,
        outer_align_short_excess_ratio=0.024,
        outer_align_short_requires_hard_anchors=True,
        outer_align_short_content_height_max=0.970,
        separator_outer_min_score=0.58,
        separator_outer_band_score=0.36,
        separator_outer_spacing_min_ratio=0.82,
        separator_outer_spacing_max_ratio=1.24,
        separator_outer_frame_error_max=0.18,
        separator_outer_max_width_ratio=0.110,
        separator_outer_gap_max_width_ratio=0.095,
        partial_edge_ratio_extras=(0.04, 0.08),
        partial_edge_max_candidates=4,
    )


def build_policy(strip_mode: str):
    return build_policy_from_format(FORMAT_ID, parameters, strip_mode)


def full_policy():
    return build_policy("full")


def partial_policy():
    return build_policy("partial")
