from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .format_specs import (
    CONTENT_ASPECTS_HORIZONTAL,
    FORMAT_CHOICES,
    FORMATS,
    STRIP_CHOICES,
    FilmFormat,
)
from .policies.parameters import FormatParameters, format_parameters


class FormatId(str, Enum):
    STANDARD_STRIP = "135"
    PARALLEL_LANE = "135-dual"
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
    parameters: FormatParameters


FORMAT_PHYSICAL_SPECS: dict[str, dict[str, object]] = {
    "135": {
        "outer_trust_profile": "moderate_white_holder_boundary",
        "separator_visibility": "narrow_or_mixed_internal_gaps",
        "geometry_tolerance": "tight_repeated_35mm_frames",
        "known_physical_risks": (
            "wide_spacing_can_mimic_extra_holder",
            "weak_grid_may_hide_missing_separator",
        ),
    },
    "135-dual": {
        "outer_trust_profile": "two_lane_holder_boundary",
        "separator_visibility": "per_lane_narrow_internal_gaps",
        "geometry_tolerance": "two_independent_35mm_lanes",
        "known_physical_risks": (
            "lane_split_failure",
            "partial_dual_lane_not_trusted",
        ),
    },
    "half": {
        "outer_trust_profile": "long_dense_strip_boundary",
        "separator_visibility": "many_small_internal_gaps",
        "geometry_tolerance": "tight_many_frame_grid",
        "known_physical_risks": (
            "weak_grid_can_overfit_dense_frames",
            "partial_edges_may_include_holder",
        ),
    },
    "xpan": {
        "outer_trust_profile": "wide_frame_holder_boundary",
        "separator_visibility": "few_wide_internal_gaps",
        "geometry_tolerance": "wide_frame_aspect_sensitive",
        "known_physical_risks": (
            "wide_content_can_mask_separator",
            "outer_overcrop_cost_high",
        ),
    },
    "120-645": {
        "outer_trust_profile": "medium_format_holder_boundary",
        "separator_visibility": "moderate_internal_gaps",
        "geometry_tolerance": "medium_format_aspect_sensitive",
        "known_physical_risks": (
            "short_axis_boundary_can_blend_with_holder",
            "content_edges_can_look_like_separators",
        ),
    },
    "120-66": {
        "outer_trust_profile": "square_frame_dark_boundary_guarded",
        "separator_visibility": "dark_band_or_wide_internal_gaps",
        "geometry_tolerance": "square_frame_spacing_sensitive",
        "known_physical_risks": (
            "dark_band_can_be_false_frame_boundary",
            "holder_edge_can_mimic_separator",
            "overlap_or_stuck_frame_risk",
        ),
    },
    "120-67": {
        "outer_trust_profile": "medium_format_wide_separator_guarded",
        "separator_visibility": "wide_internal_gaps_expected",
        "geometry_tolerance": "medium_format_aspect_sensitive",
        "known_physical_risks": (
            "short_axis_retry_can_overtrust_holder",
            "wide_separator_may_compete_with_content",
        ),
    },
}


def expected_separator_count(format_id: str, default_count: int) -> int:
    if format_id == FormatId.PARALLEL_LANE.value:
        return 10
    return max(0, int(default_count) - 1)


def format_spec(format_id: str | FormatId) -> FormatSpec:
    key = format_id.value if isinstance(format_id, FormatId) else str(format_id)
    fmt = FORMATS[key]
    physical = FORMAT_PHYSICAL_SPECS[key]
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(key)
    return FormatSpec(
        format_id=FormatId(key),
        name=fmt.name,
        default_count=fmt.default_count,
        allowed_counts=fmt.allowed_counts,
        family=fmt.family,
        horizontal_content_aspect=aspect,
        frame_aspect=aspect,
        expected_separator_count=expected_separator_count(key, fmt.default_count),
        full_mode_behavior=f"fixed nominal {fmt.default_count}-frame strip",
        partial_mode_behavior=(
            "review-biased count search with uncertain leading/trailing edges"
        ),
        outer_trust_profile=str(physical["outer_trust_profile"]),
        separator_visibility=str(physical["separator_visibility"]),
        geometry_tolerance=str(physical["geometry_tolerance"]),
        known_physical_risks=tuple(str(item) for item in physical["known_physical_risks"]),
        parameters=format_parameters(key),
    )


__all__ = [
    "CONTENT_ASPECTS_HORIZONTAL",
    "FORMAT_CHOICES",
    "FORMATS",
    "STRIP_CHOICES",
    "FilmFormat",
    "FormatId",
    "FormatSpec",
    "FormatParameters",
    "FORMAT_PHYSICAL_SPECS",
    "StripMode",
    "expected_separator_count",
    "format_spec",
    "format_parameters",
]
