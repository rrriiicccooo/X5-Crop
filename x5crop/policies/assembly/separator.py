from __future__ import annotations

from ...constants import GAP_CONTENT, GAP_DETECTED, GAP_EDGE_PAIR, GAP_EQUAL, GAP_GRID
from ...formats import FormatPhysicalSpec
from .profile_defaults import (
    leading_grid_failure_parameters,
    nearby_separator_refinement_parameters,
    separator_support_parameters,
    separator_geometry_support_parameters,
)
from .presets import FormatPolicyPreset, ModePolicyPreset
from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL
from ..runtime.separator import (
    LeadingGridFailurePolicy,
    SeparatorSupportPolicy,
    SeparatorGeometrySupportModePolicy,
    SeparatorGeometrySupportPolicy,
    SeparatorModelGapProposalPolicy,
    SeparatorPolicy,
    SeparatorRefinementFamilyPolicy,
    SeparatorRefinementPolicy,
    SeparatorWidthProfilePolicy,
)


def separator_support_policy(
    fmt: FormatPhysicalSpec,
    params: FormatParameters,
) -> SeparatorSupportPolicy:
    support = separator_support_parameters(fmt, params)
    leading_grid = leading_grid_failure_parameters(fmt, params)
    return SeparatorSupportPolicy(
        needed_hard_max=int(support.needed_hard_max),
        max_equal_gaps_floor=int(support.max_equal_gaps_floor),
        allow_geometry_support=bool(support.allow_geometry_support),
        hard_required_all_gaps=bool(support.hard_required_all_gaps),
        edge_pair_min_score_without_broad_width=float(support.edge_pair_min_score_without_broad_width),
        edge_pair_min_score_with_broad_width=float(support.edge_pair_min_score_with_broad_width),
        reliable_gap_min_score=float(support.reliable_gap_min_score),
        min_broad_separator_width_gaps_for_auto=int(support.min_broad_separator_width_gaps_for_auto),
        score_min_hard_gaps=int(support.score_min_hard_gaps),
        score_max_equal_gaps_floor=int(support.score_max_equal_gaps_floor),
        low_hard_confidence_cap=float(support.low_hard_confidence_cap),
        mostly_equal_confidence_cap=float(support.mostly_equal_confidence_cap),
        allow_full_detected_geometry=bool(support.allow_full_detected_geometry),
        leading_grid_failure=LeadingGridFailurePolicy(
            enabled=bool(leading_grid.enabled),
            min_expected_gaps=int(leading_grid.min_expected_gaps),
            leading_count=int(leading_grid.leading_count),
            low_score=float(leading_grid.low_score),
            very_low_score=float(leading_grid.very_low_score),
            very_low_count=int(leading_grid.very_low_count),
            max_hard_gaps=int(leading_grid.max_hard_gaps),
        ),
    )


def separator_geometry_support_policy(
    fmt: FormatPhysicalSpec,
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> SeparatorGeometrySupportPolicy:
    if not mode_preset.separator_geometry_support_modes:
        return SeparatorGeometrySupportPolicy()
    support = separator_geometry_support_parameters(fmt, params)
    mode_policy = SeparatorGeometrySupportModePolicy(
        enabled=True,
        min_hard_ratio=float(support.detected_geometry_min_hard_ratio),
        min_joint_score=float(support.detected_geometry_min_joint_score),
        allow_grid=True,
        max_equal_gaps=0,
        max_photo_width_cv=float(support.max_photo_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    stable_grid_policy = SeparatorGeometrySupportModePolicy(
        enabled=True,
        min_hard_ratio=float(support.stable_grid_min_hard_ratio),
        min_joint_score=float(support.stable_grid_min_joint_score),
        allow_grid=True,
        max_equal_gaps=0,
        max_photo_width_cv=float(support.max_photo_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    return SeparatorGeometrySupportPolicy(
        detected_geometry=mode_policy if "detected_geometry" in mode_preset.separator_geometry_support_modes else SeparatorGeometrySupportModePolicy(),
        stable_grid=stable_grid_policy if "stable_grid" in mode_preset.separator_geometry_support_modes else SeparatorGeometrySupportModePolicy(),
    )


def separator_model_gap_proposal_policy(
    mode_preset: ModePolicyPreset,
) -> SeparatorModelGapProposalPolicy:
    return SeparatorModelGapProposalPolicy(
        geometry_equal_model_enabled=bool(mode_preset.detector_kind == "standard_strip"),
        geometry_equal_model_strip_modes=("full",),
        requires_default_count=True,
        requires_standard_width_search=True,
        requires_incomplete_hard_gaps=True,
    )


def separator_width_profile_policy(
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
    *,
    enabled: bool,
) -> SeparatorWidthProfilePolicy:
    preset = mode_preset.separator_width_profile
    family_mode = (
        "conditional"
        if enabled and mode_preset.detector_kind == "standard_strip"
        else "off"
    )
    mode = preset.mode if preset.mode != "off" else family_mode
    if not enabled:
        mode = "off"
    width_profile = params.separator.separator_width_profile
    return SeparatorWidthProfilePolicy(
        mode=mode,
        max_width_ratio=float(width_profile.max_width_ratio),
        required_count=0,
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
            requires_explicit_count_for_partial=True,
            target_gap_methods=(GAP_DETECTED, GAP_EDGE_PAIR),
            model_promotion_gap_methods=(GAP_GRID, GAP_EQUAL, GAP_CONTENT),
        ),
        nearby=SeparatorRefinementFamilyPolicy(
            mode="conditional",
            phase="extension",
            strip_modes=standard_strip_modes,
            requires_explicit_count_for_partial=True,
            target_gap_methods=(GAP_DETECTED, GAP_EDGE_PAIR),
        ),
    )


def separator_policy(
    fmt: FormatPhysicalSpec,
    preset: FormatPolicyPreset,
    mode_preset: ModePolicyPreset,
    strip_mode: str,
    params: FormatParameters,
) -> SeparatorPolicy:
    support = separator_support_policy(fmt, params)
    separator_width_profile = params.separator.separator_width_profile
    separator_width_profile_enabled = bool(
        (strip_mode == FULL and separator_width_profile.full_enabled)
        or (strip_mode == PARTIAL and separator_width_profile.partial_enabled)
    )
    hard_gap_trust = params.separator.hard_gap_trust
    nearby_refinement = nearby_separator_refinement_parameters(fmt, params)
    gap_search = params.separator.gap_search
    profile = params.separator.separator_profile
    edge_refine = params.separator.edge_refine_profile
    return SeparatorPolicy(
        support=support,
        hard_required_all_gaps=bool(support.hard_required_all_gaps),
        model_gap_proposal=separator_model_gap_proposal_policy(mode_preset),
        width_profile=separator_width_profile_policy(
            mode_preset,
            params,
            enabled=separator_width_profile_enabled,
        ),
        width_profile_search=params.separator.separator_width_profile_search,
        refinement=separator_refinement_policy(mode_preset),
        geometry_support_modes=mode_preset.separator_geometry_support_modes,
        geometry_support=separator_geometry_support_policy(fmt, mode_preset, params),
        edge_pair=preset.separator_edge_pair,
        hard_gap_trust=hard_gap_trust,
        nearby_refinement=nearby_refinement,
        gap_search=gap_search,
        profile=profile,
        edge_refine_profile=edge_refine,
    )

__all__ = [
    'separator_support_policy',
    'separator_geometry_support_policy',
    'separator_model_gap_proposal_policy',
    'separator_refinement_policy',
    'separator_width_profile_policy',
    'separator_policy',
]
