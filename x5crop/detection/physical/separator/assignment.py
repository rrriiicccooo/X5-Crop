from __future__ import annotations

from dataclasses import dataclass, replace

from ....domain import (
    Box,
    DimensionConstrainedBoundary,
    EvidenceState,
    FrameDimensionEstimate,
    FrameBoundary,
    MeasurementProvenance,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    VisibleSequenceSpan,
)
from ..boundary import HolderOcclusionEvidence


@dataclass(frozen=True)
class FrameBoundaryBuildResult:
    boundaries: tuple[FrameBoundary, ...]
    assignments: tuple[SeparatorAssignment, ...]


def assign_observation_to_boundary(
    boundary_index: int,
    observation: SeparatorBandObservation,
    allowed_interval: PixelInterval,
) -> SeparatorAssignment:
    observed = observation.interval
    fully_contained = bool(
        observed.minimum >= allowed_interval.minimum
        and observed.maximum <= allowed_interval.maximum
    )
    if fully_contained:
        state = EvidenceState.SUPPORTED
        geometry_dependent = False
        reason = "observation_inside_physical_interval"
    elif observed.intersects(allowed_interval):
        state = EvidenceState.UNAVAILABLE
        geometry_dependent = True
        reason = "observation_partially_intersects_physical_interval"
    else:
        state = EvidenceState.CONTRADICTED
        geometry_dependent = False
        reason = "observation_outside_physical_interval"
    return SeparatorAssignment(
        boundary_index=int(boundary_index),
        observation=observation,
        allowed_interval=allowed_interval,
        state=state,
        geometry_dependent=geometry_dependent,
        used_for_boundary=False,
        reason=reason,
    )


def frame_boundary_from_assignment(
    assignment: SeparatorAssignment,
) -> FrameBoundary:
    if not assignment.used_for_boundary:
        raise ValueError("frame boundary requires a selected separator assignment")
    return FrameBoundary(
        boundary_index=assignment.boundary_index,
        position=PixelInterval.exact(assignment.observation.center),
        source="observed_separator",
        provenance=assignment.observation.provenance,
        assignment=assignment,
    )


def dimension_constrained_boundary(
    boundary_index: int,
    position: PixelInterval,
    provenance: MeasurementProvenance,
    assignment: SeparatorAssignment | None = None,
) -> FrameBoundary:
    constraint = DimensionConstrainedBoundary(
        boundary_index=int(boundary_index),
        position=position,
        provenance=provenance,
        focused_observation=(
            assignment.observation if assignment is not None else None
        ),
    )
    return FrameBoundary(
        boundary_index=int(boundary_index),
        position=position,
        source="dimension_constrained",
        provenance=provenance,
        assignment=assignment,
        dimension_constraint=constraint,
    )


def allowed_boundary_interval(
    span: VisibleSequenceSpan,
    boundary_index: int,
    count: int,
    dimensions: FrameDimensionEstimate,
    holder_occlusion: HolderOcclusionEvidence,
) -> PixelInterval:
    if not 0 < boundary_index < count:
        raise ValueError("frame boundary index must be internal to the sequence")
    leading_hidden = holder_occlusion.leading.hidden_width_px
    trailing_hidden = holder_occlusion.trailing.hidden_width_px
    leading = PixelInterval.exact(float(span.box.left)).plus(
        dimensions.width_px.scaled(float(boundary_index))
    ).minus(leading_hidden)
    trailing = PixelInterval.exact(float(span.box.right)).minus(
        dimensions.width_px.scaled(float(count - boundary_index))
    ).plus(trailing_hidden)
    minimum = max(
        float(span.box.left),
        min(leading.minimum, trailing.minimum),
    )
    maximum = min(
        float(span.box.right),
        max(leading.maximum, trailing.maximum),
    )
    if maximum < minimum:
        midpoint = 0.5 * (minimum + maximum)
        return PixelInterval.exact(midpoint)
    return PixelInterval(minimum, maximum)


def build_frame_boundaries(
    observations: tuple[SeparatorBandObservation, ...],
    focused_observations: tuple[tuple[int, SeparatorBandObservation], ...],
    span: VisibleSequenceSpan,
    count: int,
    dimensions: FrameDimensionEstimate,
    holder_occlusion: HolderOcclusionEvidence,
) -> FrameBoundaryBuildResult:
    if count <= 1:
        return FrameBoundaryBuildResult((), ())
    used: set[int] = set()
    focused_by_index = dict(focused_observations)
    boundaries: list[FrameBoundary] = []
    best_by_observation: dict[int, SeparatorAssignment] = {}
    selected_by_observation: dict[int, SeparatorAssignment] = {}
    focused_assignments: list[SeparatorAssignment] = []
    previous_coordinate = float(span.box.left)

    def diagnostic_rank(assignment: SeparatorAssignment) -> tuple[int, float, float]:
        state_rank = {
            EvidenceState.SUPPORTED: 2,
            EvidenceState.UNAVAILABLE: 1,
            EvidenceState.CONTRADICTED: 0,
            EvidenceState.NOT_APPLICABLE: -1,
        }[assignment.state]
        return (
            state_rank,
            -abs(
                assignment.observation.center
                - assignment.allowed_interval.midpoint
            ),
            assignment.observation.score,
        )

    for boundary_index in range(1, count):
        allowed = allowed_boundary_interval(
            span,
            boundary_index,
            count,
            dimensions,
            holder_occlusion,
        )
        candidates = []
        for observation_index, observation in enumerate(observations):
            assignment = assign_observation_to_boundary(
                boundary_index,
                observation,
                allowed,
            )
            current = best_by_observation.get(observation_index)
            if current is None or diagnostic_rank(assignment) > diagnostic_rank(current):
                best_by_observation[observation_index] = assignment
            if (
                observation_index in used
                or observation.center <= previous_coordinate
                or assignment.state == EvidenceState.CONTRADICTED
            ):
                continue
            candidates.append((observation_index, assignment))
        if candidates:
            observation_index, assignment = max(
                candidates,
                key=lambda item: (
                    1 if item[1].independent else 0,
                    item[1].observation.score,
                    -abs(
                        item[1].observation.center
                        - item[1].allowed_interval.midpoint
                    ),
                ),
            )
            if assignment.independent:
                selected = replace(assignment, used_for_boundary=True)
                used.add(observation_index)
                selected_by_observation[observation_index] = selected
                boundary = frame_boundary_from_assignment(selected)
                boundaries.append(boundary)
                previous_coordinate = boundary.coordinate
                continue
            constrained = (observation_index, assignment)
        else:
            constrained = None
        focused = focused_by_index.get(boundary_index)
        if focused is not None:
            constrained_assignment = SeparatorAssignment(
                boundary_index=boundary_index,
                observation=focused,
                allowed_interval=allowed,
                state=EvidenceState.UNAVAILABLE,
                geometry_dependent=True,
                used_for_boundary=True,
                reason="focused_observation_depends_on_dimension_window",
            )
            focused_assignments.append(constrained_assignment)
        elif constrained is not None:
            observation_index, assignment = constrained
            constrained_assignment = replace(
                assignment,
                used_for_boundary=True,
            )
            used.add(observation_index)
            selected_by_observation[observation_index] = constrained_assignment
        else:
            constrained_assignment = None
        boundary = dimension_constrained_boundary(
            boundary_index,
            allowed,
            MeasurementProvenance(
                root_measurement="frame_dimensions",
                source="bidirectional_boundary_constraint",
                dependencies=(
                    dimensions.provenance.root_measurement,
                    "sequence_boundaries",
                ),
            ),
            constrained_assignment,
        )
        boundaries.append(boundary)
        previous_coordinate = boundary.coordinate
    assignments = tuple(
        selected_by_observation.get(index, best_by_observation[index])
        for index in range(len(observations))
    ) + tuple(focused_assignments)
    return FrameBoundaryBuildResult(tuple(boundaries), assignments)


def frames_from_boundaries(
    span: VisibleSequenceSpan,
    boundaries: tuple[FrameBoundary, ...],
    count: int,
) -> tuple[Box, ...]:
    if count <= 0:
        raise ValueError("frame count must be positive")
    if len(boundaries) != max(0, count - 1):
        raise ValueError("internal boundary count does not match frame count")
    ordered = tuple(sorted(boundaries, key=lambda boundary: boundary.boundary_index))
    cuts = (
        float(span.box.left),
        *(boundary.coordinate for boundary in ordered),
        float(span.box.right),
    )
    return tuple(
        Box(
            int(round(left)),
            span.box.top,
            int(round(right)),
            span.box.bottom,
        )
        for left, right in zip(cuts[:-1], cuts[1:])
    )
