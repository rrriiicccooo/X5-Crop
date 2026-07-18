from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import math

from ...domain import (
    BoundaryAxis,
    BoundarySide,
    Box,
    EvidenceState,
    FrameCropEnvelope,
    FrameDimensionPrior,
    GrayBoundaryPathObservation,
    HolderSafetyEnvelope,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
    SeparatorCrossAxisMeasurement,
    SeparatorBandObservation,
    ShortAxisMeasurementSpan,
)
from ...geometry.layout import HORIZONTAL, require_work_layout
from ...strip_modes import FULL, PARTIAL
from .lane_divider import LaneDividerEvidence


class GeometryIdentityError(ValueError):
    code = "geometry_identity_mismatch"


class SharedShortAxisBasis(str, Enum):
    PHOTO_EDGE_BOUNDED = "photo_edge_bounded"
    HOLDER_EDGE_BOUNDED = "holder_edge_bounded"
    CONTAINMENT_FALLBACK = "containment_fallback"


@dataclass(frozen=True)
class SharedShortAxisSafetySpan:
    top: PixelInterval
    bottom: PixelInterval
    basis: SharedShortAxisBasis
    state: EvidenceState
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.basis, SharedShortAxisBasis):
            raise TypeError("shared short-axis span requires a typed basis")
        if not isinstance(self.state, EvidenceState):
            raise TypeError("shared short-axis span requires a typed state")
        if self.bottom.minimum <= self.top.maximum:
            raise ValueError("shared short-axis span must have positive extent")
        if self.state == EvidenceState.NOT_APPLICABLE:
            raise ValueError("shared short-axis crop span is always applicable")

    @property
    def height_px(self) -> PixelInterval:
        return self.bottom.minus(self.top)

    @property
    def supports_safe_crop(self) -> bool:
        return bool(
            self.state == EvidenceState.SUPPORTED
            and self.basis != SharedShortAxisBasis.CONTAINMENT_FALLBACK
        )

    @property
    def uncertainty_px(self) -> float:
        return float(
            self.top.maximum
            - self.top.minimum
            + self.bottom.maximum
            - self.bottom.minimum
        )

    @property
    def measurement_span(self) -> ShortAxisMeasurementSpan:
        return ShortAxisMeasurementSpan(
            top=self.top,
            bottom=self.bottom,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class PhotoHeightEvidence:
    height_px: PixelInterval | None
    state: EvidenceState
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise TypeError("photo height evidence requires a typed state")
        if self.state == EvidenceState.SUPPORTED:
            if self.height_px is None or self.height_px.minimum <= 0.0:
                raise ValueError("supported photo height requires a positive interval")
        elif self.height_px is not None:
            raise ValueError("unresolved photo height cannot claim a measurement")
        if self.state == EvidenceState.NOT_APPLICABLE:
            raise ValueError("photo height evidence is always applicable")


@dataclass(frozen=True)
class FrameWidthSearchHint:
    width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.width_px.minimum <= 0.0:
            raise ValueError("frame-width search hint must be positive")


@dataclass(frozen=True)
class HolderSpanScaleHint:
    holder_span_px: PixelInterval
    count: int
    provenance: MeasurementProvenance
    width_px: PixelInterval = field(init=False)

    def __post_init__(self) -> None:
        if self.holder_span_px.minimum <= 0.0 or self.count <= 0:
            raise ValueError("holder-span scale hint requires positive geometry")
        object.__setattr__(
            self,
            "width_px",
            self.holder_span_px.scaled(1.0 / float(self.count)),
        )


@dataclass(frozen=True)
class ContentExtentConstraint:
    long_axis_extent_px: PixelInterval
    reliable_runs_px: tuple[PixelInterval, ...]
    position_uncertainty_px: int
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.long_axis_extent_px.minimum < 0.0:
            raise ValueError("content extent must use non-negative coordinates")
        if self.position_uncertainty_px < 0:
            raise ValueError("content extent uncertainty cannot be negative")
        if any(
            run.minimum < self.long_axis_extent_px.minimum
            or run.maximum > self.long_axis_extent_px.maximum
            or run.maximum <= run.minimum
            for run in self.reliable_runs_px
        ):
            raise ValueError("content runs must fit their measured extent")


@dataclass(frozen=True)
class IndexedAnchorDistanceConstraint:
    first_boundary_index: int
    second_boundary_index: int
    anchor_span_px: PixelInterval
    intermediate_spacing_px: PixelInterval
    implied_frame_width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not 0 < self.first_boundary_index < self.second_boundary_index:
            raise ValueError("indexed anchors must be ordered internal boundaries")
        if (
            self.anchor_span_px.minimum <= 0.0
            or self.implied_frame_width_px.minimum <= 0.0
        ):
            raise ValueError("indexed anchor distance requires positive geometry")
        expected_span = self.implied_frame_width_px.scaled(
            float(self.frame_index_distance)
        ).plus(self.intermediate_spacing_px)
        if not self.anchor_span_px.intersects(expected_span):
            raise ValueError("indexed anchor distance must satisfy sequence conservation")
        if self.provenance.root_measurement != MeasurementIdentity.FRAME_GEOMETRY:
            raise ValueError("indexed anchor distance is candidate geometry, not evidence")

    @property
    def frame_index_distance(self) -> int:
        return self.second_boundary_index - self.first_boundary_index


class FrameBoundarySource(str, Enum):
    SEPARATOR_EDGE_OBSERVATION = "separator_edge_observation"
    GRAY_PATH_OBSERVATION = "gray_path_observation"
    DIMENSION_CONSTRAINED = "dimension_constrained"
    HOLDER_OCCLUSION_INFERENCE = "holder_occlusion_inference"
    EXTERNAL_SAFETY_ENVELOPE = "external_safety_envelope"
    SEQUENCE_INFERENCE = "sequence_inference"


class BoundaryGeometryState(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CONTRADICTED = "contradicted"


class BoundaryRoleAuthority(str, Enum):
    UNAVAILABLE = "unavailable"
    DIRECT_MEASUREMENT = "direct_measurement"
    MEASUREMENT_CORROBORATED = "measurement_corroborated"
    GEOMETRY_CORROBORATED = "geometry_corroborated"


@dataclass(frozen=True)
class BoundaryAnchor:
    observation: GrayBoundaryPathObservation | SeparatorBandObservation
    physical_role: BoundarySide
    role_state: EvidenceState
    role_authority: BoundaryRoleAuthority
    role_provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.physical_role not in {
            BoundarySide.LEADING,
            BoundarySide.TRAILING,
        }:
            raise ValueError("frame boundary anchor requires a long-axis role")
        if not isinstance(self.role_state, EvidenceState):
            raise TypeError("frame boundary anchor requires a typed role state")
        if not isinstance(self.role_authority, BoundaryRoleAuthority):
            raise TypeError("frame boundary anchor requires typed role authority")
        if (
            self.role_state == EvidenceState.SUPPORTED
        ) != (
            self.role_authority != BoundaryRoleAuthority.UNAVAILABLE
        ):
            raise ValueError(
                "frame-edge role state and authority must describe one fact"
            )
        if self.role_state == EvidenceState.SUPPORTED and (
            self.role_provenance.root_measurement == MeasurementIdentity.FRAME_GEOMETRY
            or MeasurementIdentity.FRAME_GEOMETRY
            in self.role_provenance.dependencies
        ):
            raise ValueError(
                "supported frame-edge role cannot depend on candidate geometry"
            )
        measurement = self.observation.provenance
        if (
            self.role_provenance != measurement
            and measurement.root_measurement
            not in self.role_provenance.dependencies
            and measurement.observation_id
            not in self.role_provenance.boundary_anchors
        ):
            raise ValueError(
                "frame-edge role provenance must reference its pixel observation"
            )


@dataclass(frozen=True)
class ResolvedFrameBoundary:
    position: PixelInterval
    source: FrameBoundarySource
    geometry_state: BoundaryGeometryState
    boundary_anchor: BoundaryAnchor | None
    inference_provenance: MeasurementProvenance | None

    def __post_init__(self) -> None:
        if not isinstance(self.source, FrameBoundarySource):
            raise TypeError("frame boundary requires a typed source")
        if not isinstance(self.geometry_state, BoundaryGeometryState):
            raise TypeError("frame boundary requires a typed geometry state")
        observed_source = self.source in {
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
        }
        if observed_source:
            if self.boundary_anchor is None or self.inference_provenance is not None:
                raise ValueError("observed frame boundary requires one boundary anchor")
            observation = self.boundary_anchor.observation
            if (
                self.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
                and not isinstance(observation, GrayBoundaryPathObservation)
            ) or (
                self.source == FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
                and not isinstance(observation, SeparatorBandObservation)
            ):
                raise ValueError("frame boundary source must match its observation")
        elif self.boundary_anchor is not None or self.inference_provenance is None:
            raise ValueError("inferred frame boundary requires inference provenance")

    @property
    def role_state(self) -> EvidenceState:
        return (
            EvidenceState.UNAVAILABLE
            if self.boundary_anchor is None
            else self.boundary_anchor.role_state
        )

    @property
    def role_authority(self) -> BoundaryRoleAuthority:
        return (
            BoundaryRoleAuthority.UNAVAILABLE
            if self.boundary_anchor is None
            else self.boundary_anchor.role_authority
        )

    @property
    def position_independently_observed(self) -> bool:
        if self.boundary_anchor is None or self.source not in {
            FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION,
            FrameBoundarySource.GRAY_PATH_OBSERVATION,
        }:
            return False
        provenance = self.boundary_anchor.observation.provenance
        return bool(
            provenance.root_measurement != MeasurementIdentity.FRAME_GEOMETRY
            and MeasurementIdentity.FRAME_GEOMETRY not in provenance.dependencies
        )

    @property
    def measurement_provenance(self) -> MeasurementProvenance:
        if self.boundary_anchor is not None:
            return self.boundary_anchor.observation.provenance
        assert self.inference_provenance is not None
        return self.inference_provenance

    @property
    def role_provenance(self) -> MeasurementProvenance | None:
        return (
            None
            if self.boundary_anchor is None
            else self.boundary_anchor.role_provenance
        )

    @property
    def independently_observed(self) -> bool:
        return bool(
            self.position_independently_observed
            and self.role_state == EvidenceState.SUPPORTED
            and self.role_authority
            in {
                BoundaryRoleAuthority.DIRECT_MEASUREMENT,
                BoundaryRoleAuthority.MEASUREMENT_CORROBORATED,
            }
        )

    @property
    def geometry_resolved(self) -> bool:
        return self.geometry_state == BoundaryGeometryState.RESOLVED


def boundary_role_is_independent_physical_measurement(
    boundary: ResolvedFrameBoundary,
) -> bool:
    provenance = boundary.role_provenance
    dependent_roles = {
        MeasurementIdentity.FRAME_DIMENSIONS,
        MeasurementIdentity.FRAME_WIDTH_PATTERN,
    }
    return bool(
        boundary.independently_observed
        and provenance is not None
        and provenance.root_measurement not in dependent_roles
        and dependent_roles.isdisjoint(provenance.dependencies)
    )


class FrameContentOccupancy(str, Enum):
    CONTENT_OBSERVED = "content_observed"
    UNAVAILABLE = "unavailable"


class SequenceSlotPosition(str, Enum):
    LEADING = "leading"
    INTERIOR = "interior"
    TRAILING = "trailing"


@dataclass(frozen=True)
class SequenceInferredSlotGeometry:
    frame_index: int
    position: SequenceSlotPosition
    nominal_interval: PixelInterval
    safe_output_interval: PixelInterval
    common_width_px: PixelInterval
    inference_inputs: tuple[MeasurementProvenance, ...]
    geometry_state: BoundaryGeometryState
    measurement_state: EvidenceState
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.frame_index <= 0:
            raise ValueError("sequence inference requires a positive frame index")
        if not isinstance(self.position, SequenceSlotPosition):
            raise TypeError("sequence inference requires a typed slot position")
        if self.nominal_interval.maximum <= self.nominal_interval.minimum:
            raise ValueError("sequence-inferred slot must have positive extent")
        if self.safe_output_interval.minimum > self.nominal_interval.minimum or (
            self.safe_output_interval.maximum < self.nominal_interval.maximum
        ):
            raise ValueError(
                "sequence-inferred safe output must contain its nominal interval"
            )
        if self.common_width_px.minimum <= 0.0:
            raise ValueError("sequence inference requires a positive common width")
        if not self.inference_inputs or len(set(self.inference_inputs)) != len(
            self.inference_inputs
        ):
            raise ValueError("sequence inference requires unique physical inputs")
        if self.geometry_state != BoundaryGeometryState.RESOLVED:
            raise ValueError("only resolved sequence geometry may create a frame slot")
        if self.measurement_state != EvidenceState.UNAVAILABLE:
            raise ValueError("sequence inference is never a pixel measurement")
        if self.provenance.root_measurement != MeasurementIdentity.FRAME_GEOMETRY:
            raise ValueError("sequence inference requires geometry provenance")


@dataclass(frozen=True)
class FrameEdgeOcclusionInference:
    side: BoundarySide
    hidden_width_px: PixelInterval
    holder_boundary_provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.side not in {BoundarySide.LEADING, BoundarySide.TRAILING}:
            raise ValueError("frame edge occlusion applies only to long-axis endpoints")
        if self.hidden_width_px.minimum < 0.0:
            raise ValueError("frame edge occlusion width cannot be negative")


@dataclass(frozen=True)
class FrameSlot:
    index: int
    visible_long_axis: PixelInterval
    leading: ResolvedFrameBoundary
    trailing: ResolvedFrameBoundary
    content_occupancy: FrameContentOccupancy
    edge_occlusion: FrameEdgeOcclusionInference | None
    sequence_inference: SequenceInferredSlotGeometry | None = None

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("frame slot index must be positive")
        if not isinstance(self.content_occupancy, FrameContentOccupancy):
            raise TypeError("frame slot requires typed content occupancy")
        if self.edge_occlusion is not None and not isinstance(
            self.edge_occlusion,
            FrameEdgeOcclusionInference,
        ):
            raise TypeError("frame slot edge occlusion must be typed")
        if self.sequence_inference is not None:
            if self.sequence_inference.frame_index != self.index:
                raise ValueError("sequence inference must belong to its frame slot")
            if self.edge_occlusion is not None:
                raise ValueError("sequence inference and edge occlusion are distinct")
            if (
                self.leading.source != FrameBoundarySource.SEQUENCE_INFERENCE
                or self.trailing.source != FrameBoundarySource.SEQUENCE_INFERENCE
                or self.leading.role_state != EvidenceState.UNAVAILABLE
                or self.trailing.role_state != EvidenceState.UNAVAILABLE
                or not self.leading.geometry_resolved
                or not self.trailing.geometry_resolved
            ):
                raise ValueError(
                    "sequence-inferred boundaries must be resolved without measurement"
                )
        if self.trailing.position.minimum <= self.leading.position.maximum:
            raise ValueError("frame slot must have guaranteed positive extent")
        nominal = self.nominal_long_axis
        if self.sequence_inference is not None and (
            self.sequence_inference.nominal_interval != nominal
        ):
            raise ValueError("sequence inference must preserve its nominal interval")
        if self.sequence_inference is not None and not self.width_px.intersects(
            self.sequence_inference.common_width_px
        ):
            raise ValueError(
                "sequence-inferred boundary uncertainty must admit the common width"
            )
        visible = self.visible_long_axis
        if (
            visible.minimum < nominal.minimum
            or visible.maximum > nominal.maximum
        ):
            raise ValueError("visible frame-slot extent must lie inside nominal extent")
        if self.edge_occlusion is not None:
            expected_hidden = (
                PixelInterval.exact(visible.minimum).minus(self.leading.position)
                if self.edge_occlusion.side == BoundarySide.LEADING
                else self.trailing.position.minus(
                    PixelInterval.exact(visible.maximum)
                )
            )
            if not self.edge_occlusion.hidden_width_px.intersects(expected_hidden):
                raise ValueError("frame edge occlusion must match nominal and visible extents")

    @property
    def nominal_long_axis(self) -> PixelInterval:
        return PixelInterval(
            self.leading.position.minimum,
            self.trailing.position.maximum,
        )

    @property
    def width_px(self) -> PixelInterval:
        return self.trailing.position.minus(self.leading.position)

    @property
    def sequence_inferred(self) -> bool:
        return self.sequence_inference is not None

    def crop_envelope(
        self,
        short_axis: SharedShortAxisSafetySpan,
    ) -> FrameCropEnvelope:
        long_axis = (
            self.sequence_inference.safe_output_interval
            if self.sequence_inference is not None
            else self.visible_long_axis
        )
        return FrameCropEnvelope(
            self.index,
            Box(
                int(math.floor(long_axis.minimum)),
                int(math.floor(short_axis.top.minimum)),
                int(math.ceil(long_axis.maximum)),
                int(math.ceil(short_axis.bottom.maximum)),
            ),
        )


@dataclass(frozen=True)
class FrameWidthMeasurementConstraint:
    frame_index: int
    leading: ResolvedFrameBoundary
    trailing: ResolvedFrameBoundary

    def __post_init__(self) -> None:
        if self.frame_index <= 0:
            raise ValueError("frame-width constraint requires a positive frame index")
        if (
            not self.leading.position_independently_observed
            or not self.trailing.position_independently_observed
            or self.leading.role_state != EvidenceState.SUPPORTED
            or self.trailing.role_state != EvidenceState.SUPPORTED
        ):
            raise ValueError(
                "frame-width constraint requires observed positions with supported roles"
            )
        if (
            self.leading.boundary_anchor is None
            or self.leading.boundary_anchor.physical_role != BoundarySide.LEADING
            or self.trailing.boundary_anchor is None
            or self.trailing.boundary_anchor.physical_role != BoundarySide.TRAILING
        ):
            raise ValueError("frame-width constraint requires leading and trailing roles")
        if self.trailing.position.minimum <= self.leading.position.maximum:
            raise ValueError("frame-width constraint must have positive extent")

    @property
    def width_px(self) -> PixelInterval:
        return self.trailing.position.minus(self.leading.position)


@dataclass(frozen=True)
class FrameWidthPhysicalScaleConstraint:
    width_px: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.width_px.minimum <= 0.0:
            raise ValueError("frame-width physical-scale constraint must be positive")
        if (
            self.provenance.root_measurement != MeasurementIdentity.FRAME_DIMENSIONS
            or MeasurementIdentity.PHYSICAL_FRAME_ASPECT
            not in self.provenance.dependencies
            or MeasurementIdentity.FRAME_GEOMETRY
            in self.provenance.dependencies
        ):
            raise ValueError(
                "frame-width physical-scale constraint requires independent "
                "photo-height and physical-aspect provenance"
            )
        if not {
            MeasurementIdentity.PHOTO_EDGES,
            MeasurementIdentity.BOUNDARY_PATHS,
        }.intersection(self.provenance.dependencies):
            raise ValueError(
                "frame-width physical-scale constraint requires measured photo height"
            )


@dataclass(frozen=True)
class CommonFrameWidthResolution:
    width_px: PixelInterval | None
    constraints: tuple[FrameWidthMeasurementConstraint, ...]
    physical_scale_constraint: FrameWidthPhysicalScaleConstraint | None
    state: EvidenceState
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise TypeError("common frame width requires a typed state")
        indexes = tuple(item.frame_index for item in self.constraints)
        if len(set(indexes)) != len(indexes):
            raise ValueError("common frame-width contributors must be unique")
        if self.state == EvidenceState.SUPPORTED:
            if self.width_px is None or self.width_px.minimum <= 0.0:
                raise ValueError("supported common frame width must be positive")
            if not self.constraints:
                raise ValueError("supported common frame width requires contributors")
            if (
                self.physical_scale_constraint is None
                and len(self.constraints) < 2
            ):
                raise ValueError(
                    "common frame width requires two measured slots or physical scale"
                )
            if any(
                not constraint.width_px.intersects(self.width_px)
                for constraint in self.constraints
            ):
                raise ValueError("common frame width must satisfy every constraint")
            if (
                self.physical_scale_constraint is not None
                and not self.physical_scale_constraint.width_px.intersects(
                    self.width_px
                )
            ):
                raise ValueError(
                    "common frame width must satisfy its physical-scale constraint"
                )
        elif (
            self.width_px is not None
            or self.constraints
            or self.physical_scale_constraint is not None
        ):
            raise ValueError("unresolved common frame width cannot claim a value")

@dataclass(frozen=True)
class FrameEdgeAssignment:
    frame_index: int
    side: BoundarySide
    observation: GrayBoundaryPathObservation
    resolution: ResolvedFrameBoundary

    def __post_init__(self) -> None:
        if self.frame_index <= 0:
            raise ValueError("long-axis boundary assignment requires a frame index")
        if self.side not in {BoundarySide.LEADING, BoundarySide.TRAILING}:
            raise ValueError("long-axis assignment requires a long-axis side")
        if self.observation.provenance != self.resolution.measurement_provenance:
            raise ValueError("long-axis assignment must preserve measurement identity")
        if self.observation.axis != BoundaryAxis.LONG:
            raise ValueError("long-axis assignment requires a long-axis observation")
        if (
            self.resolution.source != FrameBoundarySource.GRAY_PATH_OBSERVATION
            or self.resolution.boundary_anchor is None
            or self.resolution.boundary_anchor.observation != self.observation
            or self.resolution.boundary_anchor.physical_role != self.side
        ):
            raise ValueError("path assignment requires its candidate role anchor")
        if not self.observation.position.intersects(self.resolution.position):
            raise ValueError("assigned path must intersect its boundary resolution")


@dataclass(frozen=True)
class SeparatorBandAssignment:
    boundary_index: int
    observation: SeparatorBandObservation
    cross_axis_measurement: SeparatorCrossAxisMeasurement
    frame_width_px: PixelInterval
    preceding_trailing_edge: ResolvedFrameBoundary
    following_leading_edge: ResolvedFrameBoundary

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("separator assignment boundary index must be positive")
        if (
            self.cross_axis_measurement.observation_id
            != self.observation.provenance.observation_id
            or not self.cross_axis_measurement.complete_separator_supported
        ):
            raise ValueError("assigned separator requires its supported measurement")
        if self.frame_width_px.minimum <= 0.0:
            raise ValueError("separator assignment requires a positive frame width")
        if self.observation.width_px.maximum >= self.frame_width_px.minimum:
            raise ValueError(
                "separator assignment cannot consume a physically possible frame slot"
            )
        expected_preceding = self.observation.leading_edge
        expected_following = self.observation.trailing_edge
        if (
            self.preceding_trailing_edge.source
            != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            or self.following_leading_edge.source
            != FrameBoundarySource.SEPARATOR_EDGE_OBSERVATION
            or self.preceding_trailing_edge.position != expected_preceding
            or self.following_leading_edge.position != expected_following
            or self.preceding_trailing_edge.measurement_provenance
            != self.observation.provenance
            or self.following_leading_edge.measurement_provenance
            != self.observation.provenance
            or self.preceding_trailing_edge.boundary_anchor is None
            or self.following_leading_edge.boundary_anchor is None
            or self.preceding_trailing_edge.boundary_anchor.physical_role
            != BoundarySide.TRAILING
            or self.following_leading_edge.boundary_anchor.physical_role
            != BoundarySide.LEADING
        ):
            raise ValueError("separator assignment must bind both observed band edges")

def _validate_geometry_identity(
    format_id: str,
    layout: str,
    strip_mode: str,
) -> None:
    if not format_id:
        raise ValueError("candidate geometry requires a format identity")
    require_work_layout(layout)
    if strip_mode not in {FULL, PARTIAL}:
        raise ValueError(f"unsupported candidate geometry mode: {strip_mode}")


@dataclass(frozen=True)
class SequenceResiduals:
    dimension: float | None
    boundary_uncertainty: float

    def __post_init__(self) -> None:
        values = tuple(
            value
            for value in (
                self.dimension,
                self.boundary_uncertainty,
            )
            if value is not None
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("sequence residuals must be finite and non-negative")


class AssignmentConsensusOutcome(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    UNCONTESTED = "uncontested"
    AGREED = "agreed"
    EXTERNAL_SAFETY_ENVELOPE = "external_safety_envelope"
    DISAGREED = "disagreed"
    COMPONENT_UNRESOLVED = "component_unresolved"


@dataclass(frozen=True)
class BoundaryAssignmentConsensus:
    outcome: AssignmentConsensusOutcome
    solution_count: int
    conflicting_frame_indexes: tuple[int, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AssignmentConsensusOutcome):
            raise TypeError("assignment consensus requires a typed outcome")
        if self.solution_count < 0:
            raise ValueError("assignment solution count cannot be negative")
        if self.outcome == AssignmentConsensusOutcome.NOT_APPLICABLE:
            if self.solution_count != 0 or self.conflicting_frame_indexes:
                raise ValueError("not-applicable consensus cannot contain solutions")
        elif self.solution_count == 0:
            raise ValueError("assignment consensus requires a solution")
        if any(index <= 0 for index in self.conflicting_frame_indexes):
            raise ValueError("conflicting frame indexes must be positive")
        if len(set(self.conflicting_frame_indexes)) != len(
            self.conflicting_frame_indexes
        ):
            raise ValueError("conflicting frame indexes must be unique")
        if (
            self.outcome == AssignmentConsensusOutcome.AGREED
            and self.conflicting_frame_indexes
        ):
            raise ValueError("agreed consensus cannot contain conflicts")
        if self.outcome == AssignmentConsensusOutcome.DISAGREED and (
            self.solution_count <= 1 or not self.conflicting_frame_indexes
        ):
            raise ValueError("disagreed consensus requires conflicting alternatives")
        state, reason = {
            AssignmentConsensusOutcome.NOT_APPLICABLE: (
                EvidenceState.NOT_APPLICABLE,
                "assignments_not_applicable",
            ),
            AssignmentConsensusOutcome.AGREED: (
                EvidenceState.SUPPORTED,
                "frame_slot_assignment_geometry_agrees",
            ),
            AssignmentConsensusOutcome.UNCONTESTED: (
                EvidenceState.SUPPORTED,
                "frame_slot_assignment_geometry_uncontested",
            ),
            AssignmentConsensusOutcome.EXTERNAL_SAFETY_ENVELOPE: (
                EvidenceState.SUPPORTED,
                "internal_assignments_agree_with_external_safety_envelope",
            ),
            AssignmentConsensusOutcome.DISAGREED: (
                EvidenceState.UNAVAILABLE,
                "alternative_frame_slot_assignments_disagree",
            ),
            AssignmentConsensusOutcome.COMPONENT_UNRESOLVED: (
                EvidenceState.UNAVAILABLE,
                "component_frame_slot_geometry_unresolved",
            ),
        }[self.outcome]
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _derived_geometry_provenance(
    signature_parts: tuple[str, ...],
    inputs: tuple[MeasurementProvenance, ...],
    description: str,
) -> MeasurementProvenance:
    unique_inputs = tuple(dict.fromkeys(inputs))
    dependencies: set[MeasurementIdentity] = set()
    anchors: set[ObservationId] = set()
    for provenance in unique_inputs:
        if provenance.root_measurement == MeasurementIdentity.FRAME_GEOMETRY:
            dependencies.update(provenance.dependencies)
        else:
            dependencies.add(provenance.root_measurement)
        anchors.add(provenance.observation_id)
        anchors.update(provenance.boundary_anchors)
    dependencies.discard(MeasurementIdentity.FRAME_GEOMETRY)
    digest = hashlib.sha256("\x1f".join(signature_parts).encode("utf-8")).hexdigest()
    return MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        observation_id=ObservationId(f"frame_sequence_geometry:{digest}"),
        dependencies=tuple(sorted(dependencies, key=lambda item: item.value)),
        description=description,
        boundary_anchors=tuple(sorted(anchors, key=str)),
    )


def _spacing_matches_frame_slots(
    spacing: InterFrameSpacing,
    left: FrameSlot,
    right: FrameSlot,
) -> bool:
    trailing_anchor = left.trailing.boundary_anchor
    leading_anchor = right.leading.boundary_anchor
    shared_observed_contact = bool(
        spacing.basis == InterFrameSpacingBasis.OBSERVED
        and spacing.kind == InterFrameSpacingKind.CONTACT
        and left.trailing.position == right.leading.position
        and boundary_role_is_independent_physical_measurement(left.trailing)
        and boundary_role_is_independent_physical_measurement(right.leading)
        and trailing_anchor is not None
        and leading_anchor is not None
        and trailing_anchor.observation == leading_anchor.observation
        and trailing_anchor.physical_role == BoundarySide.TRAILING
        and leading_anchor.physical_role == BoundarySide.LEADING
    )
    return bool(
        spacing.boundary.lane_index is None
        and spacing.boundary.boundary_index == left.index
        and right.index == left.index + 1
        and (
            shared_observed_contact
            or spacing.signed_width_px
            == right.leading.position.minus(left.trailing.position)
        )
    )


def _frame_sequence_provenance(
    format_id: str,
    layout: str,
    strip_mode: str,
    holder_safety: HolderSafetyEnvelope,
    shared_short_axis: SharedShortAxisSafetySpan,
    frame_slots: tuple[FrameSlot, ...],
    long_axis_assignments: tuple[FrameEdgeAssignment, ...],
    separator_assignments: tuple[SeparatorBandAssignment, ...],
    frame_dimension_prior: FrameDimensionPrior,
) -> MeasurementProvenance:
    boundaries = tuple(
        boundary
        for slot in frame_slots
        for boundary in (slot.leading, slot.trailing)
    )
    inputs = tuple(
        dict.fromkeys(
            (
                shared_short_axis.provenance,
                *(boundary.measurement_provenance for boundary in boundaries),
                *(
                    boundary.role_provenance
                    for boundary in boundaries
                    if boundary.role_provenance is not None
                ),
                *(
                    slot.sequence_inference.provenance
                    for slot in frame_slots
                    if slot.sequence_inference is not None
                ),
                *(item.observation.provenance for item in long_axis_assignments),
                *(item.observation.provenance for item in separator_assignments),
                frame_dimension_prior.provenance,
                *(item.provenance for item in holder_safety.boundaries),
            )
        )
    )
    box = holder_safety.box
    signature_parts = (
        format_id,
        layout,
        strip_mode,
        str(len(frame_slots)),
        f"{box.left},{box.top},{box.right},{box.bottom}",
        shared_short_axis.basis.value,
        shared_short_axis.state.value,
        *(
            f"{slot.index}:{boundary.source.value}:"
            f"{boundary.role_state.value}:{boundary.role_authority.value}:"
            f"{boundary.geometry_state.value}:"
            f"{boundary.position.minimum:.12g}:{boundary.position.maximum:.12g}:"
            f"{boundary.measurement_provenance.observation_id}:"
            f"{boundary.role_provenance.observation_id if boundary.role_provenance else 'none'}"
            for slot in frame_slots
            for boundary in (slot.leading, slot.trailing)
        ),
        *(str(item.observation_id) for item in inputs),
    )
    return _derived_geometry_provenance(
        signature_parts,
        inputs,
        "frame-slot sequence geometry derived from accepted physical inputs",
    )


@dataclass(frozen=True)
class FrameSequenceSolution:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    nominal_count: int
    holder_safety: HolderSafetyEnvelope
    shared_short_axis: SharedShortAxisSafetySpan
    photo_height_evidence: PhotoHeightEvidence
    frame_width_search_hint: FrameWidthSearchHint
    holder_span_scale_hint: HolderSpanScaleHint
    content_extent_constraint: ContentExtentConstraint
    indexed_anchor_distance_constraints: tuple[IndexedAnchorDistanceConstraint, ...]
    frame_slots: tuple[FrameSlot, ...]
    long_axis_assignments: tuple[FrameEdgeAssignment, ...]
    separator_observations: tuple[SeparatorBandObservation, ...]
    separator_assignments: tuple[SeparatorBandAssignment, ...]
    inter_frame_spacings: tuple[InterFrameSpacing, ...]
    frame_dimension_prior: FrameDimensionPrior
    common_frame_width: CommonFrameWidthResolution
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    raw_boundary_paths: tuple[GrayBoundaryPathObservation, ...]
    sequence_provenance: MeasurementProvenance = field(init=False)

    def __post_init__(self) -> None:
        _validate_geometry_identity(self.format_id, self.layout, self.strip_mode)
        if self.count <= 0 or self.nominal_count <= 0:
            raise ValueError("frame sequence counts must be positive")
        if len(self.frame_slots) != self.count:
            raise ValueError("frame sequence requires one slot per count")
        if self.holder_span_scale_hint.count != self.count:
            raise ValueError("holder-span scale hint must match sequence count")
        if tuple(slot.index for slot in self.frame_slots) != tuple(
            range(1, self.count + 1)
        ):
            raise ValueError("frame-slot indexes must be complete and ordered")
        inferred_indexes = tuple(
            slot.index for slot in self.frame_slots if slot.sequence_inferred
        )
        if len(inferred_indexes) > 1:
            raise ValueError("frame sequence may resolve at most one inferred frame slot")
        if inferred_indexes and (
            self.strip_mode != FULL
            or self.count != self.nominal_count
            or self.count <= 1
        ):
            raise ValueError(
                "slot inference requires a nominal multi-frame full sequence"
            )
        if inferred_indexes:
            slot = self.frame_slots[inferred_indexes[0] - 1]
            assert slot.sequence_inference is not None
            expected_position = (
                SequenceSlotPosition.LEADING
                if slot.index == 1
                else (
                    SequenceSlotPosition.TRAILING
                    if slot.index == self.count
                    else SequenceSlotPosition.INTERIOR
                )
            )
            if slot.sequence_inference.position != expected_position:
                raise ValueError("inferred slot position must match its sequence index")
            if self.common_frame_width.state != EvidenceState.SUPPORTED or not (
                self.common_frame_width.width_px is not None
                and
                slot.sequence_inference.common_width_px.intersects(
                    self.common_frame_width.width_px
                )
            ):
                raise ValueError("slot inference requires common frame width")
        holder = self.holder_safety.box
        canvas = self.holder_safety.containment_fallback.box
        if (
            self.shared_short_axis.top.minimum < float(canvas.top)
            or self.shared_short_axis.bottom.maximum > float(canvas.bottom)
            or any(
                slot.visible_long_axis.minimum < float(holder.left)
                or slot.visible_long_axis.maximum > float(holder.right)
                for slot in self.frame_slots
            )
        ):
            raise GeometryIdentityError(
                "visible frame-slot geometry must stay inside the holder"
            )
        for slot in self.frame_slots:
            leading_outside = slot.leading.position.minimum < float(holder.left)
            trailing_outside = slot.trailing.position.maximum > float(holder.right)
            leading_occluded = bool(
                slot.index == 1
                and slot.edge_occlusion is not None
                and slot.edge_occlusion.side == BoundarySide.LEADING
            )
            trailing_occluded = bool(
                slot.index == self.count
                and slot.edge_occlusion is not None
                and slot.edge_occlusion.side == BoundarySide.TRAILING
            )
            if (leading_outside and not leading_occluded) or (
                trailing_outside and not trailing_occluded
            ):
                raise GeometryIdentityError(
                    "nominal geometry outside the holder requires endpoint occlusion"
                )
        if any(
            right.leading.position.minimum <= left.leading.position.maximum
            or right.trailing.position.minimum <= left.trailing.position.maximum
            for left, right in zip(self.frame_slots, self.frame_slots[1:])
        ):
            raise ValueError("frame slots must be strictly monotonic")
        if len(self.inter_frame_spacings) != max(0, self.count - 1) or any(
            not _spacing_matches_frame_slots(spacing, left, right)
            for spacing, left, right in zip(
                self.inter_frame_spacings,
                self.frame_slots[:-1],
                self.frame_slots[1:],
                strict=True,
            )
        ):
            raise GeometryIdentityError("inter-frame spacing must match adjacent slots")
        if any(
            path not in self.raw_boundary_paths
            for boundary in self.holder_safety.boundaries
            for path in boundary.supporting_paths
        ) or any(
            assignment.observation not in self.raw_boundary_paths
            for assignment in self.long_axis_assignments
        ):
            raise GeometryIdentityError("frame sequence must preserve raw path identity")
        assigned_path_boundaries = {
            (assignment.frame_index, assignment.side, assignment.resolution)
            for assignment in self.long_axis_assignments
        }
        measured_path_boundaries = {
            (slot.index, side, boundary)
            for slot in self.frame_slots
            for side, boundary in (
                (BoundarySide.LEADING, slot.leading),
                (BoundarySide.TRAILING, slot.trailing),
            )
            if boundary.source == FrameBoundarySource.GRAY_PATH_OBSERVATION
        }
        if assigned_path_boundaries != measured_path_boundaries:
            raise GeometryIdentityError(
                "every measured photo edge requires one long-axis assignment"
            )
        separator_indexes = tuple(
            item.boundary_index for item in self.separator_assignments
        )
        if separator_indexes != tuple(sorted(set(separator_indexes))):
            raise GeometryIdentityError(
                "separator assignment indexes must be unique and ordered"
            )
        if any(
            item.observation not in self.separator_observations
            for item in self.separator_assignments
        ):
            raise GeometryIdentityError("separator assignments must preserve identity")
        if self.separator_assignments and (
            self.common_frame_width.state != EvidenceState.SUPPORTED
            or self.common_frame_width.width_px is None
            or any(
                not item.frame_width_px.intersects(
                    self.common_frame_width.width_px
                )
                for item in self.separator_assignments
            )
        ):
            raise GeometryIdentityError(
                "separator assignments require supported global frame width"
            )
        selected = {item.boundary_index: item for item in self.separator_assignments}
        for boundary_index, assignment in selected.items():
            if (
                self.frame_slots[boundary_index - 1].trailing
                != assignment.preceding_trailing_edge
                or self.frame_slots[boundary_index].leading
                != assignment.following_leading_edge
            ):
                raise GeometryIdentityError(
                    "separator band edges must bind adjacent frame slots"
                )
        if any(
            constraint.second_boundary_index >= self.count
            for constraint in self.indexed_anchor_distance_constraints
        ):
            raise GeometryIdentityError(
                "indexed anchor constraints must fit internal frame boundaries"
            )
        object.__setattr__(
            self,
            "sequence_provenance",
            _frame_sequence_provenance(
                self.format_id,
                self.layout,
                self.strip_mode,
                self.holder_safety,
                self.shared_short_axis,
                self.frame_slots,
                self.long_axis_assignments,
                self.separator_assignments,
                self.frame_dimension_prior,
            ),
        )

    @property
    def frame_crop_envelopes(self) -> tuple[FrameCropEnvelope, ...]:
        return tuple(
            slot.crop_envelope(self.shared_short_axis)
            for slot in self.frame_slots
        )

    @property
    def frame_sequence_envelope(self) -> Box:
        boxes = tuple(item.box for item in self.frame_crop_envelopes)
        return Box(
            min(item.left for item in boxes),
            min(item.top for item in boxes),
            max(item.right for item in boxes),
            max(item.bottom for item in boxes),
        )

    @property
    def sequence_inferred_frame_indexes(self) -> tuple[int, ...]:
        return tuple(
            slot.index for slot in self.frame_slots if slot.sequence_inferred
        )


def combined_sequence_residuals(
    lane_solutions: tuple[FrameSequenceSolution, ...],
) -> SequenceResiduals:
    if not lane_solutions:
        raise ValueError("combined residuals require lane solutions")

    def maximum(name: str) -> float | None:
        values = tuple(
            value
            for lane in lane_solutions
            if (value := getattr(lane.residuals, name)) is not None
        )
        return max(values) if values else None

    return SequenceResiduals(
        dimension=maximum("dimension"),
        boundary_uncertainty=max(
            lane.residuals.boundary_uncertainty for lane in lane_solutions
        ),
    )


def combined_assignment_consensus(
    lane_solutions: tuple[FrameSequenceSolution, ...],
) -> BoundaryAssignmentConsensus:
    if not lane_solutions:
        raise ValueError("combined assignment consensus requires lane solutions")
    resolved = all(
        lane.assignment_consensus.state == EvidenceState.SUPPORTED
        for lane in lane_solutions
    )
    return BoundaryAssignmentConsensus(
        (
            AssignmentConsensusOutcome.AGREED
            if resolved
            else AssignmentConsensusOutcome.COMPONENT_UNRESOLVED
        ),
        math.prod(
            lane.assignment_consensus.solution_count for lane in lane_solutions
        ),
        (),
    )


def _translate_boundary(
    boundary: ResolvedFrameBoundary,
    lane_box: Box,
) -> ResolvedFrameBoundary:
    return replace(
        boundary,
        position=boundary.position.plus(
            type(boundary.position).exact(float(lane_box.left))
        ),
    )


def _translate_sequence_inference(
    inference: SequenceInferredSlotGeometry | None,
    *,
    frame_index: int,
    lane_box: Box,
) -> SequenceInferredSlotGeometry | None:
    if inference is None:
        return None
    offset = PixelInterval.exact(float(lane_box.left))
    return replace(
        inference,
        frame_index=frame_index,
        nominal_interval=inference.nominal_interval.plus(offset),
        safe_output_interval=inference.safe_output_interval.plus(offset),
    )


@dataclass(frozen=True)
class DualLaneFrameSolution:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_safety: HolderSafetyEnvelope
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    lane_divider: LaneDividerEvidence
    lane_solutions: tuple[FrameSequenceSolution, ...]
    lane_boxes: tuple[Box, ...]

    @property
    def sequence_provenance(self) -> MeasurementProvenance:
        return _derived_geometry_provenance(
            (
                self.format_id,
                self.layout,
                self.strip_mode,
                str(self.count),
                str(self.lane_divider.provenance.observation_id),
                *(str(item.sequence_provenance.observation_id) for item in self.lane_solutions),
            ),
            (
                self.lane_divider.provenance,
                *(item.sequence_provenance for item in self.lane_solutions),
            ),
            "dual-lane frame geometry derived from divider and lane solutions",
        )

    @property
    def frame_slots(self) -> tuple[FrameSlot, ...]:
        slots: list[FrameSlot] = []
        next_index = 1
        for lane_box, lane in zip(self.lane_boxes, self.lane_solutions, strict=True):
            for slot in lane.frame_slots:
                leading = _translate_boundary(slot.leading, lane_box)
                trailing = _translate_boundary(slot.trailing, lane_box)
                visible_offset = PixelInterval.exact(float(lane_box.left))
                slots.append(
                    FrameSlot(
                        index=next_index,
                        visible_long_axis=slot.visible_long_axis.plus(visible_offset),
                        leading=leading,
                        trailing=trailing,
                        content_occupancy=slot.content_occupancy,
                        edge_occlusion=slot.edge_occlusion,
                        sequence_inference=_translate_sequence_inference(
                            slot.sequence_inference,
                            frame_index=next_index,
                            lane_box=lane_box,
                        ),
                    )
                )
                next_index += 1
        return tuple(slots)

    @property
    def frame_crop_envelopes(self) -> tuple[FrameCropEnvelope, ...]:
        envelopes: list[FrameCropEnvelope] = []
        next_index = 1
        for lane_box, lane in zip(self.lane_boxes, self.lane_solutions, strict=True):
            for envelope in lane.frame_crop_envelopes:
                envelopes.append(
                    FrameCropEnvelope(
                        next_index,
                        Box(
                            envelope.box.left + lane_box.left,
                            envelope.box.top + lane_box.top,
                            envelope.box.right + lane_box.left,
                            envelope.box.bottom + lane_box.top,
                        ),
                    )
                )
                next_index += 1
        return tuple(envelopes)

    @property
    def inter_frame_spacings(self) -> tuple[InterFrameSpacing, ...]:
        return tuple(
            replace(
                spacing,
                boundary=InterFrameBoundaryReference(
                    lane_index,
                    spacing.boundary.boundary_index,
                ),
            )
            for lane_index, lane in enumerate(self.lane_solutions, start=1)
            for spacing in lane.inter_frame_spacings
        )

    def __post_init__(self) -> None:
        _validate_geometry_identity(self.format_id, self.layout, self.strip_mode)
        lane_count = len(self.lane_solutions)
        if lane_count <= 1 or len(self.lane_boxes) != lane_count:
            raise ValueError("dual-lane geometry requires one box per lane solution")
        if any(not item.valid() for item in self.lane_boxes):
            raise ValueError("dual-lane boxes must have positive extent")
        if self.count != sum(item.count for item in self.lane_solutions):
            raise ValueError("dual-lane count must equal component counts")
        if any(item.layout != HORIZONTAL for item in self.lane_solutions):
            raise ValueError("dual-lane components use horizontal lane workspaces")
        if self.residuals != combined_sequence_residuals(self.lane_solutions):
            raise ValueError("dual-lane residuals must derive from lane solutions")
        if self.assignment_consensus != combined_assignment_consensus(
            self.lane_solutions
        ):
            raise ValueError("dual-lane consensus must derive from lane solutions")


@dataclass(frozen=True)
class ReviewOnlyContainment:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_safety: HolderSafetyEnvelope
    frame_dimension_prior: FrameDimensionPrior
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    sequence_provenance: MeasurementProvenance
    raw_boundary_paths: tuple[GrayBoundaryPathObservation, ...]

    def __post_init__(self) -> None:
        _validate_geometry_identity(self.format_id, self.layout, self.strip_mode)
        if self.count <= 0:
            raise ValueError("review-only count must be positive")

CandidateGeometry = (
    FrameSequenceSolution | DualLaneFrameSolution | ReviewOnlyContainment
)
