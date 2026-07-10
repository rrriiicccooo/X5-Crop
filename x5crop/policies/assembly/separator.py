from __future__ import annotations

from ...constants import GAP_CONTENT, GAP_DETECTED, GAP_EDGE_PAIR, GAP_EQUAL, GAP_GRID
from .presets import FormatPolicyPreset, ModePolicyPreset
from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL
from ..runtime.separator import (
    SeparatorGeometrySupportModePolicy,
    SeparatorGeometrySupportPolicy,
    SeparatorModelGapProposalPolicy,
    SeparatorPolicy,
    SeparatorRefinementFamilyPolicy,
    SeparatorRefinementPolicy,
    SeparatorWidthProfilePolicy,
)


def separator_geometry_support_policy(
    strip_mode: str,
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> SeparatorGeometrySupportPolicy:
    if mode_preset.detector_kind != "standard_strip" or strip_mode != FULL:
        return SeparatorGeometrySupportPolicy()
    support = params.separator.separator_geometry_support
    mode_policy = SeparatorGeometrySupportModePolicy(
        min_hard_ratio=float(support.detected_geometry_min_hard_ratio),
        min_joint_score=float(support.detected_geometry_min_joint_score),
        max_equal_gaps=0,
        max_photo_width_cv=float(support.max_photo_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    stable_grid_policy = SeparatorGeometrySupportModePolicy(
        min_hard_ratio=float(support.stable_grid_min_hard_ratio),
        min_joint_score=float(support.stable_grid_min_joint_score),
        max_equal_gaps=0,
        max_photo_width_cv=float(support.max_photo_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    return SeparatorGeometrySupportPolicy(
        detected_geometry=mode_policy,
        stable_grid=stable_grid_policy,
    )


def separator_model_gap_proposal_policy() -> SeparatorModelGapProposalPolicy:
    return SeparatorModelGapProposalPolicy(
        geometry_equal_model_strip_modes=("full",),
    )


def separator_width_profile_policy(
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> SeparatorWidthProfilePolicy:
    mode = (
        "conditional"
        if mode_preset.detector_kind == "standard_strip"
        else "off"
    )
    width_profile = params.separator.separator_width_profile
    return SeparatorWidthProfilePolicy(
        mode=mode,
        max_width_ratio=float(width_profile.max_width_ratio),
    )


def separator_refinement_policy(
    mode_preset: ModePolicyPreset,
) -> SeparatorRefinementPolicy:
    if mode_preset.detector_kind != "standard_strip":
        return SeparatorRefinementPolicy()
    standard_strip_modes = (FULL, PARTIAL)
    return SeparatorRefinementPolicy(
        edge_pair=SeparatorRefinementFamilyPolicy(
            mode="conditional",
            phase="primary",
            strip_modes=standard_strip_modes,
            target_gap_methods=(GAP_DETECTED, GAP_EDGE_PAIR),
            model_promotion_gap_methods=(GAP_GRID, GAP_EQUAL, GAP_CONTENT),
        ),
        nearby=SeparatorRefinementFamilyPolicy(
            mode="conditional",
            phase="extension",
            strip_modes=standard_strip_modes,
            target_gap_methods=(GAP_DETECTED, GAP_EDGE_PAIR),
        ),
    )


def separator_policy(
    strip_mode: str,
    preset: FormatPolicyPreset,
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> SeparatorPolicy:
    hard_gap_trust = params.separator.hard_gap_trust
    nearby_refinement = params.separator.nearby_separator_refinement
    gap_search = params.separator.gap_search
    profile = params.separator.separator_profile
    edge_refine = params.separator.edge_refine_profile
    return SeparatorPolicy(
        support=params.separator.separator_support,
        leading_grid_failure=params.separator.leading_grid_failure,
        model_gap_proposal=separator_model_gap_proposal_policy(),
        width_profile=separator_width_profile_policy(
            mode_preset,
            params,
        ),
        width_profile_search=params.separator.separator_width_profile_search,
        refinement=separator_refinement_policy(mode_preset),
        geometry_support=separator_geometry_support_policy(
            strip_mode,
            mode_preset,
            params,
        ),
        edge_pair=preset.separator_edge_pair,
        hard_gap_trust=hard_gap_trust,
        nearby_refinement=nearby_refinement,
        gap_search=gap_search,
        profile=profile,
        edge_refine_profile=edge_refine,
    )
