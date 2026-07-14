from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import math

from ...domain import (
    BoundarySide,
    Box,
    ContainmentFallback,
    EvidenceState,
    FrameCropEnvelope,
    FrameDimensionPrior,
    GrayBoundaryPathObservation,
    HolderBoundaryObservation,
    HolderSpan,
    InterPhotoBoundaryReference,
    InterPhotoSpacing,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoAperture,
    PhotoApertureEdgeAssignment,
    PhotoApertureEdgeSource,
    SeparatorWidthConstraint,
    PhotoApertureBoundaryResolution,
    PixelInterval,
    SeparatorBandAssignment,
    SeparatorBandObservation,
)
from ...geometry.layout import HORIZONTAL, require_work_layout
from ...strip_modes import FULL, PARTIAL
from .lane_divider import LaneDividerEvidence


class GeometryIdentityError(ValueError):
    code = "geometry_identity_mismatch"


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
    DISAGREED = "disagreed"
    COMPONENT_UNRESOLVED = "component_unresolved"


@dataclass(frozen=True)
class BoundaryAssignmentConsensus:
    outcome: AssignmentConsensusOutcome
    solution_count: int
    conflicting_photo_indexes: tuple[int, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AssignmentConsensusOutcome):
            raise TypeError("assignment consensus requires a typed outcome")
        if self.solution_count < 0:
            raise ValueError("assignment solution count cannot be negative")
        if self.outcome == AssignmentConsensusOutcome.NOT_APPLICABLE:
            if self.solution_count != 0 or self.conflicting_photo_indexes:
                raise ValueError("not-applicable consensus cannot contain solutions")
        elif self.solution_count == 0:
            raise ValueError("assignment consensus requires a solution")
        if any(index <= 0 for index in self.conflicting_photo_indexes):
            raise ValueError("conflicting photo indexes must be positive")
        if len(set(self.conflicting_photo_indexes)) != len(
            self.conflicting_photo_indexes
        ):
            raise ValueError("conflicting photo indexes must be unique")
        if (
            self.outcome == AssignmentConsensusOutcome.AGREED
            and self.conflicting_photo_indexes
        ):
            raise ValueError("agreed consensus cannot contain conflicts")
        if self.outcome == AssignmentConsensusOutcome.DISAGREED and (
            self.solution_count <= 1 or not self.conflicting_photo_indexes
        ):
            raise ValueError("disagreed consensus requires conflicting alternatives")
        state, reason = {
            AssignmentConsensusOutcome.NOT_APPLICABLE: (
                EvidenceState.NOT_APPLICABLE,
                "assignments_not_applicable",
            ),
            AssignmentConsensusOutcome.AGREED: (
                EvidenceState.SUPPORTED,
                "aperture_assignment_geometry_agrees",
            ),
            AssignmentConsensusOutcome.UNCONTESTED: (
                EvidenceState.SUPPORTED,
                "aperture_assignment_geometry_uncontested",
            ),
            AssignmentConsensusOutcome.DISAGREED: (
                EvidenceState.UNAVAILABLE,
                "alternative_aperture_assignments_disagree",
            ),
            AssignmentConsensusOutcome.COMPONENT_UNRESOLVED: (
                EvidenceState.UNAVAILABLE,
                "component_aperture_geometry_unresolved",
            ),
        }[self.outcome]
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _spacing_matches_apertures(
    spacing: InterPhotoSpacing,
    left: PhotoAperture,
    right: PhotoAperture,
) -> bool:
    return bool(
        spacing.boundary.lane_index is None
        and spacing.boundary.boundary_index == left.index
        and right.index == left.index + 1
        and spacing.signed_width_px
        == right.leading.position.minus(left.trailing.position)
    )


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
        observation_id=ObservationId(f"photo_sequence_geometry:{digest}"),
        dependencies=tuple(sorted(dependencies, key=lambda item: item.value)),
        description=description,
        boundary_anchors=tuple(sorted(anchors, key=str)),
    )


def _photo_sequence_provenance(
    format_id: str,
    layout: str,
    strip_mode: str,
    count: int,
    holder_span: HolderSpan,
    photo_apertures: tuple[PhotoAperture, ...],
    aperture_edge_assignments: tuple[PhotoApertureEdgeAssignment, ...],
    separator_assignments: tuple[SeparatorBandAssignment, ...],
    frame_dimension_prior: FrameDimensionPrior,
    holder_boundaries: tuple[HolderBoundaryObservation, ...],
) -> MeasurementProvenance:
    boundaries = tuple(
        boundary
        for aperture in photo_apertures
        for boundary in (
            aperture.leading,
            aperture.trailing,
            aperture.top,
            aperture.bottom,
        )
    )
    inputs = tuple(
        dict.fromkeys(
            (
                *(boundary.provenance for boundary in boundaries),
                *(item.observation.provenance for item in aperture_edge_assignments),
                *(item.observation.provenance for item in separator_assignments),
                frame_dimension_prior.provenance,
                *(item.provenance for item in holder_boundaries),
            )
        )
    )
    box = holder_span.box
    signature_parts = (
        format_id,
        layout,
        strip_mode,
        str(count),
        f"{box.left},{box.top},{box.right},{box.bottom}",
        *(
            f"{item.photo_index}:{item.side.value}:{item.source.value}:"
            f"{item.state.value}:{item.position.minimum:.12g}:"
            f"{item.position.maximum:.12g}:{item.provenance.observation_id}"
            for item in boundaries
        ),
        *(str(item.observation_id) for item in inputs),
    )
    return _derived_geometry_provenance(
        signature_parts,
        inputs,
        "photo aperture sequence geometry derived from accepted physical inputs",
    )


@dataclass(frozen=True)
class PhotoSequenceSolution:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    photo_apertures: tuple[PhotoAperture, ...]
    aperture_edge_assignments: tuple[PhotoApertureEdgeAssignment, ...]
    separator_observations: tuple[SeparatorBandObservation, ...]
    separator_assignments: tuple[SeparatorBandAssignment, ...]
    inter_photo_spacings: tuple[InterPhotoSpacing, ...]
    frame_dimension_prior: FrameDimensionPrior
    photo_width_constraint_px: PixelInterval
    photo_height_constraint_px: PixelInterval
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    raw_boundary_paths: tuple[GrayBoundaryPathObservation, ...]
    holder_boundaries: tuple[HolderBoundaryObservation, ...]
    sequence_provenance: MeasurementProvenance = field(init=False)

    def __post_init__(self) -> None:
        _validate_geometry_identity(self.format_id, self.layout, self.strip_mode)
        if self.count <= 0:
            raise ValueError("photo sequence count must be positive")
        if len(self.photo_apertures) != self.count:
            raise ValueError("photo sequence requires one aperture per count")
        if tuple(item.index for item in self.photo_apertures) != tuple(
            range(1, self.count + 1)
        ):
            raise ValueError("photo aperture indexes must be complete and ordered")
        holder = self.holder_span.box
        if any(
            aperture.leading.position.minimum < float(holder.left)
            or aperture.trailing.position.maximum > float(holder.right)
            or aperture.top.position.minimum < float(holder.top)
            or aperture.bottom.position.maximum > float(holder.bottom)
            for aperture in self.photo_apertures
        ):
            raise GeometryIdentityError(
                "photo aperture uncertainty must stay inside the holder span"
            )
        if (
            self.photo_width_constraint_px.minimum <= 0.0
            or self.photo_height_constraint_px.minimum <= 0.0
        ):
            raise ValueError("photo aperture dimension constraints must be positive")
        interior_apertures = self.photo_apertures[1:-1]
        if any(
            not aperture.trailing.position.minus(
                aperture.leading.position
            ).intersects(self.photo_width_constraint_px)
            for aperture in interior_apertures
        ) or any(
            not aperture.bottom.position.minus(
                aperture.top.position
            ).intersects(self.photo_height_constraint_px)
            for aperture in self.photo_apertures
        ):
            raise ValueError("photo apertures must satisfy physical dimension constraints")
        if any(
            right.leading.position.minimum <= left.leading.position.maximum
            or right.trailing.position.minimum <= left.trailing.position.maximum
            for left, right in zip(self.photo_apertures, self.photo_apertures[1:])
        ):
            raise ValueError("photo aperture order must be strictly monotonic")
        if len(self.inter_photo_spacings) != max(0, self.count - 1):
            raise ValueError("photo sequence has incomplete inter-photo spacing")
        if any(
            not _spacing_matches_apertures(spacing, left, right)
            for spacing, left, right in zip(
                self.inter_photo_spacings,
                self.photo_apertures[:-1],
                self.photo_apertures[1:],
                strict=True,
            )
        ):
            raise GeometryIdentityError(
                "inter-photo spacing must derive from adjacent aperture edges"
            )
        if any(
            path not in self.raw_boundary_paths
            for item in self.holder_boundaries
            for path in item.supporting_paths
        ):
            raise GeometryIdentityError(
                "holder boundaries must preserve every raw path identity"
            )
        if any(
            item.observation not in self.raw_boundary_paths
            for item in self.aperture_edge_assignments
        ):
            raise GeometryIdentityError(
                "aperture edge assignments must preserve raw path identity"
            )
        aperture_boundaries = tuple(
            boundary
            for aperture in self.photo_apertures
            for boundary in (
                aperture.leading,
                aperture.trailing,
                aperture.top,
                aperture.bottom,
            )
        )
        measured_path_edges = {
            item
            for item in aperture_boundaries
            if item.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
        }
        assigned_path_edges = {
            item.resolution for item in self.aperture_edge_assignments
        }
        if measured_path_edges != assigned_path_edges:
            raise GeometryIdentityError(
                "every measured aperture edge requires exactly one path assignment"
            )
        if len(assigned_path_edges) != len(self.aperture_edge_assignments):
            raise GeometryIdentityError("aperture edge assignments must be unique")
        if len({item.boundary_index for item in self.separator_assignments}) != len(
            self.separator_assignments
        ):
            raise GeometryIdentityError("separator boundary assignments must be unique")
        if any(
            item.observation not in self.separator_observations
            for item in self.separator_assignments
        ):
            raise GeometryIdentityError(
                "separator assignments must preserve raw observation identity"
            )
        separator_edges = {
            item
            for item in aperture_boundaries
            if item.source == PhotoApertureEdgeSource.SEPARATOR_BAND_EDGE
        }
        assigned_separator_edges = {
            edge
            for assignment in self.separator_assignments
            for edge in (
                assignment.preceding_trailing_edge,
                assignment.following_leading_edge,
            )
        }
        if separator_edges != assigned_separator_edges:
            raise GeometryIdentityError(
                "every separator aperture edge requires exactly one band assignment"
            )
        selected = {item.boundary_index: item for item in self.separator_assignments}
        expected_separator_width = SeparatorWidthConstraint(
            self.photo_width_constraint_px
        )
        if any(
            item.width_constraint != expected_separator_width
            for item in self.separator_assignments
        ):
            raise GeometryIdentityError(
                "separator assignments must preserve the sequence width constraint"
            )
        for boundary_index in range(1, self.count):
            assignment = selected.get(boundary_index)
            if assignment is None:
                continue
            left = self.photo_apertures[boundary_index - 1]
            right = self.photo_apertures[boundary_index]
            if (
                left.trailing != assignment.preceding_trailing_edge
                or right.leading != assignment.following_leading_edge
            ):
                raise GeometryIdentityError(
                    "separator band edges must bind adjacent photo apertures"
                )
        object.__setattr__(
            self,
            "sequence_provenance",
            _photo_sequence_provenance(
                self.format_id,
                self.layout,
                self.strip_mode,
                self.count,
                self.holder_span,
                self.photo_apertures,
                self.aperture_edge_assignments,
                self.separator_assignments,
                self.frame_dimension_prior,
                self.holder_boundaries,
            ),
        )

    @property
    def frame_crop_envelopes(self) -> tuple[FrameCropEnvelope, ...]:
        return tuple(item.frame_crop_envelope for item in self.photo_apertures)

    @property
    def photo_sequence_envelope(self) -> Box:
        boxes = tuple(item.box for item in self.frame_crop_envelopes)
        return Box(
            min(item.left for item in boxes),
            min(item.top for item in boxes),
            max(item.right for item in boxes),
            max(item.bottom for item in boxes),
        )


def combined_sequence_residuals(
    lane_solutions: tuple[PhotoSequenceSolution, ...],
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
    lane_solutions: tuple[PhotoSequenceSolution, ...],
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
    boundary: PhotoApertureBoundaryResolution,
    lane_box: Box,
) -> PhotoApertureBoundaryResolution:
    offset = (
        lane_box.left
        if boundary.side in {BoundarySide.LEADING, BoundarySide.TRAILING}
        else lane_box.top
    )
    return replace(
        boundary,
        position=boundary.position.plus(
            type(boundary.position).exact(float(offset))
        ),
    )


def _translate_aperture(aperture: PhotoAperture, lane_box: Box) -> PhotoAperture:
    return PhotoAperture(
        aperture.index,
        _translate_boundary(aperture.leading, lane_box),
        _translate_boundary(aperture.trailing, lane_box),
        _translate_boundary(aperture.top, lane_box),
        _translate_boundary(aperture.bottom, lane_box),
    )


@dataclass(frozen=True)
class DualLanePhotoSolution:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    lane_divider: LaneDividerEvidence
    lane_solutions: tuple[PhotoSequenceSolution, ...]
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
            "dual-lane photo geometry derived from divider and lane solutions",
        )

    @property
    def photo_apertures(self) -> tuple[PhotoAperture, ...]:
        apertures: list[PhotoAperture] = []
        next_index = 1
        for lane_box, lane in zip(self.lane_boxes, self.lane_solutions, strict=True):
            for aperture in lane.photo_apertures:
                apertures.append(
                    replace(
                        _translate_aperture(aperture, lane_box),
                        index=next_index,
                        leading=replace(
                            _translate_boundary(aperture.leading, lane_box),
                            photo_index=next_index,
                        ),
                        trailing=replace(
                            _translate_boundary(aperture.trailing, lane_box),
                            photo_index=next_index,
                        ),
                        top=replace(
                            _translate_boundary(aperture.top, lane_box),
                            photo_index=next_index,
                        ),
                        bottom=replace(
                            _translate_boundary(aperture.bottom, lane_box),
                            photo_index=next_index,
                        ),
                    )
                )
                next_index += 1
        return tuple(apertures)

    @property
    def frame_crop_envelopes(self) -> tuple[FrameCropEnvelope, ...]:
        return tuple(item.frame_crop_envelope for item in self.photo_apertures)

    @property
    def inter_photo_spacings(self) -> tuple[InterPhotoSpacing, ...]:
        return tuple(
            replace(
                spacing,
                boundary=InterPhotoBoundaryReference(
                    lane_index,
                    spacing.boundary.boundary_index,
                ),
            )
            for lane_index, lane in enumerate(self.lane_solutions, start=1)
            for spacing in lane.inter_photo_spacings
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
    holder_span: HolderSpan
    containment_fallback: ContainmentFallback
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
    PhotoSequenceSolution | DualLanePhotoSolution | ReviewOnlyContainment
)
