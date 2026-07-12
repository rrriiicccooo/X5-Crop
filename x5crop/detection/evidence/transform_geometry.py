from __future__ import annotations

from dataclasses import dataclass
import math

from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class TransformGeometryEvidence:
    state: EvidenceState
    applied: bool
    estimated_angle_degrees: float
    applied_angle_degrees: float
    reason: str
    span_px: float | None
    span_threshold_px: float | None

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("transform geometry evidence requires a reason")
        if not all(
            math.isfinite(value)
            for value in (
                self.estimated_angle_degrees,
                self.applied_angle_degrees,
            )
        ):
            raise ValueError("transform geometry angles must be finite")
        if self.applied:
            if (
                self.state != EvidenceState.SUPPORTED
                or self.applied_angle_degrees
                != -self.estimated_angle_degrees
            ):
                raise ValueError("applied transform must match a supported estimate")
        elif self.applied_angle_degrees != 0.0:
            raise ValueError("unapplied transform cannot carry an applied angle")

        if (self.span_px is None) != (self.span_threshold_px is None):
            raise ValueError("transform span and threshold must be present together")
        if self.span_px is not None:
            if (
                not math.isfinite(self.span_px)
                or not math.isfinite(self.span_threshold_px)
                or self.span_px < 0.0
                or self.span_threshold_px <= 0.0
            ):
                raise ValueError("transform span measurements must be finite and valid")
