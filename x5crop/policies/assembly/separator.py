from __future__ import annotations

from ...constants import GAP_CONTENT, GAP_DETECTED, GAP_EDGE_PAIR, GAP_EQUAL, GAP_GRID
from ...geometry.detection_parameters import (
    EdgePairParameters,
    EdgeRefineProfileParameters,
    GapSearchParameters,
    HardGapTrustParameters,
    NearbySeparatorRefinementParameters,
    RobustGridParameters,
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
)
from ...formats import FORMATS
from .profile_defaults import (
    leading_grid_failure_parameters,
    nearby_separator_refinement_parameters,
    separator_gate_parameters,
    separator_geometry_support_parameters,
)
from .presets import FormatPolicyPreset, ModePolicyPreset
from ..parameters.aggregate import FormatParameters
from ..runtime.base import FULL, PARTIAL
from ..separator_gate_profiles import SEPARATOR_GATE_PROFILES
from ..runtime.separator import (
    LeadingGridFailurePolicy,
    SeparatorGatePolicy,
    SeparatorGeometrySupportModePolicy,
    SeparatorGeometrySupportPolicy,
    SeparatorModelGapProposalPolicy,
    SeparatorPolicy,
    SeparatorRefinementFamilyPolicy,
    SeparatorRefinementPolicy,
    SeparatorWidthProfilePolicy,
)


def separator_gate_policy(
    preset: FormatPolicyPreset,
    params: FormatParameters,
) -> SeparatorGatePolicy:
    if preset.separator_gate_profile not in SEPARATOR_GATE_PROFILES:
        supported = ", ".join(SEPARATOR_GATE_PROFILES)
        raise ValueError(
            f"Unsupported separator gate profile: {preset.separator_gate_profile!r}; "
            f"expected one of {supported}"
        )
    fmt = FORMATS[preset.format_id]
    gate = separator_gate_parameters(fmt, params)
    leading_grid = leading_grid_failure_parameters(fmt, params)
    return SeparatorGatePolicy(
        profile=preset.separator_gate_profile,
        needed_hard_max=int(gate.needed_hard_max),
        max_equal_gaps_floor=int(gate.max_equal_gaps_floor),
        allow_geometry_support=bool(gate.allow_geometry_support),
        hard_required_all_gaps=bool(gate.hard_required_all_gaps),
        edge_pair_min_score_without_broad_width=float(gate.edge_pair_min_score_without_broad_width),
        edge_pair_min_score_with_broad_width=float(gate.edge_pair_min_score_with_broad_width),
        min_broad_separator_width_gaps_for_auto=int(gate.min_broad_separator_width_gaps_for_auto),
        score_min_hard_gaps=int(gate.score_min_hard_gaps),
        score_max_equal_gaps_floor=int(gate.score_max_equal_gaps_floor),
        low_hard_confidence_cap=float(gate.low_hard_confidence_cap),
        mostly_equal_confidence_cap=float(gate.mostly_equal_confidence_cap),
        allow_full_detected_geometry=bool(gate.allow_full_detected_geometry),
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
    preset: FormatPolicyPreset,
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> SeparatorGeometrySupportPolicy:
    if not mode_preset.separator_geometry_support_modes:
        return SeparatorGeometrySupportPolicy()
    support = separator_geometry_support_parameters(FORMATS[preset.format_id], params)
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
    width_profile = params.separator_width_profile
    return SeparatorWidthProfilePolicy(
        mode=mode,
        max_width_ratio=float(width_profile.max_width_ratio),
        required_count=0,
    )


def separator_width_profile_search_parameters() -> SeparatorWidthProfileSearchParameters:
    return SeparatorWidthProfileSearchParameters()


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


def edge_pair_parameters_from_preset(
    preset: FormatPolicyPreset,
) -> EdgePairParameters:
    edge_pair = preset.separator_edge_pair
    return EdgePairParameters(
        window_ratio=float(edge_pair.window_ratio),
        min_gutter_ratio=float(edge_pair.min_gutter_ratio),
        max_gutter_ratio=float(edge_pair.max_gutter_ratio),
        min_strength=float(edge_pair.min_strength),
        min_background=float(edge_pair.min_background),
        min_quality_for_model_gap=float(edge_pair.min_quality_for_model_gap),
        min_quality_for_hard_gap=float(edge_pair.min_quality_for_hard_gap),
        hard_gap_quality_ratio=float(edge_pair.hard_gap_quality_ratio),
        max_hard_shift_ratio=float(edge_pair.max_hard_shift_ratio),
    )


def separator_policy(
    preset: FormatPolicyPreset,
    mode_preset: ModePolicyPreset,
    strip_mode: str,
    params: FormatParameters,
) -> SeparatorPolicy:
    gate = separator_gate_policy(preset, params)
    separator_width_profile = params.separator_width_profile
    separator_width_profile_enabled = bool(
        (strip_mode == FULL and separator_width_profile.full_enabled)
        or (strip_mode == PARTIAL and separator_width_profile.partial_enabled)
    )
    hard_gap_trust = params.hard_gap_trust
    nearby_refinement = nearby_separator_refinement_parameters(FORMATS[preset.format_id], params)
    robust_grid = params.robust_grid
    gap_search = params.gap_search
    profile = params.separator_profile
    edge_refine = params.edge_refine_profile
    return SeparatorPolicy(
        gate=gate,
        hard_required_all_gaps=bool(gate.hard_required_all_gaps),
        model_gap_proposal=separator_model_gap_proposal_policy(mode_preset),
        width_profile=separator_width_profile_policy(
            mode_preset,
            params,
            enabled=separator_width_profile_enabled,
        ),
        width_profile_search=separator_width_profile_search_parameters(),
        refinement=separator_refinement_policy(mode_preset),
        geometry_support_modes=mode_preset.separator_geometry_support_modes,
        geometry_support=separator_geometry_support_policy(preset, mode_preset, params),
        edge_pair=edge_pair_parameters_from_preset(preset),
        hard_gap_trust=HardGapTrustParameters(
            guard_ratio=float(hard_gap_trust.guard_ratio),
            guard_min=int(hard_gap_trust.guard_min),
            guard_max=int(hard_gap_trust.guard_max),
            narrow_ratio=float(hard_gap_trust.narrow_ratio),
            narrow_min=float(hard_gap_trust.narrow_min),
            narrow_max=float(hard_gap_trust.narrow_max),
            model_delta_ratio=float(hard_gap_trust.model_delta_ratio),
            geometry_width_ratio=float(hard_gap_trust.geometry_width_ratio),
            strong_min_score=float(hard_gap_trust.strong_min_score),
            strong_width_min=float(hard_gap_trust.strong_width_min),
            strong_width_max=float(hard_gap_trust.strong_width_max),
            narrow_ok_score=float(hard_gap_trust.narrow_ok_score),
            narrow_ok_width_min=float(hard_gap_trust.narrow_ok_width_min),
            narrow_ok_width_max=float(hard_gap_trust.narrow_ok_width_max),
            model_conflict_score=float(hard_gap_trust.model_conflict_score),
            core_content_threshold=int(hard_gap_trust.core_content_threshold),
            core_dark_threshold=int(hard_gap_trust.core_dark_threshold),
            dark_mean_max=float(hard_gap_trust.dark_mean_max),
            dark_fraction_min=float(hard_gap_trust.dark_fraction_min),
            dark_activity_max=float(hard_gap_trust.dark_activity_max),
            strong_core_content_max=float(hard_gap_trust.strong_core_content_max),
            weak_mean_min=float(hard_gap_trust.weak_mean_min),
            weak_content_min=float(hard_gap_trust.weak_content_min),
            frame_border_width_ratio=float(hard_gap_trust.frame_border_width_ratio),
            continuity_min=float(hard_gap_trust.continuity_min),
            activity_min=float(hard_gap_trust.activity_min),
        ),
        nearby_refinement=NearbySeparatorRefinementParameters(
            enabled=bool(nearby_refinement.enabled),
            window_ratio=float(nearby_refinement.window_ratio),
            window_min=int(nearby_refinement.window_min),
            window_max=int(nearby_refinement.window_max),
            exclude_ratio=float(nearby_refinement.exclude_ratio),
            exclude_min=int(nearby_refinement.exclude_min),
            exclude_max=int(nearby_refinement.exclude_max),
            max_width_ratio=float(nearby_refinement.max_width_ratio),
            max_width_min=int(nearby_refinement.max_width_min),
            max_width_max=int(nearby_refinement.max_width_max),
            distance_ratio=float(nearby_refinement.distance_ratio),
            score_add=float(nearby_refinement.score_add),
            score_multiplier=float(nearby_refinement.score_multiplier),
            local_gain_ratio=float(nearby_refinement.local_gain_ratio),
            local_gain_min=float(nearby_refinement.local_gain_min),
            local_gain_max=float(nearby_refinement.local_gain_max),
            width_cv_slack=float(nearby_refinement.width_cv_slack),
        ),
        robust_grid=RobustGridParameters(
            constrain_full_shift_ratio=float(robust_grid.constrain_full_shift_ratio),
            constrain_partial_shift_ratio=float(robust_grid.constrain_partial_shift_ratio),
            constrain_shift_min=float(robust_grid.constrain_shift_min),
            constrain_shift_max=float(robust_grid.constrain_shift_max),
            reliable_min_score=float(robust_grid.reliable_min_score),
            min_reliable=int(robust_grid.min_reliable),
            pitch_min_ratio=float(robust_grid.pitch_min_ratio),
            pitch_max_ratio=float(robust_grid.pitch_max_ratio),
            full_tolerance_ratio=float(robust_grid.full_tolerance_ratio),
            partial_tolerance_ratio=float(robust_grid.partial_tolerance_ratio),
            tolerance_min=float(robust_grid.tolerance_min),
            tolerance_max=float(robust_grid.tolerance_max),
            reject_residual_ratio=float(robust_grid.reject_residual_ratio),
            full_shift_ratio=float(robust_grid.full_shift_ratio),
            partial_shift_ratio=float(robust_grid.partial_shift_ratio),
            shift_min=float(robust_grid.shift_min),
            shift_max=float(robust_grid.shift_max),
            hard_keep_ratio=float(robust_grid.hard_keep_ratio),
            hard_keep_min=float(robust_grid.hard_keep_min),
            hard_keep_max=float(robust_grid.hard_keep_max),
            hard_protect_ratio=float(robust_grid.hard_protect_ratio),
            hard_protect_min=float(robust_grid.hard_protect_min),
            hard_protect_max=float(robust_grid.hard_protect_max),
        ),
        gap_search=GapSearchParameters(
            radius_ratio=float(gap_search.radius_ratio),
            radius_min=int(gap_search.radius_min),
            radius_max=int(gap_search.radius_max),
            max_width_ratio=float(gap_search.max_width_ratio),
            max_width_min=int(gap_search.max_width_min),
            max_width_max=int(gap_search.max_width_max),
            min_width_ratio=float(gap_search.min_width_ratio),
            min_width_min=int(gap_search.min_width_min),
            min_width_max=int(gap_search.min_width_max),
            guard_ratio=float(gap_search.guard_ratio),
            guard_min=int(gap_search.guard_min),
            guard_max=int(gap_search.guard_max),
            min_score=float(gap_search.min_score),
            peak_multiplier=float(gap_search.peak_multiplier),
            band_multiplier=float(gap_search.band_multiplier),
            band_min_score_multiplier=float(gap_search.band_min_score_multiplier),
            weak_prominence_min=float(gap_search.weak_prominence_min),
            weak_prominence_mean_override=float(gap_search.weak_prominence_mean_override),
            quality_prominence_weight=float(gap_search.quality_prominence_weight),
            separator_width_min_mean=float(gap_search.separator_width_min_mean),
            separator_width_min_prominence=float(gap_search.separator_width_min_prominence),
        ),
        profile=SeparatorProfileParameters(
            top_ratio=float(profile.top_ratio),
            bottom_ratio=float(profile.bottom_ratio),
            segments=int(profile.segments),
            dark_threshold=int(profile.dark_threshold),
            light_threshold=int(profile.light_threshold),
            consistency_percentile=float(profile.consistency_percentile),
            average_weight=float(profile.average_weight),
            consistency_weight=float(profile.consistency_weight),
            std_norm=float(profile.std_norm),
            dark_soft_mean=float(profile.dark_soft_mean),
            light_soft_mean=float(profile.light_soft_mean),
            light_soft_span=float(profile.light_soft_span),
            soft_weight=float(profile.soft_weight),
            uniform_base=float(profile.uniform_base),
            uniform_weight=float(profile.uniform_weight),
            gradient_weight=float(profile.gradient_weight),
            smooth_ratio=float(profile.smooth_ratio),
            smooth_min=int(profile.smooth_min),
        ),
        edge_refine_profile=EdgeRefineProfileParameters(
            top_ratio=float(edge_refine.top_ratio),
            bottom_ratio=float(edge_refine.bottom_ratio),
            mean_weight=float(edge_refine.mean_weight),
            p75_weight=float(edge_refine.p75_weight),
            smooth_ratio=float(edge_refine.smooth_ratio),
            smooth_min=int(edge_refine.smooth_min),
            high_percentile=float(edge_refine.high_percentile),
            background_dark_threshold=int(edge_refine.background_dark_threshold),
            background_light_threshold=int(edge_refine.background_light_threshold),
            y_edge_weight=float(edge_refine.y_edge_weight),
            activity_percentile=float(edge_refine.activity_percentile),
        ),
    )

__all__ = [
    'edge_pair_parameters_from_preset',
    'separator_gate_policy',
    'separator_geometry_support_policy',
    'separator_model_gap_proposal_policy',
    'separator_refinement_policy',
    'separator_width_profile_policy',
    'separator_width_profile_search_parameters',
    'separator_policy',
]
