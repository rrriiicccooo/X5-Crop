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
class FrameSizeMm:
    width_mm: float
    height_mm: float
    label: str = "nominal"

    @property
    def aspect(self) -> float:
        return float(self.width_mm) / float(self.height_mm)


@dataclass(frozen=True)
class FormatSpec:
    format_id: FormatId
    name: str
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str
    frame_size_mm_options: tuple[FrameSizeMm, ...]
    expected_separator_count: int
    physical_layout: str = "single_strip"
    separator_width_profile: str = "standard"
    frame_fit_profile: str = "standard_strip"
    edge_pair_profile: str = "standard_35mm"
    geometry_support_profile: str = "none"
    output_overlap_profile: str = "standard"
    complete_strip_can_be_underfilled: bool = False

    @property
    def nominal_frame_size_mm(self) -> FrameSizeMm:
        return self.frame_size_mm_options[0]

    @property
    def horizontal_content_aspect(self) -> float:
        return self.nominal_frame_size_mm.aspect

    @property
    def frame_aspect(self) -> float:
        return self.horizontal_content_aspect


@dataclass(frozen=True)
class FormatDescription:
    full_mode_behavior: str
    partial_mode_behavior: str
    outer_trust_profile: str
    separator_visibility: str
    geometry_tolerance: str
    known_physical_notes: tuple[str, ...]


FormatPhysicalSpec = FormatSpec


def expected_separator_count(format_id: str, default_count: int) -> int:
    if format_id == FormatId.DUAL_LANE.value:
        return 10
    return max(0, int(default_count) - 1)


def _format_spec(
    format_id: FormatId,
    default_count: int,
    allowed_counts: tuple[int, ...],
    family: str,
    nominal_frame_size_mm: FrameSizeMm,
    frame_size_mm_options: tuple[FrameSizeMm, ...] = (),
    physical_layout: str = "single_strip",
    separator_width_profile: str = "standard",
    frame_fit_profile: str = "standard_strip",
    edge_pair_profile: str = "standard_35mm",
    geometry_support_profile: str = "none",
    output_overlap_profile: str = "standard",
    complete_strip_can_be_underfilled: bool = False,
) -> FormatSpec:
    name = format_id.value
    return FormatSpec(
        format_id=format_id,
        name=name,
        default_count=default_count,
        allowed_counts=allowed_counts,
        family=family,
        frame_size_mm_options=frame_size_mm_options or (nominal_frame_size_mm,),
        expected_separator_count=expected_separator_count(name, default_count),
        physical_layout=physical_layout,
        separator_width_profile=separator_width_profile,
        frame_fit_profile=frame_fit_profile,
        edge_pair_profile=edge_pair_profile,
        geometry_support_profile=geometry_support_profile,
        output_overlap_profile=output_overlap_profile,
        complete_strip_can_be_underfilled=complete_strip_can_be_underfilled,
    )


FORMATS: dict[str, FormatSpec] = {
    "135": _format_spec(
        FormatId.STANDARD_STRIP,
        6,
        tuple(range(1, 7)),
        "35mm",
        FrameSizeMm(36.0, 24.0),
        frame_fit_profile="standard_strip",
        edge_pair_profile="standard_35mm",
    ),
    "135-dual": _format_spec(
        FormatId.DUAL_LANE,
        12,
        (12,),
        "35mm",
        FrameSizeMm(36.0, 24.0),
        physical_layout="dual_lane",
        frame_fit_profile="dual_lane",
        edge_pair_profile="standard_35mm",
    ),
    "half": _format_spec(
        FormatId.HALF,
        12,
        tuple(range(1, 13)),
        "35mm",
        FrameSizeMm(18.0, 24.0),
        frame_fit_profile="dense_half",
        edge_pair_profile="dense_half",
        geometry_support_profile="stable_dense_grid",
        output_overlap_profile="sensitive",
    ),
    "xpan": _format_spec(
        FormatId.XPAN,
        3,
        (1, 2, 3),
        "35mm",
        FrameSizeMm(65.0, 24.0),
        frame_fit_profile="panoramic_35mm",
        edge_pair_profile="panoramic_35mm",
        complete_strip_can_be_underfilled=True,
    ),
    "120-645": _format_spec(
        FormatId.MEDIUM_RECTANGLE,
        4,
        (1, 2, 3, 4),
        "120",
        FrameSizeMm(42.0, 56.0),
        frame_fit_profile="medium_rectangle",
        edge_pair_profile="medium_rectangle",
        output_overlap_profile="sensitive",
    ),
    "120-66": _format_spec(
        FormatId.MEDIUM_SQUARE,
        3,
        (1, 2, 3),
        "120",
        FrameSizeMm(56.0, 56.0),
        frame_size_mm_options=(
            FrameSizeMm(56.0, 56.0),
            FrameSizeMm(54.0, 54.0, label="camera_variant"),
        ),
        separator_width_profile="broad",
        frame_fit_profile="medium_square",
        edge_pair_profile="medium_square",
        output_overlap_profile="sensitive",
        complete_strip_can_be_underfilled=True,
    ),
    "120-67": _format_spec(
        FormatId.MEDIUM_WIDE,
        3,
        (1, 2, 3),
        "120",
        FrameSizeMm(70.0, 56.0),
        separator_width_profile="broad",
        frame_fit_profile="medium_wide",
        edge_pair_profile="medium_square",
        output_overlap_profile="sensitive",
    ),
}

FORMAT_DESCRIPTIONS: dict[str, FormatDescription] = {
    "135": FormatDescription(
        full_mode_behavior="fixed nominal 6-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="moderate_white_holder_boundary",
        separator_visibility="narrow_or_mixed_internal_gaps",
        geometry_tolerance="tight_repeated_35mm_frames",
        known_physical_notes=(
            "wide_spacing_can_mimic_extra_holder",
            "weak_grid_may_hide_missing_separator",
        ),
    ),
    "135-dual": FormatDescription(
        full_mode_behavior="fixed nominal 12-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="two_lane_holder_boundary",
        separator_visibility="per_lane_narrow_internal_gaps",
        geometry_tolerance="two_independent_35mm_lanes",
        known_physical_notes=(
            "lane_split_failure",
            "partial_dual_lane_not_trusted",
        ),
    ),
    "half": FormatDescription(
        full_mode_behavior="fixed nominal 12-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="long_dense_strip_boundary",
        separator_visibility="many_small_internal_gaps",
        geometry_tolerance="tight_many_frame_grid",
        known_physical_notes=(
            "weak_grid_can_overfit_dense_frames",
            "partial_edges_may_include_holder",
        ),
    ),
    "xpan": FormatDescription(
        full_mode_behavior="fixed nominal 3-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="wide_frame_holder_boundary",
        separator_visibility="few_wide_internal_gaps",
        geometry_tolerance="wide_frame_aspect_sensitive",
        known_physical_notes=(
            "wide_content_can_mask_separator",
            "outer_overcrop_cost_high",
        ),
    ),
    "120-645": FormatDescription(
        full_mode_behavior="fixed nominal 4-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="medium_format_holder_boundary",
        separator_visibility="moderate_internal_gaps",
        geometry_tolerance="medium_format_aspect_sensitive",
        known_physical_notes=(
            "short_axis_boundary_can_blend_with_holder",
            "content_edges_can_look_like_separators",
        ),
    ),
    "120-66": FormatDescription(
        full_mode_behavior="fixed nominal 3-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="square_frame_holder_boundary_guarded",
        separator_visibility="broad_internal_separator_widths",
        geometry_tolerance="square_frame_spacing_sensitive",
        known_physical_notes=(
            "broad_separator_width_can_be_false_frame_boundary",
            "holder_edge_can_mimic_separator",
            "overlap_or_stuck_frame_note",
        ),
    ),
    "120-67": FormatDescription(
        full_mode_behavior="fixed nominal 3-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="medium_format_broad_separator_width_guarded",
        separator_visibility="broad_internal_gap_widths_expected",
        geometry_tolerance="medium_format_aspect_sensitive",
        known_physical_notes=(
            "short_axis_correction_can_overtrust_holder",
            "broad_separator_width_may_compete_with_content",
        ),
    ),
}

FORMAT_CHOICES = tuple(FORMATS.keys())
LAYOUT_CHOICES = ("auto", "horizontal", "vertical")
STRIP_CHOICES = ("full", "partial")
DESKEW_CHOICES = ("off", "auto")
DESKEW_FALLBACK_CHOICES = ("off", "auto", "always")
COMPRESSION_CHOICES = ("none", "same")
CONTENT_ASPECTS_HORIZONTAL = {
    key: spec.horizontal_content_aspect
    for key, spec in FORMATS.items()
    if spec.horizontal_content_aspect is not None
}


def format_spec(format_id: str | FormatId) -> FormatSpec:
    key = format_id.value if isinstance(format_id, FormatId) else str(format_id)
    return FORMATS[key]


def format_description(format_id: str | FormatId) -> FormatDescription:
    key = format_id.value if isinstance(format_id, FormatId) else str(format_id)
    return FORMAT_DESCRIPTIONS[key]


__all__ = [
    "COMPRESSION_CHOICES",
    "CONTENT_ASPECTS_HORIZONTAL",
    "DESKEW_CHOICES",
    "DESKEW_FALLBACK_CHOICES",
    "FORMAT_CHOICES",
    "FORMAT_DESCRIPTIONS",
    "FORMATS",
    "LAYOUT_CHOICES",
    "STRIP_CHOICES",
    "FrameSizeMm",
    "FormatId",
    "FormatDescription",
    "FormatPhysicalSpec",
    "FormatSpec",
    "StripMode",
    "expected_separator_count",
    "format_description",
    "format_spec",
]
