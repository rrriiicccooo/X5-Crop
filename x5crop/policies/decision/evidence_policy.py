from __future__ import annotations

from dataclasses import dataclass, replace

from ...formats import FormatPhysicalSpec


@dataclass(frozen=True)
class EvidencePolicy:
    min_outer_area_ratio: float = 0.30
    max_outer_area_ratio: float = 0.985
    max_photo_width_cv_ratio: float = 0.030
    min_geometry_score: float = 0.70
    min_content_score: float = 0.72
    min_hard_separator_ratio: float = 0.50
    min_hard_separator_count: int = 1
    max_equal_gap_count: int = 0
    max_content_gap_count: int = 0
    max_model_gap_share: float = 0.70
    allow_geometry_supported_separator: bool = False
    geometry_supported_min_hard_ratio: float = 0.35
    geometry_supported_max_photo_width_cv_ratio: float = 0.010
    partial_requires_safe_edge: bool = False


def _physical_evidence_policy(spec: FormatPhysicalSpec, defaults: EvidencePolicy) -> EvidencePolicy:
    profile = spec.frame_geometry_profile
    if spec.physical_layout == "dual_lane":
        return replace(
            defaults,
            min_hard_separator_ratio=0.50,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.035,
        )
    if profile == "dense_half":
        return replace(
            defaults,
            min_hard_separator_ratio=0.55,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.012,
            allow_geometry_supported_separator=True,
            geometry_supported_min_hard_ratio=0.20,
            geometry_supported_max_photo_width_cv_ratio=0.010,
            max_outer_area_ratio=0.990,
        )
    if profile == "standard_35mm":
        return replace(
            defaults,
            min_hard_separator_ratio=0.35,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.030,
            max_model_gap_share=0.70,
        )
    if profile == "panoramic_35mm":
        return replace(
            defaults,
            min_hard_separator_ratio=0.67,
            min_hard_separator_count=1,
            max_photo_width_cv_ratio=0.035,
        )
    if profile == "medium_square":
        return replace(
            defaults,
            min_hard_separator_ratio=0.90,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.040,
            max_outer_area_ratio=0.990,
        )
    if profile == "medium_wide":
        return replace(
            defaults,
            min_hard_separator_ratio=0.75,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.040,
        )
    if spec.family == "120":
        return replace(
            defaults,
            min_hard_separator_ratio=0.67,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.035,
        )
    return defaults


def _partial_evidence_policy(policy: EvidencePolicy) -> EvidencePolicy:
    return replace(
        policy,
        min_hard_separator_ratio=min(policy.min_hard_separator_ratio, 0.35),
        max_photo_width_cv_ratio=max(policy.max_photo_width_cv_ratio, 0.045),
        max_outer_area_ratio=max(policy.max_outer_area_ratio, 0.990),
        partial_requires_safe_edge=True,
    )


def evidence_policy_for_physical_spec(
    spec: FormatPhysicalSpec,
    strip_mode: str,
    defaults: EvidencePolicy,
    geometry_support_modes: tuple[str, ...] = (),
) -> EvidencePolicy:
    policy = _physical_evidence_policy(spec, defaults)
    if strip_mode == "partial":
        policy = _partial_evidence_policy(policy)
    else:
        policy = replace(policy, partial_requires_safe_edge=False)
    policy = replace(
        policy,
        allow_geometry_supported_separator=bool(geometry_support_modes),
    )
    return policy
