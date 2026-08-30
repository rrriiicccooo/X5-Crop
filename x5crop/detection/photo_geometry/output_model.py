"""Placed-frame, safety-envelope, and output-slot contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import Box, EvidenceState, FiniteInterval, ObservationId
from ...geometry.convex import (
    ConvexPolygon,
    clip_convex_polygon_to_box,
    convex_hull,
    signed_area,
)
from .line_observations import SourceCoordinateLine
from .model import (
    AuthoritySide,
    BoundaryRole,
    PositionSource,
)


@dataclass(frozen=True)
class SharedStripDirection:
    """One bounded direction family retained inside cross evidence.

    It can prove local parallelism and enclosing-support projection.  It never
    becomes a placement axis, rotates an output frame, or owns cosmetic
    deskew.
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
            raise ValueError("cross direction evidence is invalid")


@dataclass(frozen=True)
class FrameBoundaryGeometry:
    role: BoundaryRole
    line: SourceCoordinateLine
    reference_trace_px: float
    canonical_position_px: float
    full_position_interval_px: FiniteInterval
    local_outward_departure_px: float
    position_source: PositionSource
    position_observation_ids: tuple[ObservationId, ...]
    named_position_inference: str | None

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
        if (
            not math.isfinite(self.local_outward_departure_px)
            or self.local_outward_departure_px < 0.0
        ):
            raise ValueError("frame boundary departure must be non-negative")
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


class FootprintSaturationKind(str, Enum):
    """Why one requested output side exceeds its lane authority."""

    SOURCE_BOUNDARY_OPTIONAL_BLEED = "source_boundary_optional_bleed"
    SOURCE_BOUNDARY_JOINT_PROTECTION = (
        "source_boundary_joint_protection"
    )
    LANE_BOUNDARY_OPTIONAL_BLEED = "lane_boundary_optional_bleed"
    LANE_BOUNDARY_JOINT_PROTECTION = "lane_boundary_joint_protection"


@dataclass(frozen=True)
class FootprintSaturationFact:
    authority_side: AuthoritySide
    kind: FootprintSaturationKind
    requested_overflow_px: float
    mandatory_overflow_px: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.authority_side, AuthoritySide)
            or not isinstance(self.kind, FootprintSaturationKind)
        ):
            raise TypeError("saturation fact requires typed authority facts")
        if (
            not math.isfinite(self.requested_overflow_px)
            or self.requested_overflow_px <= 0.0
            or not math.isfinite(self.mandatory_overflow_px)
            or self.mandatory_overflow_px < 0.0
            or (
                self.kind
                in {
                    FootprintSaturationKind.SOURCE_BOUNDARY_JOINT_PROTECTION,
                    FootprintSaturationKind.LANE_BOUNDARY_JOINT_PROTECTION,
                }
            )
            != (self.mandatory_overflow_px > 0.0)
        ):
            raise ValueError("saturation distances disagree with their kind")

    @property
    def source_boundary(self) -> bool:
        return self.kind in {
            FootprintSaturationKind.SOURCE_BOUNDARY_OPTIONAL_BLEED,
            FootprintSaturationKind.SOURCE_BOUNDARY_JOINT_PROTECTION,
        }


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


def footprint_overflow_px(
    footprint: ConvexPolygon,
    authority: Box,
    side: AuthoritySide,
) -> float:
    """Return one polygon's maximum pixel-center overflow on one side."""

    if not authority.valid() or not isinstance(side, AuthoritySide):
        raise ValueError("footprint overflow requires typed source authority")
    if side == AuthoritySide.LEFT:
        return max(0.0, authority.left - min(x for x, _y in footprint))
    if side == AuthoritySide.TOP:
        return max(0.0, authority.top - min(y for _x, y in footprint))
    if side == AuthoritySide.RIGHT:
        return max(0.0, max(x for x, _y in footprint) - (authority.right - 1))
    return max(0.0, max(y for _x, y in footprint) - (authority.bottom - 1))


def footprint_outside_authority_sides(
    footprint: ConvexPolygon,
    authority: Box,
) -> tuple[AuthoritySide, ...]:
    return tuple(
        side
        for side in AuthoritySide
        if footprint_overflow_px(footprint, authority, side) > 0.0
    )


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
    """Final selected-frame source requirement and its source-edge contract.

    ``mandatory_source_footprint`` retains joint measurement uncertainty,
    line residual and complete pixel-center support.  ``requested`` also adds
    product bleed.  ``required`` equals that request except where it reaches a
    true TIFF boundary, which is the absolute limit of available source
    pixels.  The typed saturation fact preserves whether this bounded optional
    bleed or joint protection.  Internal lane boundaries are never clipped
    into approval.
    """

    geometry_id: str
    envelope: JointPlacementEnvelope
    mandatory_source_footprint: ConvexPolygon
    requested_source_footprint: ConvexPolygon
    required_source_footprint: ConvexPolygon
    boundary_protections: tuple[BoundaryProtectionFact, ...]
    saturation_facts: tuple[FootprintSaturationFact, ...]
    sampling_authority_box: Box
    authority_profile_id: str

    def __post_init__(self) -> None:
        if (
            not self.geometry_id
            or not isinstance(self.envelope, JointPlacementEnvelope)
            or not self.sampling_authority_box.valid()
            or not self.authority_profile_id
        ):
            raise ValueError("output footprint is invalid")
        _validate_continuous_footprint(
            self.mandatory_source_footprint,
            "mandatory source footprint",
        )
        _validate_continuous_footprint(
            self.requested_source_footprint,
            "requested source footprint",
        )
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
        expected_sides = footprint_outside_authority_sides(
            self.requested_source_footprint,
            self.sampling_authority_box,
        )
        if tuple(fact.authority_side for fact in self.saturation_facts) != expected_sides:
            raise ValueError("saturation facts disagree with requested footprint")
        for fact in self.saturation_facts:
            requested_overflow = footprint_overflow_px(
                self.requested_source_footprint,
                self.sampling_authority_box,
                fact.authority_side,
            )
            mandatory_overflow = footprint_overflow_px(
                self.mandatory_source_footprint,
                self.sampling_authority_box,
                fact.authority_side,
            )
            if (
                abs(fact.requested_overflow_px - requested_overflow) > 1.0e-8
                or abs(fact.mandatory_overflow_px - mandatory_overflow) > 1.0e-8
            ):
                raise ValueError("saturation fact distances are not reproducible")
        expected_required = (
            clip_convex_polygon_to_box(
                self.requested_source_footprint,
                self.sampling_authority_box,
            )
            if self.saturation_facts and self.source_authority_supported
            else self.requested_source_footprint
        )
        if self.required_source_footprint != expected_required:
            raise ValueError("required footprint disagrees with saturation contract")

    @property
    def source_authority_supported(self) -> bool:
        return all(fact.source_boundary for fact in self.saturation_facts)


@dataclass(frozen=True)
class DirectUseBudgetEdgeAssessment:
    role: BoundaryRole
    expansion_px: float
    expansion_mm: float
    limit_mm: float
    limit_applies: bool
    within_limit: bool

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
        ):
            raise ValueError("direct-use edge assessment is invalid")


@dataclass(frozen=True)
class DirectUseBudgetAssessment:
    geometry_id: str
    boundary_use: OutputBoundaryUse
    edge_assessments: tuple[DirectUseBudgetEdgeAssessment, ...]
    enclosing_support_height_ratio: float | None
    enclosing_support_within_limit: bool | None
    support_cross_alignment_padding_mm: float | None
    support_cross_alignment_within_limit: bool | None
    state: EvidenceState

    def __post_init__(self) -> None:
        supported = all(item.within_limit for item in self.edge_assessments) and (
            self.enclosing_support_within_limit is not False
        ) and (
            self.support_cross_alignment_within_limit is not False
        )
        if (
            not self.geometry_id
            or not isinstance(self.boundary_use, OutputBoundaryUse)
            or self.state not in {
                EvidenceState.SUPPORTED,
                EvidenceState.CONTRADICTED,
            }
            or tuple(item.role for item in self.edge_assessments)
            != (
                BoundaryRole.START,
                BoundaryRole.END,
                BoundaryRole.TOP,
                BoundaryRole.BOTTOM,
            )
            or (self.state == EvidenceState.SUPPORTED) != supported
        ):
            raise ValueError("direct-use budget assessment is invalid")
        support = self.boundary_use == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        if support != (self.enclosing_support_height_ratio is not None) or support != (
            self.enclosing_support_within_limit is not None
        ) or support != (
            self.support_cross_alignment_padding_mm is not None
        ) or support != (
            self.support_cross_alignment_within_limit is not None
        ):
            raise ValueError("enclosing-support budget fields are inconsistent")
        if support and (
            not math.isfinite(float(self.enclosing_support_height_ratio))
            or float(self.enclosing_support_height_ratio) <= 1.0
        ):
            raise ValueError("enclosing-support height ratio is invalid")
        if support:
            padding = float(self.support_cross_alignment_padding_mm)
            cross_limit = min(
                item.limit_mm
                for item in self.edge_assessments
                if item.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            )
            if (
                not math.isfinite(padding)
                or padding < 0.0
                or bool(self.support_cross_alignment_within_limit)
                != (padding <= cross_limit)
            ):
                raise ValueError("support cross-alignment budget is invalid")


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
