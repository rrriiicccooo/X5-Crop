"""Placed-frame, safety-envelope, and output-slot contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import Box, EvidenceState, FiniteInterval, ObservationId
from ...geometry.convex import ConvexPolygon, convex_hull, signed_area
from .line_observations import SourceCoordinateLine
from .model import (
    AuthoritySide,
    BoundaryRole,
    ClippedRequirement,
    DirectionAuthority,
    PositionSource,
)

@dataclass(frozen=True)
class SharedStripDirection:
    """The sole canonical direction plus all retained angle uncertainty."""

    direction_id: str
    selected_observation_ids: tuple[ObservationId, ...]
    full_angle_interval_degrees: FiniteInterval
    canonical_angle_degrees: float

    def __post_init__(self) -> None:
        if (
            not self.direction_id
            or not self.selected_observation_ids
            or len(set(self.selected_observation_ids))
            != len(self.selected_observation_ids)
            or not self.full_angle_interval_degrees.contains(
                self.canonical_angle_degrees,
                epsilon=1.0e-12,
            )
            or not math.isfinite(self.canonical_angle_degrees)
        ):
            raise ValueError("shared strip direction is invalid")


@dataclass(frozen=True)
class FrameBoundaryGeometry:
    role: BoundaryRole
    line: SourceCoordinateLine
    reference_trace_px: float
    canonical_position_px: float
    full_position_interval_px: FiniteInterval
    full_direction_interval_degrees: FiniteInterval
    position_source: PositionSource
    position_observation_ids: tuple[ObservationId, ...]
    named_position_inference: str | None
    direction_authority: DirectionAuthority
    direction_reference_id: str

    def __post_init__(self) -> None:
        if not self.full_position_interval_px.contains(
            self.canonical_position_px,
            epsilon=1.0e-8,
        ):
            raise ValueError(
                "frame boundary interval must contain its canonical position"
            )
        if not math.isfinite(self.reference_trace_px):
            raise ValueError("frame boundary reference trace must be finite")
        observed = self.position_source == PositionSource.OBSERVED_TRANSITION
        if observed:
            if (
                not self.position_observation_ids
                or self.named_position_inference is not None
            ):
                raise ValueError("observed boundary requires pixel provenance")
        elif (
            not self.position_observation_ids
            or not self.named_position_inference
        ):
            raise ValueError("inferred boundary requires named observed inputs")
        if not self.direction_reference_id:
            raise ValueError("frame boundary requires direction provenance")
        if self.role in {BoundaryRole.START, BoundaryRole.END}:
            if (
                self.direction_authority
                != DirectionAuthority.BOUNDED_SEQUENCE_EDGE_DIRECTION
            ):
                raise ValueError(
                    "start/end require bounded sequence-edge direction"
                )
        elif (
            self.direction_authority
            != DirectionAuthority.SHARED_TOP_BOTTOM_DIRECTION
        ):
            raise ValueError("top/bottom must use shared canonical direction")

@dataclass(frozen=True)
class FootprintSaturationFact:
    authority_side: AuthoritySide
    clipped_requirements: tuple[ClippedRequirement, ...]

    def __post_init__(self) -> None:
        if (
            not self.clipped_requirements
            or len(set(self.clipped_requirements))
            != len(self.clipped_requirements)
        ):
            raise ValueError("saturation fact requires unique clipped facts")


def _validate_continuous_footprint(
    footprint: ConvexPolygon,
    name: str,
) -> None:
    if (
        len(footprint) < 3
        or any(
            not math.isfinite(value)
            for point in footprint
            for value in point
        )
        or signed_area(footprint) <= 1.0e-9
    ):
        raise ValueError(f"{name} must be a finite non-degenerate CCW polygon")
    if convex_hull(footprint) != footprint:
        raise ValueError(f"{name} must be an ordered convex hull")


@dataclass(frozen=True)
class SafeCropEnvelope:
    geometry_id: str
    lane_id: str
    lane_ordinal: int
    placement_source_footprint: ConvexPolygon
    required_source_footprint: ConvexPolygon
    constrained_source_footprint: ConvexPolygon
    saturation_facts: tuple[FootprintSaturationFact, ...]
    sampling_authority_box: Box
    authority_profile_id: str
    mapped_output_box: Box | None = None
    provenance: str = "selected_placement_safety_footprint"

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or not self.sampling_authority_box.valid()
            or not self.authority_profile_id
            or (
                self.mapped_output_box is not None
                and not self.mapped_output_box.valid()
            )
            or self.provenance
            != "selected_placement_safety_footprint"
        ):
            raise ValueError("safe crop envelope is invalid")
        _validate_continuous_footprint(
            self.placement_source_footprint,
            "placement source footprint",
        )
        _validate_continuous_footprint(
            self.required_source_footprint,
            "required source footprint",
        )
        _validate_continuous_footprint(
            self.constrained_source_footprint,
            "constrained source footprint",
        )
        if len({fact.authority_side for fact in self.saturation_facts}) != len(
            self.saturation_facts
        ):
            raise ValueError("saturation facts require one fact per authority side")




@dataclass(frozen=True)
class DirectUseBudgetEdgeAssessment:
    role: BoundaryRole
    expansion_px: float
    expansion_mm: float
    limit_mm: float
    within_limit: bool
    worst_placement_solution_id: str

    def __post_init__(self) -> None:
        if (
            self.role
            not in {
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            }
            or any(
                not math.isfinite(value) or value < 0.0
                for value in (
                    self.expansion_px,
                    self.expansion_mm,
                    self.limit_mm,
                )
            )
            or self.within_limit
            != (self.expansion_mm <= self.limit_mm)
            or not self.worst_placement_solution_id
        ):
            raise ValueError("direct-use edge assessment is invalid")


@dataclass(frozen=True)
class DirectUseBudgetAssessment:
    geometry_id: str
    placement_solution_ids: tuple[str, ...]
    edge_assessments: tuple[DirectUseBudgetEdgeAssessment, ...]
    state: EvidenceState
    named_gap: str | None

    def __post_init__(self) -> None:
        available = self.state != EvidenceState.UNAVAILABLE
        if (
            not self.geometry_id
            or available != bool(self.placement_solution_ids)
            or len(set(self.placement_solution_ids))
            != len(self.placement_solution_ids)
            or available != bool(self.edge_assessments)
            or (
                available
                and tuple(item.role for item in self.edge_assessments)
                != (
                    BoundaryRole.START,
                    BoundaryRole.END,
                    BoundaryRole.TOP,
                    BoundaryRole.BOTTOM,
                )
            )
            or (
                self.state == EvidenceState.SUPPORTED
                and not all(item.within_limit for item in self.edge_assessments)
            )
            or (
                self.state == EvidenceState.CONTRADICTED
                and all(item.within_limit for item in self.edge_assessments)
            )
            or (available == (self.named_gap is not None))
        ):
            raise ValueError("direct-use budget assessment is invalid")


@dataclass(frozen=True)
class ResolvedOutputSlots:
    lane_output_slot_counts: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.lane_output_slot_counts or any(
            value <= 0 for value in self.lane_output_slot_counts
        ):
            raise ValueError(
                "resolved output slots require one positive count per lane"
            )

    @property
    def output_slot_count(self) -> int:
        return sum(self.lane_output_slot_counts)


@dataclass(frozen=True)
class OutputSlotIdentity:
    global_output_ordinal: int
    lane_id: str
    lane_ordinal: int

    def __post_init__(self) -> None:
        if (
            self.global_output_ordinal <= 0
            or not self.lane_id
            or self.lane_ordinal <= 0
        ):
            raise ValueError("output slot identity is invalid")
