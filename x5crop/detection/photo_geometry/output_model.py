"""Placed-frame, safety-envelope, and output-slot contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from ...domain import Box, EvidenceState, FiniteInterval, ObservationId, WorkspaceExtent
from ...geometry.convex import (
    ContinuousBox,
    ConvexPolygon,
    clip_convex_polygon_to_bounds,
    convex_hull,
    signed_area,
)
from .line_observations import SourceCoordinateLine
from .source_geometry import SourceFixedOutputSize
from .template_model import SequenceRoleLineEvidence
from .model import (
    AuthoritySide,
    BoundaryAxis,
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
    position_source: PositionSource
    position_observation_ids: tuple[ObservationId, ...]
    named_position_inference: str | None
    line_evidence: SequenceRoleLineEvidence | None = None

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
        if self.line_evidence is not None and (
            self.role not in {BoundaryRole.START, BoundaryRole.END}
            or self.line_evidence.observation_id not in self.position_observation_ids
        ):
            raise ValueError("sequence protection line lost its boundary provenance")
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


def source_boundary_sides(
    authority: Box,
    source_extent: WorkspaceExtent,
) -> tuple[AuthoritySide, ...]:
    """Identify true TIFF sides, independently of whether a crop reaches them."""

    if (
        not isinstance(source_extent, WorkspaceExtent)
        or not authority.valid()
        or any(type(value) is not int for value in (
            authority.left, authority.top, authority.right, authority.bottom
        ))
        or authority.left < 0
        or authority.top < 0
        or authority.right > source_extent.width
        or authority.bottom > source_extent.height
    ):
        raise ValueError("sampling authority must lie inside the TIFF source extent")
    return tuple(
        side for side, touches in (
            (AuthoritySide.LEFT, authority.left == 0),
            (AuthoritySide.TOP, authority.top == 0),
            (AuthoritySide.RIGHT, authority.right == source_extent.width),
            (AuthoritySide.BOTTOM, authority.bottom == source_extent.height),
        ) if touches
    )


def sampling_authority_bounds(
    authority: Box,
    source_extent: WorkspaceExtent,
) -> ContinuousBox:
    """Use physical pixel-cell limits only at true source sides.

    Internal lane boundaries retain their original center-domain limits and
    cannot gain the source-edge saturation permission.
    """

    source_sides = source_boundary_sides(authority, source_extent)
    return (
        authority.left - (0.5 if AuthoritySide.LEFT in source_sides else 0.0),
        authority.top - (0.5 if AuthoritySide.TOP in source_sides else 0.0),
        authority.right - (0.5 if AuthoritySide.RIGHT in source_sides else 1.0),
        authority.bottom - (0.5 if AuthoritySide.BOTTOM in source_sides else 1.0),
    )


def footprint_overflow_px(
    footprint: ConvexPolygon,
    authority: Box,
    side: AuthoritySide,
    source_extent: WorkspaceExtent,
) -> float:
    """Return overflow beyond the actual continuous authority on one side."""

    if not isinstance(side, AuthoritySide):
        raise ValueError("footprint overflow requires typed source authority")
    left, top, right, bottom = sampling_authority_bounds(authority, source_extent)
    if side == AuthoritySide.LEFT:
        return max(0.0, left - min(x for x, _y in footprint))
    if side == AuthoritySide.TOP:
        return max(0.0, top - min(y for _x, y in footprint))
    if side == AuthoritySide.RIGHT:
        return max(0.0, max(x for x, _y in footprint) - right)
    return max(0.0, max(y for _x, y in footprint) - bottom)


def footprint_outside_authority_sides(
    footprint: ConvexPolygon,
    authority: Box,
    source_extent: WorkspaceExtent,
) -> tuple[AuthoritySide, ...]:
    return tuple(
        side
        for side in AuthoritySide
        if footprint_overflow_px(footprint, authority, side, source_extent) > 0.0
    )


class OutputBoundaryUse(str, Enum):
    """Which physical boundary owns the final short-axis output."""

    APERTURE_PAIR = "aperture_pair"
    ENCLOSING_SUPPORT_PAIR = "enclosing_support_pair"


class SequenceProjectionConstraintBasis(str, Enum):
    """Long-axis constraints consumed by one joint footprint projection."""

    MODEL_INTERVALS = "model_intervals"
    GLOBAL_LATTICE_AUTHORITY = "global_lattice_authority"


@dataclass(frozen=True)
class JointPlacementEnvelope:
    """All retained states of one selected placement, before fixed-window placement."""

    placement_id: str
    projection_id: str
    lane_id: str
    lane_ordinal: int
    boundary_use: OutputBoundaryUse
    canonical_source_footprint: ConvexPolygon
    feasible_source_footprint: ConvexPolygon
    extreme_evaluation_count: int
    sequence_constraint_basis: SequenceProjectionConstraintBasis
    global_lattice_constraint_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.placement_id
            or not self.projection_id
            or not self.lane_id
            or self.lane_ordinal <= 0
            or self.extreme_evaluation_count <= 0
            or not isinstance(self.boundary_use, OutputBoundaryUse)
            or not isinstance(
                self.sequence_constraint_basis,
                SequenceProjectionConstraintBasis,
            )
            or len(set(self.global_lattice_constraint_ids))
            != len(self.global_lattice_constraint_ids)
            or any(
                not identity
                for identity in self.global_lattice_constraint_ids
            )
            or (
                self.sequence_constraint_basis
                == SequenceProjectionConstraintBasis.GLOBAL_LATTICE_AUTHORITY
            )
            != bool(self.global_lattice_constraint_ids)
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
    """Physical diagnostics, independent of the fixed output size."""

    role: BoundaryRole
    measurement_expansion_px: float
    local_boundary_residual_px: float
    required_expansion_px: float

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
            self.local_boundary_residual_px,
            self.required_expansion_px,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("boundary protection distances must be non-negative")


@dataclass(frozen=True)
class EnclosingSupportApertureRisk:
    """Worst same-state output distance from the authorized aperture center.

    A supported calibrated authority narrows the aperture-center offset from
    the support midpoint.  If that authority is unavailable or contradicted,
    the risk conservatively retains every canonical-H position physically
    contained by the support.  These are safety distances, not output
    mutations.
    """

    aperture_authority_id: str
    aperture_authority_state: EvidenceState
    canonical_height_px: float
    center_offset_interval_px: FiniteInterval
    maximum_center_shift_px: float
    top_expansion_px: float
    bottom_expansion_px: float
    feasible_state_count: int

    def __post_init__(self) -> None:
        values = (
            self.canonical_height_px,
            self.maximum_center_shift_px,
            self.top_expansion_px,
            self.bottom_expansion_px,
        )
        if (
            not self.aperture_authority_id
            or not isinstance(self.aperture_authority_state, EvidenceState)
            or not isinstance(self.center_offset_interval_px, FiniteInterval)
            or any(not math.isfinite(value) for value in values)
            or self.canonical_height_px <= 0.0
            or self.maximum_center_shift_px < 0.0
            or self.top_expansion_px < 0.0
            or self.bottom_expansion_px < 0.0
            or self.feasible_state_count <= 0
        ):
            raise ValueError("enclosing-support aperture risk is invalid")
        expected_shift = max(
            abs(self.center_offset_interval_px.minimum),
            abs(self.center_offset_interval_px.maximum),
        )
        if abs(self.maximum_center_shift_px - expected_shift) > 1.0e-8:
            raise ValueError(
                "enclosing-support center shift disagrees with its interval"
            )


def _polygon_bounds(polygon: ConvexPolygon) -> tuple[float, float, float, float]:
    return (min(x for x, _ in polygon), min(y for _, y in polygon),
            max(x for x, _ in polygon), max(y for _, y in polygon))


def visible_mandatory_footprint(polygon: ConvexPolygon, extent: WorkspaceExtent) -> ConvexPolygon:
    # Internal lane boundaries never authorize clipping protected content.
    return clip_convex_polygon_to_bounds(polygon, (-0.5, -0.5, extent.width - 0.5, extent.height - 0.5))


def fixed_output_rectangle(
    size: SourceFixedOutputSize, width_axis: BoundaryAxis,
    mandatory: ConvexPolygon, source_extent: WorkspaceExtent,
    *, preferred_center: tuple[float, float] | None = None,
) -> ConvexPolygon:
    """Contain visible protection, preferring a complete true-source window.

    If containment is impossible, retain the fitted position for Review.
    The complete mandatory footprint still blocks the output budget.
    """
    visible = visible_mandatory_footprint(mandatory, source_extent)
    left, top, right, bottom = _polygon_bounds(visible)
    dimensions = ((size.output_width_px, size.output_height_px) if width_axis == BoundaryAxis.X
                  else (size.output_height_px, size.output_width_px))
    preferred = preferred_center or ((left + right) / 2.0, (top + bottom) / 2.0)
    centers = []
    for minimum, maximum, dimension, target, source_length in zip(
        (left, top), (right, bottom), dimensions, preferred,
        (source_extent.width, source_extent.height), strict=True,
    ):
        lower, upper = maximum - dimension / 2.0, minimum + dimension / 2.0
        if lower > upper:
            centers.append(target)
            continue
        source_lower = max(lower, dimension / 2.0 - 0.5)
        source_upper = min(upper, source_length - 0.5 - dimension / 2.0)
        if source_lower <= source_upper:
            lower, upper = source_lower, source_upper
        centers.append(min(max(target, lower), upper))
    cx, cy = centers
    dx, dy = dimensions[0] / 2.0, dimensions[1] / 2.0
    return convex_hull(((cx - dx, cy - dy), (cx + dx, cy - dy),
                        (cx + dx, cy + dy), (cx - dx, cy + dy)))


def fixed_output_coverage(
    output: OutputFootprint | CommonOutputFootprint,
    *, requested: ConvexPolygon | None = None, geometry_id: str | None = None,
) -> DirectUseBudgetAssessment:
    """Reproduce containment without a per-side actual outward cap."""
    window = requested if requested is not None else output.requested_source_footprint
    left, top, right, bottom = _polygon_bounds(window)
    ml, mt, mr, mb = _polygon_bounds(visible_mandatory_footprint(output.mandatory_source_footprint, output.source_extent))
    cx, cy = (left + right) / 2.0, (top + bottom) / 2.0
    reach = {"left": max(0.0, cx - ml), "right": max(0.0, mr - cx),
             "top": max(0.0, cy - mt), "bottom": max(0.0, mb - cy)}
    available = {"left": (right - left) / 2.0, "right": (right - left) / 2.0,
                 "top": (bottom - top) / 2.0, "bottom": (bottom - top) / 2.0}
    sequence = ("left", "right") if output.width_axis == BoundaryAxis.X else ("top", "bottom")
    if output.sequence_direction < 0:
        sequence = sequence[::-1]
    cross = ("top", "bottom") if output.width_axis == BoundaryAxis.X else ("left", "right")
    edges = tuple(DirectUseBudgetEdgeAssessment(role, reach[side], available[side], reach[side] <= available[side] + 1.0e-8)
                  for role, side in zip((BoundaryRole.START, BoundaryRole.END, BoundaryRole.TOP, BoundaryRole.BOTTOM),
                                        sequence + cross, strict=True))
    return DirectUseBudgetAssessment(geometry_id or output.geometry_id, output.boundary_use, edges,
                                    EvidenceState.SUPPORTED if all(edge.within_limit for edge in edges) else EvidenceState.CONTRADICTED)


def _validate_source_requirement(output: OutputFootprint | CommonOutputFootprint) -> None:
    """One source/clipping contract for native and shared output requirements."""

    if not output.geometry_id or not output.sampling_authority_box.valid() or not output.authority_profile_id:
        raise ValueError("output footprint is invalid")
    for polygon, name in (
        (output.mandatory_source_footprint, "mandatory source footprint"),
        (output.requested_source_footprint, "requested source footprint"),
        (output.required_source_footprint, "required source footprint"),
    ):
        _validate_continuous_footprint(polygon, name)
    canonical = output.envelope.canonical_source_footprint if isinstance(output, OutputFootprint) else None
    preferred = None if canonical is None else (
        (min(x for x, _ in canonical) + max(x for x, _ in canonical)) / 2.0,
        (min(y for _, y in canonical) + max(y for _, y in canonical)) / 2.0,
    )
    expected_window = fixed_output_rectangle(output.fixed_size, output.width_axis,
        output.mandatory_source_footprint, output.source_extent, preferred_center=preferred)
    if output.requested_source_footprint != expected_window:
        raise ValueError("requested footprint disagrees with the fixed output window")
    if len({fact.authority_side for fact in output.saturation_facts}) != len(output.saturation_facts):
        raise ValueError("saturation facts require one fact per authority side")
    expected_sides = footprint_outside_authority_sides(
        output.requested_source_footprint, output.sampling_authority_box, output.source_extent,
    )
    if tuple(fact.authority_side for fact in output.saturation_facts) != expected_sides:
        raise ValueError("saturation facts disagree with requested footprint")
    for fact in output.saturation_facts:
        if fact.source_boundary != (fact.authority_side in source_boundary_sides(
            output.sampling_authority_box, output.source_extent,
        )):
            raise ValueError("saturation kind disagrees with the TIFF source extent")
        requested_overflow = footprint_overflow_px(
            output.requested_source_footprint, output.sampling_authority_box,
            fact.authority_side, output.source_extent,
        )
        mandatory_overflow = footprint_overflow_px(
            output.mandatory_source_footprint, output.sampling_authority_box,
            fact.authority_side, output.source_extent,
        )
        if (abs(fact.requested_overflow_px - requested_overflow) > 1.0e-8
                or abs(fact.mandatory_overflow_px - mandatory_overflow) > 1.0e-8):
            raise ValueError("saturation fact distances are not reproducible")
    expected_required = (
        clip_convex_polygon_to_bounds(
            output.requested_source_footprint,
            sampling_authority_bounds(output.sampling_authority_box, output.source_extent),
        )
        if output.saturation_facts and output.source_authority_supported
        else output.requested_source_footprint
    )
    if output.required_source_footprint != expected_required:
        raise ValueError("required footprint disagrees with saturation contract")


@dataclass(frozen=True)
class OutputFootprint:
    """Physical requirement and a fixed source-axis crop window.

    Mandatory retains the complete feasible physical envelope. Requested is
    exactly 1.1W by 1.1H; required clips it only at true TIFF boundaries.
    Diagnostic boundary/support distances never resize the window.
    """

    geometry_id: str
    fixed_size: SourceFixedOutputSize
    width_axis: BoundaryAxis
    sequence_direction: int
    envelope: JointPlacementEnvelope
    mandatory_source_footprint: ConvexPolygon
    requested_source_footprint: ConvexPolygon
    required_source_footprint: ConvexPolygon
    boundary_protections: tuple[BoundaryProtectionFact, ...]
    maximum_same_state_cross_alignment_padding_px: float | None
    enclosing_support_aperture_risk: EnclosingSupportApertureRisk | None
    saturation_facts: tuple[FootprintSaturationFact, ...]
    sampling_authority_box: Box
    source_extent: WorkspaceExtent
    authority_profile_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.fixed_size, SourceFixedOutputSize):
            raise ValueError("output requires the source fixed-size identity")
        if not isinstance(self.width_axis, BoundaryAxis) or self.sequence_direction not in {-1, 1}:
            raise ValueError("fixed output requires source axis ownership")
        if not isinstance(self.envelope, JointPlacementEnvelope):
            raise ValueError("output footprint is invalid")
        _validate_source_requirement(self)
        if tuple(item.role for item in self.boundary_protections) != (
            BoundaryRole.START,
            BoundaryRole.END,
            BoundaryRole.TOP,
            BoundaryRole.BOTTOM,
        ):
            raise ValueError("output footprint requires four ordered protections")
        support = (
            self.envelope.boundary_use
            == OutputBoundaryUse.ENCLOSING_SUPPORT_PAIR
        )
        if support != (
            self.maximum_same_state_cross_alignment_padding_px is not None
        ) or support != (
            self.enclosing_support_aperture_risk is not None
        ):
            raise ValueError(
                "same-state cross risk requires enclosing support"
            )
        if support and (
            not math.isfinite(
                float(self.maximum_same_state_cross_alignment_padding_px)
            )
            or float(self.maximum_same_state_cross_alignment_padding_px) < 0.0
        ):
            raise ValueError("same-state cross padding is invalid")

    @property
    def source_authority_supported(self) -> bool:
        return all(fact.source_boundary for fact in self.saturation_facts)

    @property
    def lane_id(self) -> str:
        return self.envelope.lane_id

    @property
    def lane_ordinal(self) -> int:
        return self.envelope.lane_ordinal

    @property
    def boundary_use(self) -> OutputBoundaryUse:
        return self.envelope.boundary_use


@dataclass(frozen=True)
class DirectUseBudgetEdgeAssessment:
    """Visible mandatory reach from the fixed window center on one side."""

    role: BoundaryRole
    required_extent_px: float
    available_extent_px: float
    within_limit: bool

    def __post_init__(self) -> None:
        if (self.role not in {BoundaryRole.START, BoundaryRole.END, BoundaryRole.TOP, BoundaryRole.BOTTOM}
                or not math.isfinite(self.required_extent_px) or self.required_extent_px < 0.0
                or not math.isfinite(self.available_extent_px) or self.available_extent_px <= 0.0
                or type(self.within_limit) is not bool
                or self.within_limit != (self.required_extent_px <= self.available_extent_px + 1.0e-8)):
            raise ValueError("fixed-output coverage edge is invalid")


@dataclass(frozen=True)
class DirectUseBudgetAssessment:
    """Containment of visible mandatory content by a fixed output window."""

    geometry_id: str
    boundary_use: OutputBoundaryUse
    edge_assessments: tuple[DirectUseBudgetEdgeAssessment, ...]
    state: EvidenceState

    def __post_init__(self) -> None:
        if (not self.geometry_id or not isinstance(self.boundary_use, OutputBoundaryUse)
                or self.state not in {EvidenceState.SUPPORTED, EvidenceState.CONTRADICTED}
                or tuple(item.role for item in self.edge_assessments)
                != (BoundaryRole.START, BoundaryRole.END, BoundaryRole.TOP, BoundaryRole.BOTTOM)
                or (self.state == EvidenceState.SUPPORTED) != all(item.within_limit for item in self.edge_assessments)):
            raise ValueError("fixed-output coverage assessment is invalid")


@dataclass(frozen=True)
class CommonOutputMemberBudget:
    """A common requirement evaluated against one native interpretation."""

    placement_id: str
    native_geometry_id: str
    assessment: DirectUseBudgetAssessment

    def __post_init__(self) -> None:
        if not self.placement_id or not self.native_geometry_id or not isinstance(self.assessment, DirectUseBudgetAssessment):
            raise ValueError("common-output budget requires native interpretation identity")


@dataclass(frozen=True)
class CommonOutputFootprint:
    """One crop covering named native H outputs, with per-member budgets.

    This is a geometric proof over the supplied set, not evidence that the
    set is complete or that its members have final placement authority.
    Native envelopes and protection facts keep their own identities.
    """

    geometry_id: str
    fixed_size: SourceFixedOutputSize
    members: tuple[OutputFootprint, ...]
    mandatory_source_footprint: ConvexPolygon
    requested_source_footprint: ConvexPolygon
    required_source_footprint: ConvexPolygon
    member_budgets: tuple[CommonOutputMemberBudget, ...]
    saturation_facts: tuple[FootprintSaturationFact, ...]
    sampling_authority_box: Box
    source_extent: WorkspaceExtent
    authority_profile_id: str

    def __post_init__(self) -> None:
        if not self.members or any(not isinstance(member, OutputFootprint) for member in self.members):
            raise ValueError("common output requires native members")
        identities = tuple((m.envelope.placement_id, m.geometry_id) for m in self.members)
        if (len({p for p, _ in identities}) != len(identities)
                or len({g for _, g in identities}) != len(identities)
                or self.geometry_id in {g for _, g in identities}):
            raise ValueError("common output must preserve distinct member identities")
        first = self.members[0].envelope
        if any(
            member.envelope.lane_id != first.lane_id
            or member.envelope.lane_ordinal != first.lane_ordinal
            or member.envelope.boundary_use != first.boundary_use
            or member.sampling_authority_box != self.sampling_authority_box
            or member.source_extent != self.source_extent
            or member.authority_profile_id != self.authority_profile_id
            or member.fixed_size != self.fixed_size
            or member.width_axis != self.members[0].width_axis
            or member.sequence_direction != self.members[0].sequence_direction
            for member in self.members
        ):
            raise ValueError("common H output changed lane, slot or source authority")
        expected = convex_hull(tuple(point for member in self.members for point in member.mandatory_source_footprint))
        if self.mandatory_source_footprint != expected:
            raise ValueError("common output lost a native member requirement")
        if (
            tuple((b.placement_id, b.native_geometry_id) for b in self.member_budgets) != identities
            or any(b.assessment.geometry_id != self.geometry_id
                   or b.assessment.boundary_use != first.boundary_use
                   for b in self.member_budgets)
        ):
            raise ValueError("common output budgets do not cover every native member")
        _validate_source_requirement(self)

    @property
    def width_axis(self) -> BoundaryAxis:
        return self.members[0].width_axis

    @property
    def sequence_direction(self) -> int:
        return self.members[0].sequence_direction

    @property
    def source_authority_supported(self) -> bool:
        return all(fact.source_boundary for fact in self.saturation_facts)

    @property
    def budget_supported(self) -> bool:
        return all(member.assessment.state == EvidenceState.SUPPORTED for member in self.member_budgets)

    @property
    def lane_id(self) -> str:
        return self.members[0].lane_id

    @property
    def lane_ordinal(self) -> int:
        return self.members[0].lane_ordinal

    @property
    def boundary_use(self) -> OutputBoundaryUse:
        return self.members[0].envelope.boundary_use


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
