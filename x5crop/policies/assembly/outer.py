from __future__ import annotations

from ...formats import FormatSpec
from ...geometry.detection_parameters import OuterBoxDetectionParameters, OuterMaskProfileParameters
from .presets import ModePolicyPreset
from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL
from ..runtime.outer import (
    BaseOuterProposalPolicy,
    ContentContainmentCorrectionPolicy,
    EdgeAnchoredContentPositionPolicy,
    FloatingContentPositionPolicy,
    FullWidthSeparatorOuterPolicy,
    GeometryConsistencyCorrectionPolicy,
    GeometryOuterProposalPolicy,
    GridOuterRefinePolicy,
    LongAxisGeometryCorrectionPolicy,
    OuterAlignmentEvidencePolicy,
    OuterCorrectionFamilyPolicy,
    OuterCorrectionPolicy,
    OuterPolicy,
    OuterProposalPolicy,
    PartialPlacementGeometryPolicy,
    SeparatorOuterBandPolicy,
    SeparatorOuterFamilyPolicy,
    SeparatorGeometryProposalPolicy,
    ShortAxisGeometryCorrectionPolicy,
)


def separator_outer_family_policies(
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> tuple[SeparatorOuterFamilyPolicy, SeparatorOuterFamilyPolicy, SeparatorOuterFamilyPolicy]:
    is_standard_strip = mode_preset.detector_kind == "standard_strip"
    width_profile = params.separator.separator_width_profile
    full_width_outer = params.outer.separator_full_width_outer
    width_profile_enabled = bool(width_profile.full_enabled or width_profile.partial_enabled)
    return (
        SeparatorOuterFamilyPolicy(
            mode="always" if is_standard_strip else "off",
            phase="primary",
            requires_explicit_count_for_partial=False,
            max_candidates=0,
        ),
        SeparatorOuterFamilyPolicy(
            mode="conditional" if is_standard_strip else "off",
            phase="extension",
            requires_explicit_count_for_partial=True,
            max_candidates=int(full_width_outer.max_candidates),
        ),
        SeparatorOuterFamilyPolicy(
            mode="conditional" if is_standard_strip and width_profile_enabled else "off",
            phase="supplemental",
            requires_explicit_count_for_partial=True,
            max_candidates=0,
        ),
    )


def outer_correction_family_policies(
    mode_preset: ModePolicyPreset,
    strip_mode: str,
    long_axis,
) -> tuple[OuterCorrectionFamilyPolicy, OuterCorrectionFamilyPolicy, OuterCorrectionFamilyPolicy]:
    is_standard_strip = mode_preset.detector_kind == "standard_strip"
    long_and_content_strip_modes = (FULL, PARTIAL)
    long_mode = "conditional" if is_standard_strip else "off"
    short_mode = "conditional" if is_standard_strip else "off"
    content_mode = "conditional" if is_standard_strip else "off"
    return (
        OuterCorrectionFamilyPolicy(
            mode=long_mode,
            phase="geometry_consistency",
            requires_explicit_count_for_partial=True,
            strip_modes=long_and_content_strip_modes,
            requires_separator_assessment=True,
            requires_complete_hard_gaps=True,
            allowed_axes=("long",),
            max_shrink_ratio=float(long_axis.max_shrink_ratio),
            max_expand_ratio=0.0,
        ),
        OuterCorrectionFamilyPolicy(
            mode=short_mode,
            phase="geometry_consistency",
            requires_explicit_count_for_partial=True,
            strip_modes=(FULL, PARTIAL),
            requires_separator_assessment=True,
            requires_complete_hard_gaps=False,
            allowed_axes=("short",),
            max_shrink_ratio=0.0,
            max_expand_ratio=0.60,
        ),
        OuterCorrectionFamilyPolicy(
            mode=content_mode,
            phase="content_containment",
            requires_explicit_count_for_partial=True,
            strip_modes=long_and_content_strip_modes,
            requires_separator_assessment=True,
            requires_complete_hard_gaps=False,
            allowed_axes=("long", "short"),
            max_shrink_ratio=float(long_axis.max_shrink_ratio),
            max_expand_ratio=0.0,
        ),
    )


def outer_policy(
    mode_preset: ModePolicyPreset,
    strip_mode: str,
    params: FormatParameters,
    fmt: FormatSpec,
) -> OuterPolicy:
    outer = params.outer.outer_strategy
    long_axis = params.outer.long_axis_geometry_correction
    grid_refine = params.outer.grid_outer_refine
    short_axis = params.outer.short_axis_geometry_correction
    content_containment = params.outer.content_containment_correction
    outer_alignment = params.outer.outer_alignment_evidence
    floating_position = params.outer.floating_content_position
    edge_position = params.outer.edge_anchored_content_position
    base_candidates = params.outer.base_outer_candidates
    separator_outer = params.outer.separator_outer_band
    separator_full_width = params.outer.separator_full_width_outer
    partial_content_enabled = bool(strip_mode == PARTIAL and mode_preset.detector_kind != "review_only")
    separator_width_profile = mode_preset.separator_width_profile
    local_family, full_width_family, width_profile_family = separator_outer_family_policies(mode_preset, params)
    long_correction_family, short_correction_family, content_correction_family = outer_correction_family_policies(
        mode_preset,
        strip_mode,
        long_axis,
    )
    short_target_aspect = (
        float(short_axis.target_aspect)
        if float(short_axis.target_aspect) > 0.0
        else float(fmt.horizontal_content_aspect or 1.0)
    )
    return OuterPolicy(
        proposal=OuterProposalPolicy(
            base=BaseOuterProposalPolicy(
                enabled=True,
                candidates=OuterBoxDetectionParameters(
                    white_x_width_multiplier=float(base_candidates.white_x_width_multiplier),
                    white_x_extra_ratio=float(base_candidates.white_x_extra_ratio),
                    candidate_max_area=float(base_candidates.candidate_max_area),
                    mask_expand_ratio=float(base_candidates.mask_expand_ratio),
                    mask_profiles=tuple(
                        OuterMaskProfileParameters(
                            name=profile.name,
                            low=profile.low,
                            high=profile.high,
                            min_row_fraction=float(profile.min_row_fraction),
                            min_col_fraction=float(profile.min_col_fraction),
                        )
                        for profile in base_candidates.mask_profiles
                    ),
                    min_width_ratio=float(base_candidates.min_width_ratio),
                    min_height_ratio=float(base_candidates.min_height_ratio),
                    min_width_px=int(base_candidates.min_width_px),
                    min_height_px=int(base_candidates.min_height_px),
                    bw_not_white_threshold=int(base_candidates.bw_not_white_threshold),
                    bw_dark_threshold=int(base_candidates.bw_dark_threshold),
                    bw_min_fraction=float(base_candidates.bw_min_fraction),
                    bw_min_width_ratio=float(base_candidates.bw_min_width_ratio),
                    bw_min_height_ratio=float(base_candidates.bw_min_height_ratio),
                    bw_margin_ratio=float(base_candidates.bw_margin_ratio),
                    bw_margin_min=int(base_candidates.bw_margin_min),
                    white_border_ratio=float(base_candidates.white_border_ratio),
                    white_run_ratio=float(base_candidates.white_run_ratio),
                    white_run_min=int(base_candidates.white_run_min),
                    white_run_max=int(base_candidates.white_run_max),
                    white_dark_threshold=int(base_candidates.white_dark_threshold),
                    white_light_threshold=int(base_candidates.white_light_threshold),
                    white_min_width_ratio=float(base_candidates.white_min_width_ratio),
                    white_min_height_ratio=float(base_candidates.white_min_height_ratio),
                    white_margin_ratio=float(base_candidates.white_margin_ratio),
                    white_margin_min=int(base_candidates.white_margin_min),
                ),
            ),
            geometry=GeometryOuterProposalPolicy(
                partial_placement=PartialPlacementGeometryPolicy(
                    enabled=partial_content_enabled,
                    floating=FloatingContentPositionPolicy(
                        enabled=partial_content_enabled,
                        ratio_extras=tuple(float(value) for value in floating_position.ratio_extras),
                        content_threshold=int(floating_position.content_threshold),
                        content_margin_ratio=float(floating_position.content_margin_ratio),
                        content_margin_min=int(floating_position.content_margin_min),
                        content_margin_max=int(floating_position.content_margin_max),
                        min_width_ratio=float(floating_position.min_width_ratio),
                        max_candidates=int(floating_position.max_candidates),
                    ),
                    edge_anchor=EdgeAnchoredContentPositionPolicy(
                        enabled=partial_content_enabled,
                        partial_center_ratio=float(edge_position.partial_center_ratio),
                        ratio_extras=tuple(float(value) for value in edge_position.ratio_extras),
                        content_threshold=int(edge_position.content_threshold),
                        content_margin_ratio=float(edge_position.content_margin_ratio),
                        content_margin_min=int(edge_position.content_margin_min),
                        content_margin_max=int(edge_position.content_margin_max),
                        min_width_ratio=float(edge_position.min_width_ratio),
                        max_candidates=int(edge_position.max_candidates),
                    ),
                ),
                separator=SeparatorGeometryProposalPolicy(
                    local=local_family,
                    full_width=full_width_family,
                    width_profile_family=width_profile_family,
                    separator_outer_allow_oversized_band=separator_width_profile.separator_outer_allow_oversized_band,
                    separator_outer_oversized_band_max_ratio=separator_width_profile.separator_outer_oversized_band_max_ratio,
                    separator_outer_oversized_band_score_penalty=separator_width_profile.separator_outer_oversized_band_score_penalty,
                    separator_gap_search_max_width_ratio=float(outer.separator_gap_search_max_width_ratio),
                    band=SeparatorOuterBandPolicy(
                        min_score=float(separator_outer.min_score),
                        band_score=float(separator_outer.band_score),
                        min_width_ratio=float(separator_outer.min_width_ratio),
                        max_width_ratio=float(separator_outer.max_width_ratio),
                        spacing_min_ratio=float(separator_outer.spacing_min_ratio),
                        spacing_max_ratio=float(separator_outer.spacing_max_ratio),
                        frame_error_max=float(separator_outer.frame_error_max),
                        edge_margin_ratio=float(separator_outer.edge_margin_ratio),
                        source_candidate_count=int(separator_outer.source_candidate_count),
                        band_candidate_count=int(separator_outer.band_candidate_count),
                        pair_candidate_count=int(separator_outer.pair_candidate_count),
                        max_candidates=int(separator_outer.max_candidates),
                        sequence_pair_score_weight=float(separator_outer.sequence_pair_score_weight),
                        edge_margin_min_px=float(separator_outer.edge_margin_min_px),
                        edge_margin_max_short_axis_ratio=float(separator_outer.edge_margin_max_short_axis_ratio),
                        prominence_min=float(separator_outer.prominence_min),
                        high_mean_prominence_bypass=float(separator_outer.high_mean_prominence_bypass),
                        prominence_score_weight=float(separator_outer.prominence_score_weight),
                    ),
                    full_width_outer=FullWidthSeparatorOuterPolicy(
                        required_count=int(separator_full_width.required_count),
                        source_candidate_count=int(separator_full_width.source_candidate_count),
                        margin_ratios=tuple(float(value) for value in separator_full_width.margin_ratios),
                        max_candidates=int(separator_full_width.max_candidates),
                    ),
                ),
                grid_refine=GridOuterRefinePolicy(
                    shift_ratio=float(grid_refine.shift_ratio),
                    shift_min=int(grid_refine.shift_min),
                    shift_max=int(grid_refine.shift_max),
                    max_width_change=float(grid_refine.max_width_change),
                ),
            ),
        ),
        correction=OuterCorrectionPolicy(
            geometry_consistency=GeometryConsistencyCorrectionPolicy(
                long_axis=LongAxisGeometryCorrectionPolicy(
                    enabled=long_correction_family.mode != "off",
                    family=long_correction_family,
                    ratio_tolerance=float(long_axis.ratio_tolerance),
                    min_shrink_ratio=float(long_axis.min_shrink_ratio),
                    max_shrink_ratio=float(long_axis.max_shrink_ratio),
                    content_margin_ratio=float(long_axis.content_margin_ratio),
                    content_margin_min=int(long_axis.content_margin_min),
                    content_margin_max=int(long_axis.content_margin_max),
                ),
                short_axis=ShortAxisGeometryCorrectionPolicy(
                    enabled=short_correction_family.mode != "off",
                    family=short_correction_family,
                    min_error=float(short_axis.min_error),
                    target_aspect=short_target_aspect,
                    margin_ratio=float(short_axis.margin_ratio),
                    margin_min=int(short_axis.margin_min),
                    margin_max=int(short_axis.margin_max),
                ),
            ),
            content_containment=ContentContainmentCorrectionPolicy(
                family=content_correction_family,
                margin_x_ratio=float(content_containment.margin_x_ratio),
                margin_x_min=int(content_containment.margin_x_min),
                margin_x_max=int(content_containment.margin_x_max),
                margin_y_ratio=float(content_containment.margin_y_ratio),
                margin_y_min=int(content_containment.margin_y_min),
                margin_y_max=int(content_containment.margin_y_max),
                long_margin_ratio=float(content_containment.long_margin_ratio),
                long_margin_cap_ratio=float(content_containment.long_margin_cap_ratio),
                long_margin_cap_min=int(content_containment.long_margin_cap_min),
                long_margin_cap_max=int(content_containment.long_margin_cap_max),
                short_margin_ratio=float(content_containment.short_margin_ratio),
                short_margin_cap_ratio=float(content_containment.short_margin_cap_ratio),
                short_margin_cap_min=int(content_containment.short_margin_cap_min),
                short_margin_cap_max=int(content_containment.short_margin_cap_max),
                min_corrected_size_ratio=float(content_containment.min_corrected_size_ratio),
                min_corrected_width_px=int(content_containment.min_corrected_width_px),
                min_corrected_height_px=int(content_containment.min_corrected_height_px),
            ),
        ),
        alignment_evidence=OuterAlignmentEvidencePolicy(
            content_bbox_thresholds=tuple(int(value) for value in outer_alignment.content_bbox_thresholds),
            content_bbox_min_row_fraction=float(outer_alignment.content_bbox_min_row_fraction),
            content_bbox_min_col_fraction=float(outer_alignment.content_bbox_min_col_fraction),
            border_dark_threshold=int(outer_alignment.border_dark_threshold),
            border_band_min_px=int(outer_alignment.border_band_min_px),
            border_band_max_px=int(outer_alignment.border_band_max_px),
            edge_short_min_px=int(outer_alignment.edge_short_min_px),
            white_edge_long_ratio=float(outer_alignment.white_edge_long_ratio),
            white_edge_long_min=int(outer_alignment.white_edge_long_min),
            white_edge_long_max=int(outer_alignment.white_edge_long_max),
            long_threshold_ratio=float(outer_alignment.long_threshold_ratio),
            long_threshold_min=int(outer_alignment.long_threshold_min),
            long_threshold_max=int(outer_alignment.long_threshold_max),
            short_threshold_ratio=float(outer_alignment.short_threshold_ratio),
            short_threshold_min=int(outer_alignment.short_threshold_min),
            short_threshold_max=int(outer_alignment.short_threshold_max),
            long_excess_ratio=float(outer_alignment.long_excess_ratio),
            long_excess_threshold_ratio=float(outer_alignment.long_excess_threshold_ratio),
            short_excess_ratio=float(outer_alignment.short_excess_ratio),
            short_requires_hard_anchors=bool(outer_alignment.short_requires_hard_anchors),
            short_content_height_max=float(outer_alignment.short_content_height_max),
            content_width_min=float(outer_alignment.content_width_min),
            edge_short_ratio=float(outer_alignment.edge_short_ratio),
            edge_dark_max=float(outer_alignment.edge_dark_max),
            border_band_ratio=float(outer_alignment.border_band_ratio),
        ),
    )

__all__ = [
    'outer_policy',
    'outer_correction_family_policies',
    'separator_outer_family_policies',
]
