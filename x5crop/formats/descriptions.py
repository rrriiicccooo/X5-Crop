from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatDescription:
    full_mode_behavior: str
    partial_mode_behavior: str
    outer_trust_profile: str
    separator_visibility: str
    geometry_tolerance: str
    known_physical_notes: tuple[str, ...]


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
        separator_visibility="few_variable_width_internal_gaps",
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
        separator_visibility="variable_width_internal_separators",
        geometry_tolerance="square_frame_spacing_sensitive",
        known_physical_notes=(
            "separator_width_variation_can_compete_with_frame_boundaries",
            "holder_edge_can_mimic_separator",
            "overlap_or_stuck_frame_note",
        ),
    ),
    "120-67": FormatDescription(
        full_mode_behavior="fixed nominal 3-frame strip",
        partial_mode_behavior="review-biased count search with uncertain leading/trailing edges",
        outer_trust_profile="medium_format_broad_separator_width_guarded",
        separator_visibility="variable_width_internal_gaps",
        geometry_tolerance="medium_format_aspect_sensitive",
        known_physical_notes=(
            "short_axis_correction_can_overtrust_holder",
            "separator_width_variation_may_compete_with_content",
        ),
    ),
}
