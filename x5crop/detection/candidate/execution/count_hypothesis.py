from __future__ import annotations

from ....domain import (
    FrameSequenceSearchScope,
    PhysicalSearchOutcome,
    combined_physical_search_outcome,
)
from ....image.content import ContentRegionObservation
from ...context import DetectionContext
from ..assessment.candidate import assess_candidate
from ..build.sequence_candidate import build_sequence_candidate
from ..model import AssessedCandidate
from ..plan.model import CountHypothesis
from ..proposal.sequence import FrameSequenceObservations
from ..selection.choose import select_candidates
from ...physical.frame_dimensions import frame_dimension_priors
from ...physical.short_axis import SharedShortAxisPlan
from .model import CountHypothesisEvaluation


def _assess_count_hypothesis(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    search_scope: FrameSequenceSearchScope,
    short_axis_plan: SharedShortAxisPlan,
    sequence_observations: FrameSequenceObservations,
    visible_content: ContentRegionObservation,
) -> tuple[list[AssessedCandidate], PhysicalSearchOutcome]:
    outcomes = []
    for dimensions in frame_dimension_priors(
        context.configuration.physical_spec,
    ):
        outcome = build_sequence_candidate(
            context.request,
            context.configuration.physical_spec,
            hypothesis,
            search_scope,
            short_axis_plan,
            sequence_observations,
            dimensions,
            visible_content,
            solver_parameters=context.configuration.candidate_plan.sequence_solver,
        )
        context.execution_statistics.record_assignment_evaluations(
            outcome.assignment_evaluations
        )
        outcomes.append(outcome)
    physical_search = combined_physical_search_outcome(
        tuple(outcome.physical_search for outcome in outcomes)
    )
    assessed: list[AssessedCandidate] = []
    for outcome in outcomes:
        if outcome.candidate is not None:
            assessed.append(assess_candidate(outcome.candidate, context))
            context.execution_statistics.record_assessed_candidate()
    return assessed, physical_search


def evaluate_count_hypothesis(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    *,
    search_scope: FrameSequenceSearchScope,
    short_axis_plan: SharedShortAxisPlan,
    sequence_observations: FrameSequenceObservations,
    visible_content: ContentRegionObservation,
    larger_count_search_complete: bool,
) -> CountHypothesisEvaluation:
    candidates, physical_search = _assess_count_hypothesis(
        context,
        hypothesis,
        search_scope,
        short_axis_plan,
        sequence_observations,
        visible_content,
    )
    selection = (
        select_candidates(
            tuple(candidates),
            larger_count_search_complete=(
                larger_count_search_complete
            ),
            physical_search=physical_search,
        )
        if candidates
        else None
    )
    return CountHypothesisEvaluation(
        hypothesis=hypothesis,
        candidates=tuple(candidates),
        selection=selection,
        physical_search=physical_search,
    )
