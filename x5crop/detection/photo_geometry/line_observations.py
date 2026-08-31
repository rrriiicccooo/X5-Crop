"""Fitted source-line and tracked transition-region observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import FiniteInterval, ObservationId
from .model import BoundaryAxis, BoundaryRole, SPATIAL_SUPPORT_REGION_COUNT


@dataclass(frozen=True)
class SourceCoordinateLine:
    """Normalized line ``normal_x*x + normal_y*y = offset``."""

    normal_x: float
    normal_y: float
    offset_px: float
    support_projection_px: FiniteInterval
    source_axis_long: BoundaryAxis

    def __post_init__(self) -> None:
        values = (self.normal_x, self.normal_y, self.offset_px)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("source-coordinate line must be finite")
        if not math.isclose(
            math.hypot(self.normal_x, self.normal_y),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-8,
        ):
            raise ValueError(
                "source-coordinate line normal must be unit length"
            )

    def intersection(
        self,
        other: "SourceCoordinateLine",
    ) -> tuple[float, float]:
        determinant = (
            self.normal_x * other.normal_y
            - self.normal_y * other.normal_x
        )
        if abs(determinant) <= 1.0e-12:
            raise ValueError("parallel boundary lines do not intersect")
        return (
            (
                self.offset_px * other.normal_y
                - self.normal_y * other.offset_px
            )
            / determinant,
            (
                self.normal_x * other.offset_px
                - self.offset_px * other.normal_x
            )
            / determinant,
        )


@dataclass(frozen=True)
class RobustLineFitReceipt:
    method: str
    converged: bool
    status: int
    evaluation_count: int
    cost: float
    optimality: float

    def __post_init__(self) -> None:
        if (
            self.method != "scipy_least_squares_huber"
            or not self.converged
            or self.status <= 0
            or self.evaluation_count <= 0
            or not math.isfinite(self.cost)
            or self.cost < 0.0
            or not math.isfinite(self.optimality)
            or self.optimality < 0.0
        ):
            raise ValueError("robust line-fit receipt is invalid")


@dataclass(frozen=True)
class PhotoBoundaryObservation:
    observation_id: ObservationId
    role: BoundaryRole
    line: SourceCoordinateLine
    offset_interval_px: FiniteInterval
    fit_residual_px: float
    angle_interval_degrees: FiniteInterval
    trace_support_count: int
    queried_trace_count: int
    independent_support_region_count: int
    continuous_support_fraction: float
    transition_ids: tuple[ObservationId, ...]
    fit_receipt: RobustLineFitReceipt
    left_background_preference_fraction: float = 0.0
    right_background_preference_fraction: float = 0.0
    fit_angle_interval_degrees: FiniteInterval | None = None
    source_spanning_continuous: bool = False
    trace_coordinates_px: tuple[int, ...] = ()
    trace_position_intervals_px: tuple[FiniteInterval, ...] = ()

    def __post_init__(self) -> None:
        if self.fit_angle_interval_degrees is None:
            object.__setattr__(
                self,
                "fit_angle_interval_degrees",
                self.angle_interval_degrees,
            )
        fit_angle = self.fit_angle_interval_degrees
        assert fit_angle is not None
        if (
            not self.offset_interval_px.contains(
                self.line.offset_px,
                epsilon=1.0e-8,
            )
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or self.trace_support_count <= 0
            or self.queried_trace_count < self.trace_support_count
            or not 1
            <= self.independent_support_region_count
            <= SPATIAL_SUPPORT_REGION_COUNT
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not 0.0
            <= self.left_background_preference_fraction
            <= 1.0
            or not 0.0
            <= self.right_background_preference_fraction
            <= 1.0
            or not self.transition_ids
            or (
                bool(self.trace_coordinates_px)
                != bool(self.trace_position_intervals_px)
            )
            or (
                self.trace_coordinates_px
                and (
                    tuple(sorted(set(self.trace_coordinates_px)))
                    != self.trace_coordinates_px
                    or len(self.trace_coordinates_px)
                    != len(self.trace_position_intervals_px)
                    or any(
                        not isinstance(item, FiniteInterval)
                        for item in self.trace_position_intervals_px
                    )
                )
            )
            or not self.angle_interval_degrees.contains(
                fit_angle.minimum,
                epsilon=1.0e-9,
            )
            or not self.angle_interval_degrees.contains(
                fit_angle.maximum,
                epsilon=1.0e-9,
            )
        ):
            raise ValueError("photo-boundary observation is invalid")
        if len(set(self.transition_ids)) != len(self.transition_ids):
            raise ValueError("line transition identities must be unique")

class TransitionRegionMeasurementBasis(str, Enum):
    DIRECT_TRACE = "direct_trace"
    CROSS_HEIGHT_AGGREGATE = "cross_height_aggregate"
    BROAD_MATERIAL_AGGREGATE = "broad_material_aggregate"


@dataclass(frozen=True)
class SideTransitionRegion:
    """Direction-free physical region from tracked transitions."""

    region_id: str
    position_interval_px: FiniteInterval
    transition_ids: tuple[ObservationId, ...]
    trace_support_count: int
    queried_trace_count: int
    independent_support_region_count: int
    continuous_support_fraction: float
    fit_residual_px: float
    mean_gradient_z: float
    mean_tone_or_texture_z: float
    left_background_preference_fraction: float
    right_background_preference_fraction: float
    ambiguous: bool = False
    measurement_basis: TransitionRegionMeasurementBasis = (
        TransitionRegionMeasurementBasis.DIRECT_TRACE
    )

    def __post_init__(self) -> None:
        if (
            not self.region_id
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or len(self.transition_ids) != self.trace_support_count
            or self.trace_support_count <= 0
            or self.queried_trace_count < self.trace_support_count
            or not 1
            <= self.independent_support_region_count
            <= SPATIAL_SUPPORT_REGION_COUNT
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
            or not math.isfinite(self.mean_gradient_z)
            or self.mean_gradient_z < 0.0
            or not math.isfinite(self.mean_tone_or_texture_z)
            or self.mean_tone_or_texture_z < 0.0
            or not 0.0
            <= self.left_background_preference_fraction
            <= 1.0
            or not 0.0
            <= self.right_background_preference_fraction
            <= 1.0
            or not isinstance(
                self.measurement_basis,
                TransitionRegionMeasurementBasis,
            )
        ):
            raise ValueError("side transition region is invalid")
