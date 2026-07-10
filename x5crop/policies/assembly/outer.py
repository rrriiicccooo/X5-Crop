from __future__ import annotations

from .presets import ModePolicyPreset
from ..parameters.aggregate import FormatParameters
from ..parameters.outer import (
    LongAxisGeometryCorrectionParameters,
    ShortAxisGeometryCorrectionParameters,
)
from ..runtime.base import PARTIAL
from ..runtime.outer import (
    BaseOuterProposalPolicy,
    ContentContainmentCorrectionPolicy,
    GeometryConsistencyCorrectionPolicy,
    GeometryOuterProposalPolicy,
    LongAxisGeometryCorrectionPolicy,
    OuterCorrectionFamilyPolicy,
    OuterCorrectionPolicy,
    OuterPolicy,
    OuterProposalPolicy,
    PartialPlacementGeometryPolicy,
    SeparatorOuterFamilyPolicy,
    SeparatorGeometryProposalPolicy,
    ShortAxisGeometryCorrectionPolicy,
)


def separator_outer_family_policies(
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> tuple[SeparatorOuterFamilyPolicy, SeparatorOuterFamilyPolicy, SeparatorOuterFamilyPolicy]:
    is_standard_strip = mode_preset.detector_kind == "standard_strip"
    full_width_outer = params.outer.separator_full_width_outer
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
            mode="conditional" if is_standard_strip else "off",
            phase="supplemental",
            requires_explicit_count_for_partial=True,
            max_candidates=0,
        ),
    )


def outer_correction_family_policies(
    mode_preset: ModePolicyPreset,
    long_axis: LongAxisGeometryCorrectionParameters,
    short_axis: ShortAxisGeometryCorrectionParameters,
) -> tuple[OuterCorrectionFamilyPolicy, OuterCorrectionFamilyPolicy, OuterCorrectionFamilyPolicy]:
    is_standard_strip = mode_preset.detector_kind == "standard_strip"
    long_mode = "conditional" if is_standard_strip else "off"
    short_mode = "conditional" if is_standard_strip else "off"
    content_mode = "conditional" if is_standard_strip else "off"
    return (
        OuterCorrectionFamilyPolicy(
            mode=long_mode,
            phase="geometry_consistency",
            requires_complete_hard_gaps=True,
            allowed_axes=("long",),
            max_shrink_ratio=float(long_axis.max_shrink_ratio),
            max_expand_ratio=0.0,
        ),
        OuterCorrectionFamilyPolicy(
            mode=short_mode,
            phase="geometry_consistency",
            requires_complete_hard_gaps=False,
            allowed_axes=("short",),
            max_shrink_ratio=0.0,
            max_expand_ratio=float(short_axis.max_expand_ratio),
        ),
        OuterCorrectionFamilyPolicy(
            mode=content_mode,
            phase="content_containment",
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
) -> OuterPolicy:
    outer = params.outer.outer_strategy
    long_axis = params.outer.long_axis_geometry_correction
    short_axis = params.outer.short_axis_geometry_correction
    content_containment = params.outer.content_containment_correction
    floating_position = params.outer.floating_content_position
    edge_position = params.outer.edge_anchored_content_position
    separator_outer = params.outer.separator_outer_band
    separator_full_width = params.outer.separator_full_width_outer
    partial_content_enabled = bool(strip_mode == PARTIAL and mode_preset.detector_kind != "review_only")
    local_family, full_width_family, width_profile_family = separator_outer_family_policies(mode_preset, params)
    long_correction_family, short_correction_family, content_correction_family = outer_correction_family_policies(
        mode_preset,
        long_axis,
        short_axis,
    )
    return OuterPolicy(
        proposal=OuterProposalPolicy(
            base=BaseOuterProposalPolicy(
                candidates=params.outer.base_outer_candidates,
            ),
            geometry=GeometryOuterProposalPolicy(
                partial_placement=PartialPlacementGeometryPolicy(
                    enabled=partial_content_enabled,
                    floating=floating_position,
                    edge_anchor=edge_position,
                ),
                separator=SeparatorGeometryProposalPolicy(
                    local=local_family,
                    full_width=full_width_family,
                    width_profile_family=width_profile_family,
                    separator_gap_search_max_width_ratio=float(outer.separator_gap_search_max_width_ratio),
                    band=separator_outer,
                    full_width_outer=separator_full_width,
                ),
                grid_refine=params.outer.grid_outer_refine,
            ),
        ),
        correction=OuterCorrectionPolicy(
            geometry_consistency=GeometryConsistencyCorrectionPolicy(
                long_axis=LongAxisGeometryCorrectionPolicy(
                    family=long_correction_family,
                    parameters=long_axis,
                ),
                short_axis=ShortAxisGeometryCorrectionPolicy(
                    family=short_correction_family,
                    parameters=short_axis,
                ),
            ),
            content_containment=ContentContainmentCorrectionPolicy(
                family=content_correction_family,
                parameters=content_containment,
            ),
        ),
        alignment_evidence=params.outer.outer_alignment_evidence,
    )
