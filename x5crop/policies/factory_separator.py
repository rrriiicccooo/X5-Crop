from __future__ import annotations

from ..formats import FORMATS
from .factory_presets import FormatPolicyPreset, ModePolicyPreset
from .parameters import FormatParameters
from .runtime_policy import (
    FULL,
    PARTIAL,
    GatePolicy,
    GapSearchPolicy,
    HardGapTrustPolicy,
    LeadingGridFailurePolicy,
    NearbySeparatorCorrectionPolicy,
    RobustGridPolicy,
    EnhancedSeparatorPolicy,
    SeparatorGatePolicy,
    SeparatorGeometrySupportModePolicy,
    SeparatorGeometrySupportPolicy,
    SeparatorProfilePolicy,
    SeparatorPolicy,
    EdgeRefineProfilePolicy,
)

def separator_gate_policy(
    preset: FormatPolicyPreset,
    params: FormatParameters,
) -> SeparatorGatePolicy:
    gate = params.separator_gate
    leading_grid = params.leading_grid_failure
    return SeparatorGatePolicy(
        profile=preset.separator_gate_profile,
        needed_hard_max=int(gate.needed_hard_max),
        max_equal_gaps_floor=int(gate.max_equal_gaps_floor),
        allow_geometry_support=bool(gate.allow_geometry_support),
        hard_required_all_gaps=bool(gate.hard_required_all_gaps),
        edge_pair_min_score_without_wide=float(gate.edge_pair_min_score_without_wide),
        edge_pair_min_score_with_wide=float(gate.edge_pair_min_score_with_wide),
        min_wide_gaps_for_auto=int(gate.min_wide_gaps_for_auto),
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
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> SeparatorGeometrySupportPolicy:
    if not mode_preset.separator_geometry_support_modes:
        return SeparatorGeometrySupportPolicy()
    support = params.separator_geometry_support
    mode_policy = SeparatorGeometrySupportModePolicy(
        enabled=True,
        min_hard_ratio=float(support.wide_geometry_min_hard_ratio),
        min_joint_score=float(support.wide_geometry_min_joint_score),
        allow_grid=True,
        max_equal_gaps=0,
        max_width_cv=float(support.max_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    stable_grid_policy = SeparatorGeometrySupportModePolicy(
        enabled=True,
        min_hard_ratio=float(support.stable_grid_min_hard_ratio),
        min_joint_score=float(support.stable_grid_min_joint_score),
        allow_grid=True,
        max_equal_gaps=0,
        max_width_cv=float(support.max_width_cv),
        required_content_support="ok",
        max_outer_area_ratio=float(support.max_outer_area_ratio),
    )
    return SeparatorGeometrySupportPolicy(
        wide_geometry=mode_policy if "wide_geometry" in mode_preset.separator_geometry_support_modes else SeparatorGeometrySupportModePolicy(),
        stable_grid=stable_grid_policy if "stable_grid" in mode_preset.separator_geometry_support_modes else SeparatorGeometrySupportModePolicy(),
    )

def separator_policy(
    preset: FormatPolicyPreset,
    mode_preset: ModePolicyPreset,
    strip_mode: str,
    params: FormatParameters,
) -> SeparatorPolicy:
    gate = separator_gate_policy(preset, params)
    wide_retry = params.wide_retry
    hard_gap_trust = params.hard_gap_trust
    nearby_correction = params.nearby_separator_correction
    robust_grid = params.robust_grid
    gap_search = params.gap_search
    enhanced = params.enhanced_separator
    profile = params.separator_profile
    edge_refine = params.edge_refine_profile
    return SeparatorPolicy(
        gate=gate,
        hard_required_all_gaps=bool(gate.hard_required_all_gaps),
        wide_retry=bool(
            (strip_mode == FULL and wide_retry.full_enabled)
            or (strip_mode == PARTIAL and wide_retry.partial_enabled)
        ),
        wide_retry_max_width_ratio=float(wide_retry.max_width_ratio),
        wide_separator_confidence_cap=float(wide_retry.confidence_cap),
        geometry_support_modes=mode_preset.separator_geometry_support_modes,
        geometry_support=separator_geometry_support_policy(mode_preset, params),
        edge_pair=preset.separator_edge_pair,
        hard_gap_trust=HardGapTrustPolicy(
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
        nearby_correction=NearbySeparatorCorrectionPolicy(
            enabled=bool(nearby_correction.enabled),
            window_ratio=float(nearby_correction.window_ratio),
            window_min=int(nearby_correction.window_min),
            window_max=int(nearby_correction.window_max),
            exclude_ratio=float(nearby_correction.exclude_ratio),
            exclude_min=int(nearby_correction.exclude_min),
            exclude_max=int(nearby_correction.exclude_max),
            max_width_ratio=float(nearby_correction.max_width_ratio),
            max_width_min=int(nearby_correction.max_width_min),
            max_width_max=int(nearby_correction.max_width_max),
            distance_ratio=float(nearby_correction.distance_ratio),
            score_add=float(nearby_correction.score_add),
            score_multiplier=float(nearby_correction.score_multiplier),
            local_gain_ratio=float(nearby_correction.local_gain_ratio),
            local_gain_min=float(nearby_correction.local_gain_min),
            local_gain_max=float(nearby_correction.local_gain_max),
        ),
        robust_grid=RobustGridPolicy(
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
        gap_search=GapSearchPolicy(
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
            wide_min_mean=float(gap_search.wide_min_mean),
            wide_min_prominence=float(gap_search.wide_min_prominence),
        ),
        enhanced=EnhancedSeparatorPolicy(
            max_width_ratio=float(enhanced.max_width_ratio),
            max_width_min=float(enhanced.max_width_min),
            max_width_max=float(enhanced.max_width_max),
            max_shift_ratio=float(enhanced.max_shift_ratio),
            max_shift_min=float(enhanced.max_shift_min),
            max_shift_max=float(enhanced.max_shift_max),
            auto_low_score=float(enhanced.auto_low_score),
        ),
        profile=SeparatorProfilePolicy(
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
        edge_refine_profile=EdgeRefineProfilePolicy(
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
    'separator_gate_policy',
    'separator_geometry_support_policy',
    'separator_policy',
]
