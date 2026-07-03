from __future__ import annotations

from .factory_presets import ModePolicyPreset
from .parameter_aggregate import FormatParameters
from .runtime_diagnostics import (
    DebugGapOverlayPolicy,
    LuckyPassRiskPolicy,
    NearbySeparatorDiagnosticsPolicy,
    OverlapBleedRiskPolicy,
    RuntimeDiagnosticsPolicy,
)
from .runtime_final import (
    ApprovedGeometryAdjustmentPolicy,
    FinalizationPolicy,
)


def finalization_policy(params: FormatParameters) -> FinalizationPolicy:
    finalization = params.finalization
    approved_adjustment = params.approved_geometry_adjustment
    return FinalizationPolicy(
        align_outer_to_content=True,
        outer_correction_candidates_enabled=bool(finalization.outer_correction_candidates_enabled),
        apply_output_bleed=True,
        apply_approved_geometry_adjustment=True,
        approved_geometry_adjustment=ApprovedGeometryAdjustmentPolicy(
            long_limit_ratio=float(approved_adjustment.long_limit_ratio),
            long_limit_min=int(approved_adjustment.long_limit_min),
            long_limit_max=int(approved_adjustment.long_limit_max),
            min_ext_ratio=float(approved_adjustment.min_ext_ratio),
            min_ext_min=int(approved_adjustment.min_ext_min),
            min_ext_max=int(approved_adjustment.min_ext_max),
        ),
        content_aspect_conflict_cap=float(finalization.content_aspect_conflict_cap),
        content_low_confidence_cap=float(finalization.content_low_confidence_cap),
        outer_mismatch_cap=float(finalization.outer_mismatch_cap),
        lucky_pass_risk_cap=float(finalization.lucky_pass_risk_cap),
    )


def diagnostics_policy(mode_preset: ModePolicyPreset, params: FormatParameters) -> RuntimeDiagnosticsPolicy:
    debug_gap = params.debug_gap_overlay
    nearby = params.nearby_separator_diagnostics
    overlap = params.diagnostic_overlap_risk
    lucky = params.lucky_pass_risk
    return RuntimeDiagnosticsPolicy(
        overlap_bleed_risk=OverlapBleedRiskPolicy(
            enabled=mode_preset.diagnostics_overlap_bleed,
            mean_min=float(overlap.mean_min),
            weak_continuity=float(overlap.weak_continuity),
            weak_activity=float(overlap.weak_activity),
            medium_continuity=float(overlap.medium_continuity),
            medium_activity=float(overlap.medium_activity),
            strong_continuity=float(overlap.strong_continuity),
            strong_activity=float(overlap.strong_activity),
        ),
        debug_gap_overlay=DebugGapOverlayPolicy(
            overlap_tolerance_ratio=float(debug_gap.overlap_tolerance_ratio),
            overlap_tolerance_min=float(debug_gap.overlap_tolerance_min),
            overlap_tolerance_max=float(debug_gap.overlap_tolerance_max),
            tick_length_ratio=float(debug_gap.tick_length_ratio),
            tick_length_min=int(debug_gap.tick_length_min),
            hard_line_width=int(debug_gap.hard_line_width),
            model_line_width=int(debug_gap.model_line_width),
            diagnostic_line_width=int(debug_gap.diagnostic_line_width),
        ),
        nearby_separator=NearbySeparatorDiagnosticsPolicy(
            window_ratio=float(nearby.window_ratio),
            window_min=int(nearby.window_min),
            window_max=int(nearby.window_max),
            exclude_ratio=float(nearby.exclude_ratio),
            exclude_min=int(nearby.exclude_min),
            exclude_max=int(nearby.exclude_max),
            max_width_ratio=float(nearby.max_width_ratio),
            max_width_min=int(nearby.max_width_min),
            max_width_max=int(nearby.max_width_max),
            detail_score_add=float(nearby.detail_score_add),
            detail_score_multiplier=float(nearby.detail_score_multiplier),
        ),
        lucky_pass_risk=LuckyPassRiskPolicy(
            enabled=bool(lucky.enabled),
            model_gap_support_min=int(lucky.model_gap_support_min),
            model_gap_support_weight=float(lucky.model_gap_support_weight),
            minor_model_gap_support_weight=float(lucky.minor_model_gap_support_weight),
            limited_strong_hard_max=int(lucky.limited_strong_hard_max),
            limited_strong_hard_weight=float(lucky.limited_strong_hard_weight),
            very_limited_strong_hard_max=int(lucky.very_limited_strong_hard_max),
            very_limited_strong_hard_weight=float(lucky.very_limited_strong_hard_weight),
            suspicious_hard_weight=float(lucky.suspicious_hard_weight),
            strong_overlap_weight=float(lucky.strong_overlap_weight),
            combo_weight=float(lucky.combo_weight),
            unstable_width_cv=float(lucky.unstable_width_cv),
            unstable_width_weight=float(lucky.unstable_width_weight),
            mild_width_cv=float(lucky.mild_width_cv),
            mild_width_weight=float(lucky.mild_width_weight),
            strong_hard_credit_min=int(lucky.strong_hard_credit_min),
            strong_hard_credit=float(lucky.strong_hard_credit),
            stable_width_cv=float(lucky.stable_width_cv),
            stable_model_gap_min=int(lucky.stable_model_gap_min),
            stable_geometry_credit=float(lucky.stable_geometry_credit),
            risk_threshold=float(lucky.risk_threshold),
        ),
    )

__all__ = [
    'finalization_policy',
    'diagnostics_policy',
]
