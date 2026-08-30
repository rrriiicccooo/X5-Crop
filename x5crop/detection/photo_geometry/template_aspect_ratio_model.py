"""Canonical typed authority for bounded source aperture W/H coupling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval


class ApertureAspectRatioFailureKind(str, Enum):
    AUTHORITY_UNAVAILABLE = "aperture_aspect_ratio_authority_unavailable"
    PHYSICAL_PRIOR_CONFLICT = "aperture_aspect_ratio_physical_prior_conflict"
    DIRECT_CONFLICT = "aperture_aspect_ratio_direct_conflict"
    BUDGET_EXHAUSTED = "aperture_aspect_ratio_budget_exhausted"


@dataclass(frozen=True)
class ApertureAspectRatioAuthority:
    """One correlated H inference from direct source W and calibrated R."""

    authority_id: str
    state: EvidenceState
    calibration_id: str | None
    axis_guard_calibration_id: str | None
    raw_width_over_height: PositiveInterval | None
    guarded_width_over_height: PositiveInterval | None
    width_guard_mm: float | None
    height_guard_mm: float | None
    width_guard_ratio: float | None
    height_guard_ratio: float | None
    scale_height_over_width: PositiveInterval | None
    source_width_px: FiniteInterval | None
    inferred_height_px: FiniteInterval | None
    effective_height_px: FiniteInterval | None
    canonical_height_px: float | None
    width_observation_ids: tuple[ObservationId, ...]
    minimum_output_expansion_mm: float | None
    output_expansion_limit_mm: float | None
    failure_kind: ApertureAspectRatioFailureKind | None
    failure_detail: str | None
    consumed_for_cross_inference: bool = False
    blocks_cross_resolution: bool = False
    direct_height_px: FiniteInterval | None = None
    correlated_inference: bool = True
    independent_constraint_rank: int = 0

    def __post_init__(self) -> None:
        if not self.authority_id or not isinstance(self.state, EvidenceState):
            raise ValueError("aperture aspect-ratio authority is invalid")
        ids = tuple(
            item if isinstance(item, ObservationId) else ObservationId(str(item))
            for item in self.width_observation_ids
        )
        if len(set(ids)) != len(ids):
            raise ValueError("aperture aspect-ratio W provenance must be unique")
        object.__setattr__(self, "width_observation_ids", ids)
        if not self.correlated_inference or self.independent_constraint_rank != 0:
            raise ValueError("aspect-ratio inference cannot add independent rank")
        if self.consumed_for_cross_inference and self.direct_height_px is not None:
            raise ValueError("direct H and ratio-inferred H cannot both own cross")
        if self.consumed_for_cross_inference and self.blocks_cross_resolution:
            raise ValueError("consumed aspect-ratio authority cannot block cross")
        if self.state == EvidenceState.SUPPORTED:
            required = (
                self.calibration_id,
                self.axis_guard_calibration_id,
                self.raw_width_over_height,
                self.guarded_width_over_height,
                self.width_guard_mm,
                self.height_guard_mm,
                self.width_guard_ratio,
                self.height_guard_ratio,
                self.scale_height_over_width,
                self.source_width_px,
                self.inferred_height_px,
                self.effective_height_px,
                self.canonical_height_px,
                self.minimum_output_expansion_mm,
                self.output_expansion_limit_mm,
            )
            if (
                any(value is None for value in required)
                or len(ids) < 4
                or self.failure_kind is not None
                or self.failure_detail is not None
            ):
                raise ValueError("supported aspect-ratio authority is incomplete")
            assert self.effective_height_px is not None
            assert self.canonical_height_px is not None
            if not self.effective_height_px.contains(
                self.canonical_height_px,
                epsilon=1.0e-9,
            ):
                raise ValueError("canonical aspect-ratio H leaves its interval")
        elif self.state in {EvidenceState.UNAVAILABLE, EvidenceState.CONTRADICTED}:
            if self.failure_kind is None or not self.failure_detail:
                raise ValueError("failed aspect-ratio authority needs typed detail")
            if self.consumed_for_cross_inference:
                raise ValueError("failed aspect-ratio authority cannot own cross")
        else:
            raise ValueError("aspect-ratio authority has unsupported state")
        for value in (
            self.width_guard_mm,
            self.height_guard_mm,
            self.width_guard_ratio,
            self.height_guard_ratio,
            self.minimum_output_expansion_mm,
            self.output_expansion_limit_mm,
        ):
            if value is not None and (not math.isfinite(value) or value < 0.0):
                raise ValueError("aspect-ratio output budget must be non-negative")
        for value in (self.width_guard_ratio, self.height_guard_ratio):
            if value is not None and not 0.0 < value < 1.0:
                raise ValueError("aspect-ratio axis guard ratio is invalid")
        if (
            self.raw_width_over_height is not None
            and self.guarded_width_over_height is not None
            and (
                self.guarded_width_over_height.minimum
                > self.raw_width_over_height.minimum
                or self.guarded_width_over_height.maximum
                < self.raw_width_over_height.maximum
            )
        ):
            raise ValueError("aspect-ratio guard does not contain raw calibration")
        if (
            self.state == EvidenceState.SUPPORTED
            and self.minimum_output_expansion_mm is not None
            and self.output_expansion_limit_mm is not None
            and self.minimum_output_expansion_mm
            > self.output_expansion_limit_mm
        ):
            raise ValueError("supported aspect ratio exceeds output budget")
        if (
            self.failure_kind == ApertureAspectRatioFailureKind.BUDGET_EXHAUSTED
            and (
                self.minimum_output_expansion_mm is None
                or self.output_expansion_limit_mm is None
                or self.minimum_output_expansion_mm
                <= self.output_expansion_limit_mm
            )
        ):
            raise ValueError("aspect-ratio budget failure is not exhausted")


def unavailable_aperture_aspect_ratio_authority(
    detail: str = "format calibration was not registered",
) -> ApertureAspectRatioAuthority:
    return ApertureAspectRatioAuthority(
        authority_id="aperture-aspect-ratio:unavailable",
        state=EvidenceState.UNAVAILABLE,
        calibration_id=None,
        axis_guard_calibration_id=None,
        raw_width_over_height=None,
        guarded_width_over_height=None,
        width_guard_mm=None,
        height_guard_mm=None,
        width_guard_ratio=None,
        height_guard_ratio=None,
        scale_height_over_width=None,
        source_width_px=None,
        inferred_height_px=None,
        effective_height_px=None,
        canonical_height_px=None,
        width_observation_ids=(),
        minimum_output_expansion_mm=None,
        output_expansion_limit_mm=None,
        failure_kind=ApertureAspectRatioFailureKind.AUTHORITY_UNAVAILABLE,
        failure_detail=detail,
    )


__all__ = [
    "ApertureAspectRatioAuthority",
    "ApertureAspectRatioFailureKind",
    "unavailable_aperture_aspect_ratio_authority",
]
