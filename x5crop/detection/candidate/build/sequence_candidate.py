from __future__ import annotations

from dataclasses import dataclass

from ....configuration.candidate import SequenceSolverParameters
from ....domain import (
    EvidenceState,
    FrameDimensionPrior,
    FrameSequenceSearchScope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    combined_physical_search_outcome,
)
from ....formats import FormatSpec
from ....image.content import ContentRegionObservation
from ...context import DetectionRequest
from ...physical.model import FrameSequenceSolution
from ...physical.frame_sequence_solver import (
    solve_frame_sequence,
)
from ...physical.frame_sequence_result import FrameSequenceSolveFailure
from ...physical.short_axis import SharedShortAxisPlan
from ..model import BuiltCandidate
from ..plan.model import CountHypothesis
from ..proposal.sequence import FrameSequenceObservations


@dataclass(frozen=True)
class SequenceCandidateBuildOutcome:
    candidate: BuiltCandidate | None
    physical_search: PhysicalSearchOutcome
    assignment_evaluations: int

    def __post_init__(self) -> None:
        if self.assignment_evaluations < 0:
            raise ValueError("candidate build evaluation count cannot be negative")
        if (
            self.physical_search.state == EvidenceState.CONTRADICTED
            and self.candidate is not None
        ) or (
            self.physical_search.state == EvidenceState.SUPPORTED
            and self.candidate is None
        ):
            raise ValueError(
                "candidate availability must match its physical search outcome"
            )


def build_sequence_candidate(
    request: DetectionRequest,
    fmt: FormatSpec,
    count_hypothesis: CountHypothesis,
    search_scope: FrameSequenceSearchScope,
    short_axis_plan: SharedShortAxisPlan,
    sequence_observations: FrameSequenceObservations,
    dimensions: FrameDimensionPrior,
    visible_content: ContentRegionObservation,
    *,
    solver_parameters: SequenceSolverParameters,
) -> SequenceCandidateBuildOutcome:
    if not short_axis_plan.span.supports_safe_crop:
        return SequenceCandidateBuildOutcome(
            None,
            short_axis_plan.search_outcome,
            0,
        )
    support_set = sequence_observations.search_index.separator_supports
    solved = solve_frame_sequence(
        sequence_observations.search_index,
        search_scope,
        short_axis_plan,
        int(count_hypothesis.count),
        dimensions,
        visible_content,
        solver_parameters.maximum_assignment_evaluations,
        strip_mode=count_hypothesis.strip_mode,
        nominal_count=fmt.strip.default_count,
    )
    if isinstance(solved, FrameSequenceSolveFailure):
        return SequenceCandidateBuildOutcome(
            None,
            solved.search_outcome,
            solved.assignment_evaluations,
        )
    physical_search = solved.search_outcome
    if support_set.budget_exhausted:
        physical_search = combined_physical_search_outcome(
            (
                physical_search,
                PhysicalSearchOutcome(
                    (PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,),
                ),
            )
        )
    geometry = FrameSequenceSolution(
        format_id=fmt.format_id,
        layout=request.layout,
        strip_mode=count_hypothesis.strip_mode,
        count=int(count_hypothesis.count),
        nominal_count=fmt.strip.default_count,
        holder_safety=search_scope.holder_safety,
        shared_short_axis=solved.shared_short_axis,
        photo_height_evidence=solved.photo_height_evidence,
        frame_width_search_hint=solved.frame_width_search_hint,
        holder_span_scale_hint=solved.holder_span_scale_hint,
        content_extent_constraint=solved.content_extent_constraint,
        indexed_anchor_distance_constraints=(
            solved.indexed_anchor_distance_constraints
        ),
        frame_slots=solved.frame_slots,
        long_axis_assignments=solved.long_axis_assignments,
        separator_observations=tuple(
            sequence_observations.separator_observations.observations
        ),
        separator_assignments=solved.separator_assignments,
        inter_frame_spacings=solved.inter_frame_spacings,
        frame_dimension_prior=dimensions,
        common_frame_width=solved.common_frame_width,
        residuals=solved.residuals,
        assignment_consensus=solved.assignment_consensus,
        raw_boundary_paths=search_scope.raw_boundary_paths,
    )
    return SequenceCandidateBuildOutcome(
        BuiltCandidate(
            geometry=geometry,
            count_hypothesis=count_hypothesis,
            build_diagnostics=(),
        ),
        physical_search,
        solved.assignment_evaluations,
    )
