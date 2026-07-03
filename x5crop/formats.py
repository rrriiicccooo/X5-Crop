from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FormatId(str, Enum):
    STANDARD_STRIP = "135"
    DUAL_LANE = "135-dual"
    HALF = "half"
    XPAN = "xpan"
    MEDIUM_RECTANGLE = "120-645"
    MEDIUM_SQUARE = "120-66"
    MEDIUM_WIDE = "120-67"


class StripMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


@dataclass(frozen=True)
class FormatSpec:
    format_id: FormatId
    name: str
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str
    horizontal_content_aspect: float | None
    frame_aspect: float | None
    expected_separator_count: int
    full_mode_behavior: str
    partial_mode_behavior: str
    outer_trust_profile: str
    separator_visibility: str
    geometry_tolerance: str
    known_physical_risks: tuple[str, ...]


def expected_separator_count(format_id: str, default_count: int) -> int:
    if format_id == FormatId.DUAL_LANE.value:
        return 10
    return max(0, int(default_count) - 1)


def _format_spec(
    format_id: FormatId,
    default_count: int,
    allowed_counts: tuple[int, ...],
    family: str,
    horizontal_content_aspect: float,
    outer_trust_profile: str,
    separator_visibility: str,
    geometry_tolerance: str,
    known_physical_risks: tuple[str, ...],
) -> FormatSpec:
    name = format_id.value
    return FormatSpec(
        format_id=format_id,
        name=name,
        default_count=default_count,
        allowed_counts=allowed_counts,
        family=family,
        horizontal_content_aspect=horizontal_content_aspect,
        frame_aspect=horizontal_content_aspect,
        expected_separator_count=expected_separator_count(name, default_count),
        full_mode_behavior=f"fixed nominal {default_count}-frame strip",
        partial_mode_behavior=(
            "review-biased count search with uncertain leading/trailing edges"
        ),
        outer_trust_profile=outer_trust_profile,
        separator_visibility=separator_visibility,
        geometry_tolerance=geometry_tolerance,
        known_physical_risks=known_physical_risks,
    )


FORMATS: dict[str, FormatSpec] = {
    "135": _format_spec(
        FormatId.STANDARD_STRIP,
        6,
        tuple(range(1, 7)),
        "35mm",
        3.0 / 2.0,
        "moderate_white_holder_boundary",
        "narrow_or_mixed_internal_gaps",
        "tight_repeated_35mm_frames",
        (
            "wide_spacing_can_mimic_extra_holder",
            "weak_grid_may_hide_missing_separator",
        ),
    ),
    "135-dual": _format_spec(
        FormatId.DUAL_LANE,
        12,
        (12,),
        "35mm",
        3.0 / 2.0,
        "two_lane_holder_boundary",
        "per_lane_narrow_internal_gaps",
        "two_independent_35mm_lanes",
        (
            "lane_split_failure",
            "partial_dual_lane_not_trusted",
        ),
    ),
    "half": _format_spec(
        FormatId.HALF,
        12,
        tuple(range(1, 13)),
        "35mm",
        2.0 / 3.0,
        "long_dense_strip_boundary",
        "many_small_internal_gaps",
        "tight_many_frame_grid",
        (
            "weak_grid_can_overfit_dense_frames",
            "partial_edges_may_include_holder",
        ),
    ),
    "xpan": _format_spec(
        FormatId.XPAN,
        3,
        (1, 2, 3),
        "35mm",
        65.0 / 24.0,
        "wide_frame_holder_boundary",
        "few_wide_internal_gaps",
        "wide_frame_aspect_sensitive",
        (
            "wide_content_can_mask_separator",
            "outer_overcrop_cost_high",
        ),
    ),
    "120-645": _format_spec(
        FormatId.MEDIUM_RECTANGLE,
        4,
        (1, 2, 3, 4),
        "120",
        3.0 / 4.0,
        "medium_format_holder_boundary",
        "moderate_internal_gaps",
        "medium_format_aspect_sensitive",
        (
            "short_axis_boundary_can_blend_with_holder",
            "content_edges_can_look_like_separators",
        ),
    ),
    "120-66": _format_spec(
        FormatId.MEDIUM_SQUARE,
        3,
        (1, 2, 3),
        "120",
        1.0,
        "square_frame_holder_boundary_guarded",
        "broad_internal_separator_widths",
        "square_frame_spacing_sensitive",
        (
            "broad_separator_width_can_be_false_frame_boundary",
            "holder_edge_can_mimic_separator",
            "overlap_or_stuck_frame_risk",
        ),
    ),
    "120-67": _format_spec(
        FormatId.MEDIUM_WIDE,
        3,
        (1, 2, 3),
        "120",
        5.0 / 4.0,
        "medium_format_broad_separator_width_guarded",
        "broad_internal_gap_widths_expected",
        "medium_format_aspect_sensitive",
        (
            "short_axis_retry_can_overtrust_holder",
            "broad_separator_width_may_compete_with_content",
        ),
    ),
}

FORMAT_CHOICES = tuple(FORMATS.keys())
LAYOUT_CHOICES = ("auto", "horizontal", "vertical")
STRIP_CHOICES = ("full", "partial")
DESKEW_CHOICES = ("off", "auto")
ANALYSIS_CHOICES = ("off", "auto", "always")
COMPRESSION_CHOICES = ("none", "same")
CONTENT_ASPECTS_HORIZONTAL = {
    key: spec.horizontal_content_aspect
    for key, spec in FORMATS.items()
    if spec.horizontal_content_aspect is not None
}


def format_spec(format_id: str | FormatId) -> FormatSpec:
    key = format_id.value if isinstance(format_id, FormatId) else str(format_id)
    return FORMATS[key]


__all__ = [
    "ANALYSIS_CHOICES",
    "COMPRESSION_CHOICES",
    "CONTENT_ASPECTS_HORIZONTAL",
    "DESKEW_CHOICES",
    "FORMAT_CHOICES",
    "FORMATS",
    "LAYOUT_CHOICES",
    "STRIP_CHOICES",
    "FormatId",
    "FormatSpec",
    "StripMode",
    "expected_separator_count",
    "format_spec",
]
