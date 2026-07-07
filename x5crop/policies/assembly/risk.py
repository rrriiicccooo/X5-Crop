from __future__ import annotations

from ...formats import FormatSpec
from .presets import ModePolicyPreset
from .profile_defaults import lucky_pass_risk_parameters
from ..parameters.aggregate import FormatParameters
from ..runtime.risk import (
    LuckyPassRiskPolicy,
    OverlapBleedRiskPolicy,
    RuntimeRiskPolicy,
)


def runtime_risk_policy(
    fmt: FormatSpec,
    mode_preset: ModePolicyPreset,
    params: FormatParameters,
) -> RuntimeRiskPolicy:
    overlap = params.overlap_bleed_risk
    lucky = lucky_pass_risk_parameters(fmt, params)
    return RuntimeRiskPolicy(
        overlap_bleed=OverlapBleedRiskPolicy(
            enabled=mode_preset.overlap_bleed_risk_enabled,
            mean_min=float(overlap.mean_min),
            weak_continuity=float(overlap.weak_continuity),
            weak_activity=float(overlap.weak_activity),
            medium_continuity=float(overlap.medium_continuity),
            medium_activity=float(overlap.medium_activity),
            strong_continuity=float(overlap.strong_continuity),
            strong_activity=float(overlap.strong_activity),
        ),
        lucky_pass=LuckyPassRiskPolicy(
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
            unstable_photo_width_cv=float(lucky.unstable_photo_width_cv),
            unstable_photo_width_weight=float(lucky.unstable_photo_width_weight),
            mild_photo_width_cv=float(lucky.mild_photo_width_cv),
            mild_photo_width_weight=float(lucky.mild_photo_width_weight),
            strong_hard_credit_min=int(lucky.strong_hard_credit_min),
            strong_hard_credit=float(lucky.strong_hard_credit),
            stable_photo_width_cv=float(lucky.stable_photo_width_cv),
            stable_model_gap_min=int(lucky.stable_model_gap_min),
            stable_photo_width_geometry_credit=float(lucky.stable_photo_width_geometry_credit),
            risk_threshold=float(lucky.risk_threshold),
        ),
    )


__all__ = [
    "runtime_risk_policy",
]
