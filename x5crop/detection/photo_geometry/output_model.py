"""Placed-frame, safety-envelope, and output-slot contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
    """One straight deskew state and the wider directly observed angle span.

    ``full_angle_interval_degrees`` is the low-dimensional feasible interval
    used by placement and output sampling.  Local edge departures, including
    slight film bend, live in ``observed_angle_interval_degrees`` and in each
    boundary's residual interval; they must not masquerade as a possible
    rotation of the complete strip.
    """

    direction_id: str
    selected_observation_ids: tuple[ObservationId, ...]
    full_angle_interval_degrees: FiniteInterval
    observed_angle_interval_degrees: FiniteInterval
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
            or not self.observed_angle_interval_degrees.contains(
                self.full_angle_interval_degrees.minimum,
                epsilon=1.0e-12,
            )
            or not self.observed_angle_interval_degrees.contains(
                self.full_angle_interval_degrees.maximum,
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


class OutputBoundaryUse(str, Enum):
    """Which physical boundary owns the final short-axis output."""

    APERTURE_PAIR = "aperture_pair"
    ENCLOSING_SUPPORT_PAIR = "enclosing_support_pair"


@dataclass(frozen=True)
class JointPlacementEnvelope:
    """All retained states of one selected placement, before product bleed."""

    placement_id: str
    projection_id: str
    lane_id: str
    lane_ordinal: int
    boundary_use: OutputBoundaryUse
    canonical_source_footprint: ConvexPolygon
    feasible_source_footprint: ConvexPolygon
    extreme_evaluation_count: int

    def __post_init__(self) -> None:
        if (
            not self.placement_id
            or not self.projection_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or self.extreme_evaluation_count <= 0
            or not isinstance(self.boundary_use, OutputBoundaryUse)
        ):
            raise ValueError("joint placement envelope identity is invalid")
        _validate_continuous_footprint(
            self.canonical_source_footprint,
            "canonical source footprint",
        )
        _validate_continuous_footprint(
            self.feasible_source_footprint,
            "feasible source footprint",
        )


@dataclass(frozen=True)
class BoundaryProtectionFact:
    """One boundary's components and final joint output protection.

    The component values are diagnostic counterfactuals.  They are not added
    to obtain ``joint_expansion_px`` because their independent extrema need
    not describe one feasible placement state.
    """

    role: BoundaryRole
    measurement_expansion_px: float
    bleed_px: float
    local_boundary_residual_px: float
    joint_expansion_px: float

    def __post_init__(self) -> None:
        if self.role not in {
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.TOP,
            BoundaryRole.BOTTOM,
        }:
            raise ValueError("boundary protection requires an output role")
        values = (
            self.measurement_expansion_px,
            self.bleed_px,
            self.local_boundary_residual_px,
            self.joint_expansion_px,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("boundary protection distances must be non-negative")


@dataclass(frozen=True)
class OutputFootprint:
    """Final selected-frame sampling requirement, including product bleed.

    The required polygon is never clipped to source authority.  When any part
    lies outside the lane, ``saturation_facts`` records the contradiction and
    ``mapped_output_box`` remains unavailable so the Gate must request review.
    """

    geometry_id: str
    envelope: JointPlacementEnvelope
    required_source_footprint: ConvexPolygon
    boundary_protections: tuple[BoundaryProtectionFact, ...]
    saturation_facts: tuple[FootprintSaturationFact, ...]
    sampling_authority_box: Box
    authority_profile_id: str
    mapped_output_box: Box | None

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or not isinstance(self.envelope, JointPlacementEnvelope)
            or not self.sampling_authority_box.valid()
            or not self.authority_profile_id
            or (
                self.mapped_output_box is not None
                and not self.mapped_output_box.valid()
            )
        ):
            raise ValueError("output footprint is invalid")
        _validate_continuous_footprint(
            self.required_source_footprint,
            "required source footprint",
        )
        if tuple(item.role for item in self.boundary_protections) != (
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.TOP,
            BoundaryRole.BOTTOM,
        ):
            raise ValueError("output footprint requires four ordered protections")
        if len({fact.authority_side for fact in self.saturation_facts}) != len(
            self.saturation_facts
        ):
            raise ValueError("saturation facts require one fact per authority side")
        if bool(self.saturation_facts) == (self.mapped_output_box is not None):
            raise ValueError("saturated output cannot expose a mapped output box")




@dataclass(frozen=True)
class DirectUseBudgetEdgeAssessment:
    role: BoundaryRole
    expansion_px: float
    expansion_mm: float
    limit_mm: float
    limit_applies: bool
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
            or not isinstance(self.limit_applies, bool)
            or self.within_limit
            != (
                self.expansion_mm <= self.limit_mm
                if self.limit_applies
                else True
            )
            or not self.worst_placement_solution_id
        ):
            raise ValueError("direct-use edge assessment is invalid")


@dataclass(frozen=True)
class DirectUseBudgetAssessment:
    geometry_id: str
    placement_solution_ids: tuple[str, ...]
    boundary_use: OutputBoundaryUse
    edge_assessments: tuple[DirectUseBudgetEdgeAssessment, ...]
    enclosing_support_height_ratio: float | None
    enclosing_support_within_limit: bool | None
    state: EvidenceState
    named_gap: str | None

    def __post_init__(self) -> None:
        available = self.state != EvidenceState.UNAVAILABLE
        if (
            not self.geometry_id
            or not isinstance(self.boundary_use, OutputBoundaryUse)
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
                and not (
                    all(item.within_limit for item in self.edge_assessments)
                    and self.enclosing_support_within_limit is not False
                )
            )
            or (
                self.state == EvidenceState.CONTRADICTED
                and all(item.within_limit for item in self.edge_assessments)
                and self.enclosing_support_within_limit is not False
            )
            or (available == (self.named_gap is not None))
        ):
            raise ValueError("direct-use budget assessment is invalid")
        support = self.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        if support != (self.enclosing_support_height_ratio is not None) or support != (
            self.enclosing_support_within_limit is not None
        ):
            raise ValueError("enclosing-support budget fields are inconsistent")
        if support and (
            not math.isfinite(float(self.enclosing_support_height_ratio))
            or float(self.enclosing_support_height_ratio) <= 1.0
        ):
            raise ValueError("enclosing-support height ratio is invalid")


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
