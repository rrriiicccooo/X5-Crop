from __future__ import annotations

from dataclasses import dataclass, replace

from ...domain import (
    BoundaryKind,
    BoundaryObservation,
    BoundarySide,
    Box,
    EvidenceState,
    FrameBoundary,
    FrameBoundaryReference,
    FrameDimensionPrior,
    MeasurementIdentity,
    MeasurementProvenance,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    VisibleSequenceSpan,
)
from .boundary import (
    HolderOcclusionConstraint,
    HolderOcclusionEvidence,
    holder_occlusion_constraint,
    holder_occlusion_for_sequence,
    visible_sequence_length_interval,
)
from .model import (
    AssignmentConsensusOutcome,
    BoundaryAssignmentConsensus,
    PhotoInterval,
    SequenceResiduals,
)
from .separator.assignment import (
    assign_observation_to_boundary,
    boundary_position_constraint,
    dimension_constrained_boundary,
    frame_boundary_from_assignment,
    separator_width_constraint,
)
from .spacing import (
    InterFrameSpacing,
    corroborate_single_missing_overlap,
    observed_spacing_evidence,
    spacing_hypothesis,
)


@dataclass(frozen=True)
class SequenceSolveResult:
    photo_intervals: tuple[PhotoInterval, ...]
    frames: tuple[Box, ...]
    assignments: tuple[SeparatorAssignment, ...]
    boundaries: tuple[FrameBoundary, ...]
    relations: tuple[InterFrameSpacing, ...]
    holder_occlusion: HolderOcclusionEvidence
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    search_budget_exhausted: bool


@dataclass(frozen=True)
class _AssignmentState:
    rank: tuple[int, float, float, tuple[int, ...]]
    selections: tuple[tuple[int, int, SeparatorAssignment], ...]


@dataclass(frozen=True)
class _AssignmentSearchResult:
    states: tuple[_AssignmentState, ...]
    diagnostic: dict[int, SeparatorAssignment]
    budget_exhausted: bool


@dataclass(frozen=True)
class _SolvedAssignmentState:
    state: _AssignmentState
    boundaries: tuple[FrameBoundary, ...]
    focused_assignments: tuple[SeparatorAssignment, ...]
    frames: tuple[Box, ...]
    photo_intervals: tuple[PhotoInterval, ...]


def _assignment_rank(
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
        float(assignment.observation.tonal_evidence)
        for _boundary_index, _observation_index, assignment in selections
    )
    return (
        len(selections),
        -float(position_error),
        float(signal_support),
        tuple(-observation_index for _, observation_index, _ in selections),
    )


def _monotonic_assignment_solutions(
    observations: tuple[SeparatorBandObservation, ...],
    span: VisibleSequenceSpan,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionConstraint,
    maximum_assignment_evaluations: int,
) -> _AssignmentSearchResult:
    if maximum_assignment_evaluations <= 0:
        raise ValueError("sequence solver evaluation budget must be positive")
    diagnostic: dict[int, SeparatorAssignment] = {}
    for observation_index, observation in enumerate(observations):
        for boundary_index in range(1, count):
            assignment = assign_observation_to_boundary(
                boundary_index,
                observation,
                boundary_position_constraint(
                    span,
                    boundary_index,
                    count,
                    dimensions,
                    holder_occlusion,
                ),
                separator_width_constraint(
                    span,
                    boundary_index,
                    count,
                    dimensions,
                    holder_occlusion,
                ),
            )
            current = diagnostic.get(observation_index)
            if current is None or (
                int(assignment.state == EvidenceState.SUPPORTED),
                -abs(
                    observation.center
                    - assignment.position_constraint.position.midpoint
                ),
            ) > (
                int(current.state == EvidenceState.SUPPORTED),
                -abs(
                    current.observation.center
                    - current.position_constraint.position.midpoint
                ),
            ):
                diagnostic[observation_index] = assignment
    terminal: list[_AssignmentState] = []
    evaluations = 0
    exhausted = False

    def visit(
        boundary_index: int,
        next_observation_index: int,
        selections: tuple[tuple[int, int, SeparatorAssignment], ...],
    ) -> None:
        nonlocal evaluations, exhausted
        if boundary_index >= count:
            terminal.append(_AssignmentState(_assignment_rank(selections), selections))
            return
        visit(boundary_index + 1, next_observation_index, selections)
        if exhausted:
            return
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
        previous_boundary_index = selections[-1][0] if selections else 0
        previous_center = (
            selections[-1][2].observation.center
            if selections
            else float(span.box.left)
        )
        for observation_index in range(next_observation_index, len(observations)):
            if evaluations >= maximum_assignment_evaluations:
                exhausted = True
                return
            evaluations += 1
            observation = observations[observation_index]
            assignment = assign_observation_to_boundary(
                boundary_index,
                observation,
                position,
                width,
            )
            if not assignment.independent:
                continue
            minimum_separation = float(boundary_index - previous_boundary_index)
            if observation.center - previous_center < minimum_separation:
                continue
            if float(span.box.right) - observation.center < float(
                count - boundary_index
            ):
                continue
            visit(
                boundary_index + 1,
                observation_index + 1,
                (
                    *selections,
                    (boundary_index, observation_index, assignment),
                ),
            )
            if exhausted:
                return

    visit(1, 0, ())
    if not terminal:
        terminal.append(_AssignmentState(_assignment_rank(()), ()))
    return _AssignmentSearchResult(tuple(terminal), diagnostic, exhausted)


def _cuts(
    span: VisibleSequenceSpan,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionConstraint,
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
        cut_minimum = max(lower, position.position.minimum)
        cut_maximum = min(upper, position.position.maximum)
        if cut_maximum < cut_minimum:
            raise ValueError("physical sequence constraints do not intersect")
        cut_position = PixelInterval(cut_minimum, cut_maximum)
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
                root_measurement=MeasurementIdentity.FRAME_DIMENSIONS,
                source="monotonic_dimension_constraint",
                dependencies=(
                    dimensions.provenance.root_measurement,
                    MeasurementIdentity.SEQUENCE_BOUNDARIES,
                ),
            ),
            focused_assignment,
        )
        boundaries.append(boundary)
        previous = boundary.coordinate
    return tuple(boundaries), tuple(focused_assignments)


def _selected_assignments(
    state: _AssignmentState,
) -> dict[int, SeparatorAssignment]:
    return {
        boundary_index: replace(assignment, used_for_boundary=True)
        for boundary_index, _observation_index, assignment in state.selections
    }


def _solve_assignment_states(
    states: tuple[_AssignmentState, ...],
    span: VisibleSequenceSpan,
    count: int,
    dimensions: FrameDimensionPrior,
    holder_occlusion: HolderOcclusionConstraint,
    focused: dict[int, SeparatorBandObservation],
    boundary_observations: tuple[BoundaryObservation, ...],
) -> tuple[_SolvedAssignmentState, ...]:
    assignment_counts = sorted(
        {len(state.selections) for state in states},
        reverse=True,
    )
    for assignment_count in assignment_counts:
        solved: list[_SolvedAssignmentState] = []
        for state in states:
            if len(state.selections) != assignment_count:
                continue
            try:
                boundaries, focused_assignments = _cuts(
                    span,
                    count,
                    dimensions,
                    holder_occlusion,
                    _selected_assignments(state),
                    focused,
                )
                frames = _frames(span, boundaries, count)
                photo_intervals = _photo_intervals(
                    boundaries,
                    frames,
                    boundary_observations,
                )
            except ValueError:
                continue
            solved.append(
                _SolvedAssignmentState(
                    state,
                    boundaries,
                    focused_assignments,
                    frames,
                    photo_intervals,
                )
            )
        if solved:
            return tuple(solved)
    raise ValueError("physical sequence has no valid assignment solution")


def _assignment_consensus(
    solutions: tuple[_SolvedAssignmentState, ...],
    *,
    budget_exhausted: bool,
) -> BoundaryAssignmentConsensus:
    conflicting = tuple(
        boundary_index
        for boundary_index in range(1, len(solutions[0].boundaries) + 1)
        if max(
            solution.boundaries[boundary_index - 1].position.minimum
            for solution in solutions
        )
        > min(
            solution.boundaries[boundary_index - 1].position.maximum
            for solution in solutions
        )
    )
    return BoundaryAssignmentConsensus(
        (
            AssignmentConsensusOutcome.BUDGET_EXHAUSTED
            if budget_exhausted
            else AssignmentConsensusOutcome.DISAGREED
            if conflicting
            else AssignmentConsensusOutcome.AGREED
        ),
        len(solutions),
        conflicting,
    )


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
    rounded = [int(round(cuts[0]))]
    for index, coordinate in enumerate(cuts[1:-1], start=1):
        rounded.append(
            max(
                rounded[-1] + 1,
                min(
                    int(round(coordinate)),
                    int(round(cuts[-1])) - (count - index),
                ),
            )
        )
    rounded.append(int(round(cuts[-1])))
    if any(right <= left for left, right in zip(rounded[:-1], rounded[1:])):
        raise ValueError("sequence solution has no positive-width pixel frames")
    return tuple(
        Box(
            left,
            span.box.top,
            right,
            span.box.bottom,
        )
        for left, right in zip(rounded[:-1], rounded[1:])
    )


def _photo_intervals(
    boundaries: tuple[FrameBoundary, ...],
    frames: tuple[Box, ...],
    boundary_observations: tuple[BoundaryObservation, ...],
) -> tuple[PhotoInterval, ...]:
    by_index = {boundary.boundary_index: boundary for boundary in boundaries}
    sequence_edges = {
        observation.side: observation
        for observation in boundary_observations
        if observation.side in {BoundarySide.LEADING, BoundarySide.TRAILING}
    }
    generated_provenance = MeasurementProvenance(
        root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
        source="sequence_photo_interval",
        dependencies=(MeasurementIdentity.SEQUENCE_CUTS,),
    )
    intervals: list[PhotoInterval] = []
    for index, frame in enumerate(frames, start=1):
        previous = by_index.get(index - 1)
        following = by_index.get(index)
        leading = sequence_edges.get("leading") if index == 1 else None
        trailing = sequence_edges.get("trailing") if index == len(frames) else None
        if previous is not None and previous.hard_separator:
            assert previous.assignment is not None
            start = PixelInterval.exact(previous.assignment.observation.end)
            start_provenance = previous.assignment.observation.provenance
            start_observed = True
        elif previous is not None:
            start = previous.position
            start_provenance = previous.provenance
            start_observed = False
        elif leading is not None:
            start = leading.position
            start_provenance = leading.provenance
            start_observed = leading.kind != BoundaryKind.CANVAS_CLIP
        else:
            start = PixelInterval.exact(float(frame.left))
            start_provenance = generated_provenance
            start_observed = False
        if following is not None and following.hard_separator:
            assert following.assignment is not None
            end = PixelInterval.exact(following.assignment.observation.start)
            end_provenance = following.assignment.observation.provenance
            end_observed = True
        elif following is not None:
            end = following.position
            end_provenance = following.provenance
            end_observed = False
        elif trailing is not None:
            end = trailing.position
            end_provenance = trailing.provenance
            end_observed = trailing.kind != BoundaryKind.CANVAS_CLIP
        else:
            end = PixelInterval.exact(float(frame.right))
            end_provenance = generated_provenance
            end_observed = False
        intervals.append(
            PhotoInterval(
                index,
                start,
                end,
                start_provenance,
                end_provenance,
                start_observed,
                end_observed,
            )
        )
    return tuple(intervals)


def _relations(
    boundaries: tuple[FrameBoundary, ...],
    dimensions: FrameDimensionPrior,
    span: VisibleSequenceSpan,
    holder_occlusion: HolderOcclusionEvidence,
    boundary_observations: tuple[BoundaryObservation, ...],
) -> tuple[InterFrameSpacing, ...]:
    relations: list[InterFrameSpacing] = []
    for boundary in boundaries:
        assignment = boundary.assignment
        if assignment is not None and assignment.independent:
            relations.append(
                observed_spacing_evidence(
                    FrameBoundaryReference(None, boundary.boundary_index),
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
                FrameBoundaryReference(None, boundary.boundary_index),
                PixelInterval(
                    -float(dimensions.width_px.maximum),
                    float(width_constraint.maximum),
                ),
                MeasurementProvenance(
                    root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
                    source="unobserved_inter_frame_relation",
                    dependencies=tuple(
                        dict.fromkeys(
                            (
                                boundary.provenance.root_measurement,
                                dimensions.provenance.root_measurement,
                            )
                        )
                    ),
                ),
            )
        )
    return corroborate_single_missing_overlap(
        visible_length_px=visible_sequence_length_interval(
            span,
            boundary_observations,
        ),
        count=len(boundaries) + 1,
        frame_width_px=dimensions.width_px,
        spacings=tuple(relations),
        holder_occlusion=holder_occlusion,
        boundary_observations=boundary_observations,
        dimension_source=dimensions.source,
    )


def _residuals(
    span: VisibleSequenceSpan,
    photo_intervals: tuple[PhotoInterval, ...],
    boundaries: tuple[FrameBoundary, ...],
    dimensions: FrameDimensionPrior,
) -> SequenceResiduals:
    observed_widths = tuple(
        photo.width_px.midpoint
        for photo in photo_intervals
        if photo.independently_observed
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
    boundary_observations: tuple[BoundaryObservation, ...],
    maximum_assignment_evaluations: int,
) -> SequenceSolveResult:
    if count <= 0:
        raise ValueError("sequence count must be positive")
    occlusion_constraint = holder_occlusion_constraint(
        boundary_observations,
        dimensions.width_px,
    )
    if count == 1:
        frames = (span.box,)
        intervals = _photo_intervals((), frames, boundary_observations)
        holder_occlusion = holder_occlusion_for_sequence(
            boundary_observations,
            span,
            (),
            dimensions.width_px,
        )
        return SequenceSolveResult(
            intervals,
            frames,
            (),
            (),
            (),
            holder_occlusion,
            _residuals(span, intervals, (), dimensions),
            BoundaryAssignmentConsensus(
                AssignmentConsensusOutcome.AGREED,
                1,
                (),
            ),
            False,
        )
    search = _monotonic_assignment_solutions(
        observations,
        span,
        count,
        dimensions,
        occlusion_constraint,
        maximum_assignment_evaluations,
    )
    solved_states = _solve_assignment_states(
        search.states,
        span,
        count,
        dimensions,
        occlusion_constraint,
        dict(focused_observations),
        boundary_observations,
    )
    representative = max(solved_states, key=lambda item: item.state.rank)
    selected = _selected_assignments(representative.state)
    boundaries = representative.boundaries
    focused_assignments = representative.focused_assignments
    selected_observations = {
        id(assignment.observation): assignment for assignment in selected.values()
    }
    assignments = tuple(
        selected_observations.get(id(observation), search.diagnostic[id_index])
        for id_index, observation in enumerate(observations)
    ) + focused_assignments
    frames = representative.frames
    intervals = representative.photo_intervals
    holder_occlusion = holder_occlusion_for_sequence(
        boundary_observations,
        span,
        boundaries,
        dimensions.width_px,
    )
    relations = _relations(
        boundaries,
        dimensions,
        span,
        holder_occlusion,
        boundary_observations,
    )
    return SequenceSolveResult(
        photo_intervals=intervals,
        frames=frames,
        assignments=assignments,
        boundaries=boundaries,
        relations=relations,
        holder_occlusion=holder_occlusion,
        residuals=_residuals(span, intervals, boundaries, dimensions),
        assignment_consensus=_assignment_consensus(
            solved_states,
            budget_exhausted=search.budget_exhausted,
        ),
        search_budget_exhausted=search.budget_exhausted,
    )
