from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import EvidenceState
from ...geometry.affine import AffineCoordinateTransform
from .photo_edges import NumericInterval


class TransformOutcome(str, Enum):
    PHOTO_EDGE_PAIR_UNAVAILABLE = "photo_edge_pair_unavailable"
    ANGLE_ESTIMATION_UNAVAILABLE = "angle_estimation_unavailable"
    IDENTITY_WITHIN_TOLERANCE = "identity_within_tolerance"
    DESKEW_APPLIED = "deskew_applied"
    ANGLE_OUT_OF_RANGE = "angle_out_of_range"


@dataclass(frozen=True)
class TransformGeometryEvidence:
    outcome: TransformOutcome
    estimated_angle_degrees: float | None
    pixel_angle_interval_degrees: NumericInterval | None
    projected_edge_drift_px: float | None
    identity_drift_threshold_px: float | None
    position_uncertainty_px: float
    coordinate_transform: AffineCoordinateTransform

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, TransformOutcome):
            raise TypeError("transform geometry requires a typed outcome")
        if self.estimated_angle_degrees is not None and not math.isfinite(
            self.estimated_angle_degrees
        ):
            raise ValueError("transform geometry angle must be finite when present")
        if (self.projected_edge_drift_px is None) != (
            self.identity_drift_threshold_px is None
        ):
            raise ValueError(
                "transform edge drift and identity threshold must be present together"
            )
        if (self.estimated_angle_degrees is None) != (
            self.projected_edge_drift_px is None
        ):
            raise ValueError(
                "transform angle and projected edge drift must be present together"
            )
        if (self.estimated_angle_degrees is None) != (
            self.pixel_angle_interval_degrees is None
        ):
            raise ValueError(
                "transform angle and its joint interval must be present together"
            )
        if self.projected_edge_drift_px is not None and (
            not math.isfinite(self.projected_edge_drift_px)
            or not math.isfinite(self.identity_drift_threshold_px)
            or self.projected_edge_drift_px < 0.0
            or self.identity_drift_threshold_px <= 0.0
        ):
            raise ValueError(
                "transform edge-drift measurements must be finite and valid"
            )
        if (
            not math.isfinite(self.position_uncertainty_px)
            or self.position_uncertainty_px < 0.0
        ):
            raise ValueError("transform position uncertainty must be finite")

        measured_outcomes = {
            TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
            TransformOutcome.DESKEW_APPLIED,
        }
        measured = self.outcome in measured_outcomes
        if measured != (
            self.estimated_angle_degrees is not None
            and self.projected_edge_drift_px is not None
        ):
            raise ValueError(
                "only supported transform outcomes carry angle and edge drift"
            )

        applied = self.outcome == TransformOutcome.DESKEW_APPLIED
        if applied != (self.position_uncertainty_px > 0.0):
            raise ValueError("only an applied transform carries interpolation uncertainty")
        if applied == self.coordinate_transform.is_identity:
            raise ValueError("transform mapping must match whether deskew was applied")

    @property
    def state(self) -> EvidenceState:
        if self.outcome in {
            TransformOutcome.IDENTITY_WITHIN_TOLERANCE,
            TransformOutcome.DESKEW_APPLIED,
        }:
            return EvidenceState.SUPPORTED
        if self.outcome in {
            TransformOutcome.PHOTO_EDGE_PAIR_UNAVAILABLE,
            TransformOutcome.ANGLE_ESTIMATION_UNAVAILABLE,
            TransformOutcome.ANGLE_OUT_OF_RANGE,
        }:
            return EvidenceState.UNAVAILABLE
        raise ValueError("transform outcome has no evidence-state mapping")

    @property
    def applied(self) -> bool:
        return self.outcome == TransformOutcome.DESKEW_APPLIED

    @property
    def applied_angle_degrees(self) -> float | None:
        if not self.applied:
            return None
        assert self.estimated_angle_degrees is not None
        return -float(self.estimated_angle_degrees)
