from __future__ import annotations

from dataclasses import replace

from ...formats import FormatSpec, format_spec
from ...formats.traits import runtime_traits_for_spec
from .contract import EvidencePolicy


def _content_aspect(spec: FormatSpec) -> float:
    return float(spec.horizontal_content_aspect or 1.0)


def _is_standard_35mm_strip(spec: FormatSpec) -> bool:
    return (
        spec.family == "35mm"
        and spec.physical_layout == "single_strip"
        and spec.default_count == 6
        and runtime_traits_for_spec(spec).frame_fit_profile == "standard_strip"
    )


def _is_dense_geometry_supported_strip(spec: FormatSpec) -> bool:
    return runtime_traits_for_spec(spec).geometry_support_profile == "stable_dense_grid"


def _is_panorama_strip(spec: FormatSpec) -> bool:
    return spec.family == "35mm" and _content_aspect(spec) > 2.0


def _is_medium_square_strip(spec: FormatSpec) -> bool:
    return spec.family == "120" and abs(_content_aspect(spec) - 1.0) <= 0.05


def _is_medium_wide_strip(spec: FormatSpec) -> bool:
    return spec.family == "120" and _content_aspect(spec) > 1.1


def _physical_evidence_policy(spec: FormatSpec, defaults: EvidencePolicy) -> EvidencePolicy:
    if spec.physical_layout == "dual_lane":
        return replace(
            defaults,
            min_hard_separator_ratio=0.50,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.035,
        )
    if _is_dense_geometry_supported_strip(spec):
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
    if _is_standard_35mm_strip(spec):
        return replace(
            defaults,
            min_hard_separator_ratio=0.35,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.030,
            max_model_gap_share=0.70,
        )
    if _is_panorama_strip(spec):
        return replace(
            defaults,
            min_hard_separator_ratio=0.67,
            min_hard_separator_count=1,
            max_photo_width_cv_ratio=0.035,
        )
    if _is_medium_square_strip(spec):
        return replace(
            defaults,
            min_hard_separator_ratio=0.90,
            min_hard_separator_count=2,
            max_photo_width_cv_ratio=0.040,
            max_outer_area_ratio=0.990,
        )
    if _is_medium_wide_strip(spec):
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
    format_id: str,
    strip_mode: str,
    defaults: EvidencePolicy,
    geometry_support_modes: tuple[str, ...] = (),
) -> EvidencePolicy:
    spec = format_spec(format_id)
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


__all__ = ["evidence_policy_for_physical_spec"]
