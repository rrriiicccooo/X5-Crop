from __future__ import annotations

from dataclasses import dataclass, replace

from ...domain import (
    Box,
    EvidenceState,
    FrameBoundary,
    FrameDimensionPrior,
    MeasurementProvenance,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    VisibleSequenceSpan,
)
from .boundary import HolderOcclusionEvidence
from .model import PhotoInterval, SequenceResiduals
from .separator.assignment import (
    assign_observation_to_boundary,
    boundary_position_constraint,
    dimension_constrained_boundary,
    frame_boundary_from_assignment,
    separator_width_constraint,
)
from .spacing import (
    InterFrameRelation,
    observed_spacing_evidence,
    spacing_hypothesis,
)


@dataclass(frozen=True)
class SequenceSolveResult:
    photo_intervals: tuple[PhotoInterval, ...]
    frames: tuple[Box, ...]
    assignments: tuple[SeparatorAssignment, ...]
    boundaries: tuple[FrameBoundary, ...]
    relations: tuple[InterFrameRelation, ...]
    residuals: SequenceResiduals
    search_exhausted: bool


@dataclass(frozen=True)
class _AssignmentState:
    score: tuple[int, float, float, tuple[int, ...]]
    selections: tuple[tuple[int, int, SeparatorAssignment], ...]


def _assignment_score(
    selections: tuple[tuple[int, int, SeparatorAssignment], ...],
) -> tuple[int, float, float, tuple[int, ...]]:
    position_error = sum(
        abs(
            assignment.observation.center
            - assignment.position_constraint.position.midpoint
        )
        / max(1.0, assignment.position_constraint.position.maximum - assignment.position_constraint.position.minimum)
        for _boundary_index, _observation_index, assignment in selections
    )
    signal_support = sum(
        float(assignment.observation.score)
        for _boundary_index, _observation_index, assignment in selections
    )
    return (
        len(selections),
        -float(position_error),
        float(signal_support),
        tuple(-observation_index for _, observation_index, _ in selections),
    )


def _best_monotonic_assignments(
    observations: tuple[SeparatorBandObservation, ...],
    span: VisibleSequenceSpan,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionEvidence,
) -> tuple[
    dict[int, SeparatorAssignment],
    dict[int, SeparatorAssignment],
]:
    states: dict[int, _AssignmentState] = {
        -1: _AssignmentState(_assignment_score(()), ())
    }
    diagnostic: dict[int, SeparatorAssignment] = {}
    for boundary_index in range(1, count):
        position = boundary_position_constraint(
            span,
            boundary_index,
            count,
            dimensions,
            holder_occlusion,
        )
        width = separator_width_constraint(
            span,
            boundary_index,
            count,
            dimensions,
            holder_occlusion,
        )
        next_states = dict(states)
        for last_observation_index, state in states.items():
            previous_boundary_index = (
                state.selections[-1][0] if state.selections else 0
            )
            previous_center = (
                state.selections[-1][2].observation.center
                if state.selections
                else float(span.box.left)
            )
            for observation_index in range(last_observation_index + 1, len(observations)):
                observation = observations[observation_index]
                assignment = assign_observation_to_boundary(
                    boundary_index,
                    observation,
                    position,
                    width,
                )
                current = diagnostic.get(observation_index)
                if current is None or (
                    int(assignment.state == EvidenceState.SUPPORTED),
                    -abs(observation.center - position.position.midpoint),
                ) > (
                    int(current.state == EvidenceState.SUPPORTED),
                    -abs(
                        current.observation.center
                        - current.position_constraint.position.midpoint
                    ),
                ):
                    diagnostic[observation_index] = assignment
                if not assignment.independent:
                    continue
                minimum_separation = float(boundary_index - previous_boundary_index)
                if observation.center - previous_center < minimum_separation:
                    continue
                if float(span.box.right) - observation.center < float(count - boundary_index):
                    continue
                selections = (*state.selections, (boundary_index, observation_index, assignment))
                candidate = _AssignmentState(
                    _assignment_score(selections),
                    selections,
                )
                existing = next_states.get(observation_index)
                if existing is None or candidate.score > existing.score:
                    next_states[observation_index] = candidate
        states = next_states
    selected_state = max(states.values(), key=lambda state: state.score)
    selected = {
        boundary_index: replace(assignment, used_for_boundary=True)
        for boundary_index, _observation_index, assignment in selected_state.selections
    }
    return selected, diagnostic


def _cuts(
    span: VisibleSequenceSpan,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionEvidence,
    selected: dict[int, SeparatorAssignment],
    focused: dict[int, SeparatorBandObservation],
) -> tuple[tuple[FrameBoundary, ...], tuple[SeparatorAssignment, ...]]:
    boundaries: list[FrameBoundary] = []
    focused_assignments: list[SeparatorAssignment] = []
    previous = float(span.box.left)
    for boundary_index in range(1, count):
        assignment = selected.get(boundary_index)
        if assignment is not None:
            boundary = frame_boundary_from_assignment(assignment)
            boundaries.append(boundary)
            previous = boundary.coordinate
            continue
        position = boundary_position_constraint(
            span,
            boundary_index,
            count,
            dimensions,
            holder_occlusion,
        )
        lower = previous + 1.0
        upper = float(span.box.right - (count - boundary_index))
        future = tuple(
            item.observation.center
            for index, item in selected.items()
            if index > boundary_index
        )
        if future:
            next_index = min(index for index in selected if index > boundary_index)
            upper = min(
                upper,
                selected[next_index].observation.center
                - float(next_index - boundary_index),
            )
        if upper < lower:
            raise ValueError("physical sequence has no monotonic cut solution")
        coordinate = max(lower, min(upper, position.position.midpoint))
        cut_position = PixelInterval.exact(coordinate)
        focused_assignment = None
        if boundary_index in focused:
            width = separator_width_constraint(
                span,
                boundary_index,
                count,
                dimensions,
                holder_occlusion,
            )
            measured = assign_observation_to_boundary(
                boundary_index,
                focused[boundary_index],
                position,
                width,
            )
            focused_assignment = replace(
                measured,
                state=(
                    EvidenceState.CONTRADICTED
                    if measured.state == EvidenceState.CONTRADICTED
                    else EvidenceState.UNAVAILABLE
                ),
                geometry_dependent=True,
                used_for_boundary=True,
                reason="focused_observation_depends_on_sequence_solution",
            )
            focused_assignments.append(focused_assignment)
        boundary = dimension_constrained_boundary(
            boundary_index,
            cut_position,
            MeasurementProvenance(
                root_measurement="frame_dimensions",
                source="monotonic_dimension_constraint",
                dependencies=(
                    dimensions.provenance.root_measurement,
                    "sequence_boundaries",
                ),
            ),
            focused_assignment,
        )
        boundaries.append(boundary)
        previous = boundary.coordinate
    return tuple(boundaries), tuple(focused_assignments)


def _frames(
    span: VisibleSequenceSpan,
    boundaries: tuple[FrameBoundary, ...],
    count: int,
) -> tuple[Box, ...]:
    cuts = (
        float(span.box.left),
        *(boundary.coordinate for boundary in boundaries),
        float(span.box.right),
    )
    if len(cuts) != count + 1 or any(
        right <= left for left, right in zip(cuts[:-1], cuts[1:])
    ):
        raise ValueError("sequence solution requires strictly monotonic cuts")
    return tuple(
        Box(
            int(round(left)),
            span.box.top,
            int(round(right)),
            span.box.bottom,
        )
        for left, right in zip(cuts[:-1], cuts[1:])
    )


def _photo_intervals(
    boundaries: tuple[FrameBoundary, ...],
    frames: tuple[Box, ...],
) -> tuple[PhotoInterval, ...]:
    assignments = {
        boundary.boundary_index: boundary.assignment
        for boundary in boundaries
        if boundary.assignment is not None and boundary.assignment.independent
    }
    intervals: list[PhotoInterval] = []
    for index, frame in enumerate(frames, start=1):
        previous = assignments.get(index - 1)
        following = assignments.get(index)
        start = PixelInterval.exact(
            previous.observation.end if previous is not None else float(frame.left)
        )
        end = PixelInterval.exact(
            following.observation.start if following is not None else float(frame.right)
        )
        if end.maximum <= start.minimum:
            start = PixelInterval.exact(float(frame.left))
            end = PixelInterval.exact(float(frame.right))
        intervals.append(
            PhotoInterval(
                index,
                start,
                end,
                MeasurementProvenance(
                    root_measurement=(
                        "photo_edges"
                        if previous is not None or following is not None
                        else "frame_geometry"
                    ),
                    source="sequence_photo_interval",
                    dependencies=tuple(
                        dict.fromkeys(
                            item.observation.provenance.root_measurement
                            for item in (previous, following)
                            if item is not None
                        )
                    )
                    or ("sequence_cuts",),
                ),
            )
        )
    return tuple(intervals)


def _relations(
    boundaries: tuple[FrameBoundary, ...],
    dimensions: FrameDimensionPrior,
) -> tuple[InterFrameRelation, ...]:
    relations: list[InterFrameRelation] = []
    for boundary in boundaries:
        assignment = boundary.assignment
        if assignment is not None and assignment.independent:
            relations.append(
                observed_spacing_evidence(
                    boundary.boundary_index,
                    PixelInterval.exact(assignment.observation.width),
                    assignment.observation.provenance,
                )
            )
            continue
        width_constraint = (
            assignment.width_constraint.width
            if assignment is not None
            else PixelInterval(0.0, dimensions.width_px.maximum)
        )
        relations.append(
            spacing_hypothesis(
                boundary.boundary_index,
                PixelInterval(
                    -float(dimensions.width_px.maximum),
                    float(width_constraint.maximum),
                ),
                MeasurementProvenance(
                    root_measurement="frame_geometry",
                    source="unobserved_inter_frame_relation",
                    dependencies=(
                        boundary.provenance.root_measurement,
                        dimensions.provenance.root_measurement,
                    ),
                ),
            )
        )
    return tuple(relations)


def _residuals(
    span: VisibleSequenceSpan,
    photo_intervals: tuple[PhotoInterval, ...],
    boundaries: tuple[FrameBoundary, ...],
    dimensions: FrameDimensionPrior,
) -> SequenceResiduals:
    observed_widths = tuple(
        photo.width_px.midpoint
        for photo in photo_intervals
        if photo.provenance.root_measurement == "photo_edges"
    )
    target = dimensions.width_px.midpoint
    dimension = (
        max(abs(width - target) / max(1.0, target) for width in observed_widths)
        if observed_widths
        else None
    )
    boundary_uncertainty = sum(
        boundary.position.maximum - boundary.position.minimum
        for boundary in boundaries
    ) / max(1.0, float(span.box.width))
    return SequenceResiduals(
        dimension=dimension,
        conservation=None,
        boundary_uncertainty=float(boundary_uncertainty),
    )


def solve_frame_sequence(
    observations: tuple[SeparatorBandObservation, ...],
    focused_observations: tuple[tuple[int, SeparatorBandObservation], ...],
    span: VisibleSequenceSpan,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionEvidence,
) -> SequenceSolveResult:
    if count <= 0:
        raise ValueError("sequence count must be positive")
    if count == 1:
        frames = (span.box,)
        intervals = (
            PhotoInterval(
                1,
                PixelInterval.exact(float(span.box.left)),
                PixelInterval.exact(float(span.box.right)),
                MeasurementProvenance(
                    "sequence_boundaries",
                    "single_photo_interval",
                    ("sequence_boundaries",),
                ),
            ),
        )
        return SequenceSolveResult(
            intervals,
            frames,
            (),
            (),
            (),
            _residuals(span, intervals, (), dimensions),
            False,
        )
    selected, diagnostic = _best_monotonic_assignments(
        observations,
        span,
        count,
        dimensions,
        holder_occlusion,
    )
    boundaries, focused_assignments = _cuts(
        span,
        count,
        dimensions,
        holder_occlusion,
        selected,
        dict(focused_observations),
    )
    selected_observations = {
        id(assignment.observation): assignment for assignment in selected.values()
    }
    assignments = tuple(
        selected_observations.get(id(observation), diagnostic[id_index])
        for id_index, observation in enumerate(observations)
    ) + focused_assignments
    frames = _frames(span, boundaries, count)
    intervals = _photo_intervals(boundaries, frames)
    relations = _relations(boundaries, dimensions)
    return SequenceSolveResult(
        photo_intervals=intervals,
        frames=frames,
        assignments=assignments,
        boundaries=boundaries,
        relations=relations,
        residuals=_residuals(span, intervals, boundaries, dimensions),
        search_exhausted=False,
    )
