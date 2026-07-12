from __future__ import annotations

from dataclasses import dataclass, replace

from ....domain import (
    BoundaryPositionConstraint,
    Box,
    DimensionConstrainedBoundary,
    EvidenceState,
    FrameBoundary,
    FrameDimensionEstimate,
    MeasurementProvenance,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    SeparatorWidthConstraint,
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
    position_constraint: BoundaryPositionConstraint,
    width_constraint: SeparatorWidthConstraint,
) -> SeparatorAssignment:
    position = position_constraint.position
    width = float(observation.width)
    width_supported = bool(
        width_constraint.width.minimum <= width <= width_constraint.width.maximum
    )
    center_supported = bool(
        position.minimum <= observation.center <= position.maximum
    )
    if not width_supported:
        state = EvidenceState.CONTRADICTED
        geometry_dependent = False
        reason = "separator_width_outside_physical_constraint"
    elif center_supported:
        state = EvidenceState.SUPPORTED
        geometry_dependent = False
        reason = "separator_position_and_width_supported"
    elif observation.interval.intersects(position):
        state = EvidenceState.UNAVAILABLE
        geometry_dependent = True
        reason = "separator_position_geometry_dependent"
    else:
        state = EvidenceState.CONTRADICTED
        geometry_dependent = False
        reason = "separator_position_outside_physical_constraint"
    return SeparatorAssignment(
        boundary_index=int(boundary_index),
        observation=observation,
        position_constraint=position_constraint,
        width_constraint=width_constraint,
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


def boundary_position_constraint(
    span: VisibleSequenceSpan,
    boundary_index: int,
    count: int,
    dimensions: FrameDimensionEstimate,
    holder_occlusion: HolderOcclusionEvidence,
) -> BoundaryPositionConstraint:
    if not 0 < boundary_index < count:
        raise ValueError("frame boundary index must be internal to the sequence")
    leading = PixelInterval.exact(float(span.box.left)).plus(
        dimensions.width_px.scaled(float(boundary_index))
    ).minus(holder_occlusion.leading.hidden_width_px)
    trailing = PixelInterval.exact(float(span.box.right)).minus(
        dimensions.width_px.scaled(float(count - boundary_index))
    ).plus(holder_occlusion.trailing.hidden_width_px)
    minimum = max(
        float(span.box.left),
        min(leading.minimum, trailing.minimum),
    )
    maximum = min(
        float(span.box.right),
        max(leading.maximum, trailing.maximum),
    )
    position = (
        PixelInterval.exact(0.5 * (minimum + maximum))
        if maximum < minimum
        else PixelInterval(minimum, maximum)
    )
    return BoundaryPositionConstraint(
        boundary_index=int(boundary_index),
        position=position,
        provenance=MeasurementProvenance(
            root_measurement="frame_dimensions",
            source="boundary_position_constraint",
            dependencies=(
                dimensions.provenance.root_measurement,
                "sequence_boundaries",
                "holder_occlusion",
            ),
        ),
    )


def separator_width_constraint(
    span: VisibleSequenceSpan,
    boundary_index: int,
    count: int,
    dimensions: FrameDimensionEstimate,
    holder_occlusion: HolderOcclusionEvidence,
) -> SeparatorWidthConstraint:
    if not 0 < boundary_index < count:
        raise ValueError("separator width constraint index must be internal")
    occlusion = holder_occlusion.leading.hidden_width_px.plus(
        holder_occlusion.trailing.hidden_width_px
    )
    spacing_budget = PixelInterval.exact(float(span.box.width)).plus(
        occlusion
    ).minus(dimensions.width_px.scaled(float(count)))
    return SeparatorWidthConstraint(
        boundary_index=int(boundary_index),
        width=PixelInterval(0.0, max(0.0, spacing_budget.maximum)),
        provenance=MeasurementProvenance(
            root_measurement="frame_dimensions",
            source="separator_width_constraint",
            dependencies=(
                dimensions.provenance.root_measurement,
                "sequence_boundaries",
                "holder_occlusion",
            ),
        ),
    )


def _bounded_position(
    constraint: BoundaryPositionConstraint,
    previous_coordinate: float,
    span: VisibleSequenceSpan,
    boundary_index: int,
    count: int,
) -> PixelInterval:
    lower = previous_coordinate + 1.0
    upper = float(span.box.right - (count - boundary_index))
    if upper < lower:
        raise ValueError("frame sequence has no room for monotonic cuts")
    minimum = max(lower, constraint.position.minimum)
    maximum = min(upper, constraint.position.maximum)
    if maximum < minimum:
        return PixelInterval.exact(
            max(lower, min(upper, constraint.position.midpoint))
        )
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
                - assignment.position_constraint.position.midpoint
            ),
            assignment.observation.score,
        )

    for boundary_index in range(1, count):
        position_constraint = boundary_position_constraint(
            span,
            boundary_index,
            count,
            dimensions,
            holder_occlusion,
        )
        width_constraint = separator_width_constraint(
            span,
            boundary_index,
            count,
            dimensions,
            holder_occlusion,
        )
        bounded_position = _bounded_position(
            position_constraint,
            previous_coordinate,
            span,
            boundary_index,
            count,
        )
        candidates: list[tuple[int, SeparatorAssignment]] = []
        for observation_index, observation in enumerate(observations):
            assignment = assign_observation_to_boundary(
                boundary_index,
                observation,
                position_constraint,
                width_constraint,
            )
            current = best_by_observation.get(observation_index)
            if current is None or diagnostic_rank(assignment) > diagnostic_rank(current):
                best_by_observation[observation_index] = assignment
            if (
                observation_index in used
                or not assignment.independent
                or not bounded_position.minimum
                <= observation.center
                <= bounded_position.maximum
            ):
                continue
            candidates.append((observation_index, assignment))
        if candidates:
            observation_index, assignment = max(
                candidates,
                key=lambda item: (
                    item[1].observation.score,
                    -abs(
                        item[1].observation.center
                        - item[1].position_constraint.position.midpoint
                    ),
                ),
            )
            selected = replace(assignment, used_for_boundary=True)
            used.add(observation_index)
            selected_by_observation[observation_index] = selected
            boundary = frame_boundary_from_assignment(selected)
            boundaries.append(boundary)
            previous_coordinate = boundary.coordinate
            continue

        focused = focused_by_index.get(boundary_index)
        constrained_assignment = None
        if focused is not None:
            measured = assign_observation_to_boundary(
                boundary_index,
                focused,
                position_constraint,
                width_constraint,
            )
            constrained_assignment = replace(
                measured,
                state=(
                    EvidenceState.CONTRADICTED
                    if measured.state == EvidenceState.CONTRADICTED
                    else EvidenceState.UNAVAILABLE
                ),
                geometry_dependent=True,
                used_for_boundary=True,
                reason="focused_observation_depends_on_dimension_constraint",
            )
            focused_assignments.append(constrained_assignment)
        boundary = dimension_constrained_boundary(
            boundary_index,
            bounded_position,
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
    if any(right <= left for left, right in zip(cuts[:-1], cuts[1:])):
        raise ValueError("frame cuts must be strictly monotonic")
    return tuple(
        Box(
            int(round(left)),
            span.box.top,
            int(round(right)),
            span.box.bottom,
        )
        for left, right in zip(cuts[:-1], cuts[1:])
    )
