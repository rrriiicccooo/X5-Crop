from __future__ import annotations

from dataclasses import dataclass
import math

from ..domain import EvidenceState, FiniteInterval
from ..geometry.affine import AffineCoordinateTransform
from .photo_geometry.line_observations import PhotoBoundaryObservation
from .photo_geometry.output_model import SharedStripDirection


def observed_strip_angle_estimate_degrees(
    observations: tuple[PhotoBoundaryObservation, ...],
) -> float:
    """Return one angle inside all retained direction evidence.

    Trace count and fit residual remain report evidence; they cannot pull a
    shared physical direction toward one side.  Prefer the common robust-fit
    interval, falling back to the common full measurement interval.  Complete
    chain selection still owns the canonical output direction.
    """

    if not observations:
        raise ValueError("strip-angle estimate requires observations")
    fit_minimum = max(
        item.fit_angle_interval_degrees.minimum for item in observations
    )
    fit_maximum = min(
        item.fit_angle_interval_degrees.maximum for item in observations
    )
    if fit_minimum <= fit_maximum:
        estimate = (fit_minimum + fit_maximum) / 2.0
    else:
        full_minimum = max(
            item.angle_interval_degrees.minimum for item in observations
        )
        full_maximum = min(
            item.angle_interval_degrees.maximum for item in observations
        )
        if full_minimum > full_maximum:
            raise ValueError("strip-angle observations have no common direction")
        estimate = (full_minimum + full_maximum) / 2.0
    if not math.isfinite(estimate):
        raise ValueError("strip-angle estimate is not finite")
    return estimate


@dataclass(frozen=True)
class SharedStripDirectionResolution:
    direction: SharedStripDirection | None
    state: EvidenceState
    named_gap: str | None

    def __post_init__(self) -> None:
        supported = self.state == EvidenceState.SUPPORTED
        if (
            supported != (self.direction is not None)
            or supported == (self.named_gap is not None)
        ):
            raise ValueError("shared strip direction resolution is inconsistent")


@dataclass(frozen=True)
class OutputTransformAssessment:
    transform: AffineCoordinateTransform | None
    outcome: str
    state: EvidenceState
    named_gap: str | None
    observed_angle_interval_degrees: FiniteInterval | None
    applied_source_rotation_degrees: float | None
    authority: str | None

    def __post_init__(self) -> None:
        if self.outcome not in {
            "identity",
            "shared_rotation",
            "unavailable",
        }:
            raise ValueError("unknown output-transform outcome")
        if self.authority not in {
            None,
            "shared_strip_direction",
        }:
            raise ValueError("unknown output-transform authority")
        supported = self.state == EvidenceState.SUPPORTED
        if supported:
            if (
                self.transform is None
                or self.named_gap is not None
                or self.observed_angle_interval_degrees is None
                or self.applied_source_rotation_degrees is None
                or self.authority is None
            ):
                raise ValueError("supported transform assessment is incomplete")
            if (
                self.outcome == "identity"
                and (
                    not self.transform.is_identity
                    or self.applied_source_rotation_degrees != 0.0
                    or not self.observed_angle_interval_degrees.contains(0.0)
                )
            ):
                raise ValueError("identity transform lacks zero-angle evidence")
            if (
                self.outcome == "shared_rotation"
                and (
                    self.authority != "shared_strip_direction"
                    or
                    self.transform.is_identity
                    or self.applied_source_rotation_degrees == 0.0
                )
            ):
                raise ValueError("shared rotation must be non-identity")
        elif (
            self.outcome != "unavailable"
            or self.transform is not None
            or self.named_gap is None
            or self.applied_source_rotation_degrees is not None
            or self.authority is not None
        ):
            raise ValueError("unavailable transform assessment is inconsistent")




def output_transform_assessment(
    direction_resolution: SharedStripDirectionResolution,
    *,
    layout: str,
    source_width: int,
    source_height: int,
) -> OutputTransformAssessment:
    """Build one transform directly from the resolved canonical direction."""

    if layout not in {"horizontal", "vertical"}:
        raise ValueError(f"unsupported transform layout: {layout}")
    if min(source_width, source_height) <= 0:
        raise ValueError("output transform requires positive source extent")
    direction = direction_resolution.direction
    if direction is None:
        return OutputTransformAssessment(
            transform=None,
            outcome="unavailable",
            state=EvidenceState.UNAVAILABLE,
            named_gap=direction_resolution.named_gap,
            observed_angle_interval_degrees=None,
            applied_source_rotation_degrees=None,
            authority=None,
        )
    canonical_angle = direction.canonical_angle_degrees
    common = direction.full_angle_interval_degrees
    if canonical_angle == 0.0:
        return OutputTransformAssessment(
            transform=AffineCoordinateTransform.identity(
                source_width,
                source_height,
            ),
            outcome="identity",
            state=EvidenceState.SUPPORTED,
            named_gap=None,
            observed_angle_interval_degrees=common,
            applied_source_rotation_degrees=0.0,
            authority="shared_strip_direction",
        )
    source_rotation = -canonical_angle
    return OutputTransformAssessment(
        transform=AffineCoordinateTransform.expanded_rotation(
            source_width,
            source_height,
            source_rotation,
        ),
        outcome="shared_rotation",
        state=EvidenceState.SUPPORTED,
        named_gap=None,
        observed_angle_interval_degrees=common,
        applied_source_rotation_degrees=source_rotation,
        authority="shared_strip_direction",
    )
