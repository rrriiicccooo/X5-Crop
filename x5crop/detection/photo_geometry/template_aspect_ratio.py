"""Derive and reconcile bounded format-calibrated aperture aspect ratio."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState, FiniteInterval, PositiveInterval
from ...formats import APERTURE_COMPATIBILITY_SPEC, OUTPUT_PROTECTION_SPEC
from .interval_math import intersect
from .physical_identity import physical_fact_id
from .source_geometry import SourceScanGeometry
from .template_aspect_ratio_model import (
    ApertureAspectRatioAuthority,
    ApertureAspectRatioFailureKind,
    unavailable_aperture_aspect_ratio_authority,
)
from .template_frame_width import SourceFrameWidthAuthority


def derive_aperture_aspect_ratio_authority(
    source_geometry: SourceScanGeometry,
    source_frame_width_authority: SourceFrameWidthAuthority,
) -> ApertureAspectRatioAuthority:
    """Map one canonical source W through calibrated R at rank zero."""

    if not isinstance(
        source_frame_width_authority,
        SourceFrameWidthAuthority,
    ):
        raise TypeError("aspect ratio requires typed source W authority")

    spec = source_geometry.frame_spec.aperture_aspect_ratio
    if spec is None:
        return unavailable_aperture_aspect_ratio_authority()
    if source_frame_width_authority.state != EvidenceState.SUPPORTED:
        return unavailable_aperture_aspect_ratio_authority(
            "canonical source W authority is unavailable"
        )
    width_ids = source_geometry.width_state.observation_ids
    if width_ids != source_frame_width_authority.observation_ids:
        raise ValueError("source geometry and canonical W authority disagree")
    if (
        source_geometry.width_state.scale_authority
        != source_geometry.height_state.scale_authority
    ):
        return unavailable_aperture_aspect_ratio_authority(
            "source axes do not share one scan-scale identity"
        )
    raw_ratio = PositiveInterval(
        spec.raw_width_over_height_minimum,
        spec.raw_width_over_height_maximum,
    )
    guarded_bounds = spec.guarded_bounds(
        nominal_width_mm=source_geometry.frame_spec.frame_width_mm,
        nominal_height_mm=source_geometry.frame_spec.frame_height_mm,
    )
    ratio = PositiveInterval(
        guarded_bounds[0],
        guarded_bounds[1],
    )
    width_guard_mm = APERTURE_COMPATIBILITY_SPEC.width.guard_mm(
        source_geometry.frame_spec.frame_width_mm
    )
    height_guard_mm = APERTURE_COMPATIBILITY_SPEC.height.guard_mm(
        source_geometry.frame_spec.frame_height_mm
    )
    width_guard_ratio = (
        width_guard_mm / source_geometry.frame_spec.frame_width_mm
    )
    height_guard_ratio = (
        height_guard_mm / source_geometry.frame_spec.frame_height_mm
    )
    # SourceScanGeometry proves one shared scale identity.  This exact 1 is a
    # correlation fact, not the forbidden recombination of two scale ranges.
    scale_ratio = PositiveInterval.exact(1.0)
    width = source_geometry.width_state.extent_projection_px()
    inferred = FiniteInterval(
        width.minimum * scale_ratio.minimum / ratio.maximum,
        width.maximum * scale_ratio.maximum / ratio.minimum,
    )
    physical_height = source_geometry.height_state.extent_projection_px()
    effective = intersect(inferred, physical_height)
    authority_id = physical_fact_id(
        "aperture-aspect-ratio",
        (
            spec.calibration_id,
            APERTURE_COMPATIBILITY_SPEC.calibration_id,
        ),
        raw_ratio,
        ratio,
        scale_ratio,
        width,
        source_frame_width_authority.authority_id,
        width_ids,
    )
    if effective is None:
        return ApertureAspectRatioAuthority(
            authority_id=authority_id,
            state=EvidenceState.CONTRADICTED,
            calibration_id=spec.calibration_id,
            axis_guard_calibration_id=(
                APERTURE_COMPATIBILITY_SPEC.calibration_id
            ),
            raw_width_over_height=raw_ratio,
            guarded_width_over_height=ratio,
            width_guard_mm=width_guard_mm,
            height_guard_mm=height_guard_mm,
            width_guard_ratio=width_guard_ratio,
            height_guard_ratio=height_guard_ratio,
            scale_height_over_width=scale_ratio,
            source_width_px=width,
            inferred_height_px=inferred,
            effective_height_px=None,
            canonical_height_px=None,
            width_observation_ids=width_ids,
            minimum_output_expansion_mm=None,
            output_expansion_limit_mm=(
                source_geometry.frame_spec.frame_height_mm
                * OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side
            ),
            failure_kind=(
                ApertureAspectRatioFailureKind.PHYSICAL_PRIOR_CONFLICT
            ),
            failure_detail=(
                "calibrated W/H inference does not intersect format H prior"
            ),
        )
    canonical = effective.center
    uncertainty_px = max(
        canonical - effective.minimum,
        effective.maximum - canonical,
    )
    minimum_expansion_mm = (
        source_geometry.height_state.worst_case_mm(uncertainty_px)
        + OUTPUT_PROTECTION_SPEC.cross_bleed_mm
    )
    limit_mm = (
        source_geometry.frame_spec.frame_height_mm
        * OUTPUT_PROTECTION_SPEC.maximum_expansion_ratio_per_side
    )
    if minimum_expansion_mm > limit_mm:
        return ApertureAspectRatioAuthority(
            authority_id=authority_id,
            state=EvidenceState.CONTRADICTED,
            calibration_id=spec.calibration_id,
            axis_guard_calibration_id=(
                APERTURE_COMPATIBILITY_SPEC.calibration_id
            ),
            raw_width_over_height=raw_ratio,
            guarded_width_over_height=ratio,
            width_guard_mm=width_guard_mm,
            height_guard_mm=height_guard_mm,
            width_guard_ratio=width_guard_ratio,
            height_guard_ratio=height_guard_ratio,
            scale_height_over_width=scale_ratio,
            source_width_px=width,
            inferred_height_px=inferred,
            effective_height_px=effective,
            canonical_height_px=canonical,
            width_observation_ids=width_ids,
            minimum_output_expansion_mm=minimum_expansion_mm,
            output_expansion_limit_mm=limit_mm,
            failure_kind=ApertureAspectRatioFailureKind.BUDGET_EXHAUSTED,
            failure_detail=(
                "ratio H uncertainty plus minimum cross bleed exceeds 5%"
            ),
        )
    return ApertureAspectRatioAuthority(
        authority_id=authority_id,
        state=EvidenceState.SUPPORTED,
        calibration_id=spec.calibration_id,
        axis_guard_calibration_id=APERTURE_COMPATIBILITY_SPEC.calibration_id,
        raw_width_over_height=raw_ratio,
        guarded_width_over_height=ratio,
        width_guard_mm=width_guard_mm,
        height_guard_mm=height_guard_mm,
        width_guard_ratio=width_guard_ratio,
        height_guard_ratio=height_guard_ratio,
        scale_height_over_width=scale_ratio,
        source_width_px=width,
        inferred_height_px=inferred,
        effective_height_px=effective,
        canonical_height_px=canonical,
        width_observation_ids=width_ids,
        minimum_output_expansion_mm=minimum_expansion_mm,
        output_expansion_limit_mm=limit_mm,
        failure_kind=None,
        failure_detail=None,
    )


def consume_aperture_aspect_ratio_for_cross(
    authority: ApertureAspectRatioAuthority,
) -> ApertureAspectRatioAuthority:
    if authority.state != EvidenceState.SUPPORTED:
        return authority
    return replace(
        authority,
        consumed_for_cross_inference=True,
        blocks_cross_resolution=False,
    )


def require_aperture_aspect_ratio_for_cross(
    authority: ApertureAspectRatioAuthority,
) -> ApertureAspectRatioAuthority:
    """Record that no direct-H closure survived without this authority."""

    if authority.state == EvidenceState.SUPPORTED:
        return authority
    return replace(authority, blocks_cross_resolution=True)


def reconcile_direct_aperture_height(
    authority: ApertureAspectRatioAuthority,
    direct_height_px: FiniteInterval,
) -> ApertureAspectRatioAuthority:
    """Keep native direct H when compatible; typed-review a true conflict."""

    if authority.state != EvidenceState.SUPPORTED:
        return replace(
            authority,
            blocks_cross_resolution=False,
            direct_height_px=direct_height_px,
        )
    if authority.effective_height_px is None:
        raise AssertionError("supported aspect-ratio authority lost effective H")
    if intersect(authority.effective_height_px, direct_height_px) is None:
        return replace(
            authority,
            state=EvidenceState.CONTRADICTED,
            canonical_height_px=None,
            failure_kind=ApertureAspectRatioFailureKind.DIRECT_CONFLICT,
            failure_detail=(
                "unique direct aperture H contradicts calibrated W/H interval"
            ),
            blocks_cross_resolution=True,
            direct_height_px=direct_height_px,
        )
    return replace(
        authority,
        direct_height_px=direct_height_px,
        consumed_for_cross_inference=False,
    )


def apply_inferred_aperture_height(
    source_geometry: SourceScanGeometry,
    authority: ApertureAspectRatioAuthority,
) -> SourceScanGeometry:
    """Narrow effective H without turning correlated inference into direct H."""

    if (
        authority.state != EvidenceState.SUPPORTED
        or not authority.consumed_for_cross_inference
        or authority.effective_height_px is None
    ):
        return source_geometry
    height_state = source_geometry.height_state.intersect_inferred_extent(
        authority.effective_height_px
    )
    return SourceScanGeometry.from_axis_states(
        source_geometry.frame_spec,
        source_geometry.width_state,
        height_state,
    )


__all__ = [
    "apply_inferred_aperture_height",
    "consume_aperture_aspect_ratio_for_cross",
    "derive_aperture_aspect_ratio_authority",
    "require_aperture_aspect_ratio_for_cross",
    "reconcile_direct_aperture_height",
]
