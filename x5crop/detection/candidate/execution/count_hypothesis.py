from __future__ import annotations

from ....domain import PhotoSequenceSearchScope
from ....image.content import ContentRegionObservation
from ...context import DetectionContext
from ..assessment.candidate import assess_candidate
from ..build.sequence_candidate import build_sequence_candidate
from ..model import AssessedCandidate
from ..plan.model import CountHypothesis
from ..selection.choose import select_candidates
from ...physical.photo_size import frame_dimension_priors
from .model import CountHypothesisEvaluation


def _assess_count_hypothesis(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    search_scope: PhotoSequenceSearchScope,
    visible_content: ContentRegionObservation,
) -> tuple[list[AssessedCandidate], bool]:
    outcomes = []
    for dimensions in frame_dimension_priors(
        context.configuration.physical_spec,
        context.scan_calibration,
        layout=context.request.layout,
    ):
        outcome = build_sequence_candidate(
            context.request,
            context.configuration.physical_spec,
            hypothesis,
            search_scope,
            dimensions,
            visible_content,
            cache=context.measurement_cache,
            separator_configuration=context.configuration.separator,
            solver_parameters=context.configuration.candidate_plan.sequence_solver,
        )
        context.execution_statistics.record_assignment_evaluations(
            outcome.assignment_evaluations
        )
        outcomes.append(outcome)
    search_budget_exhausted = any(
        outcome.search_budget_exhausted for outcome in outcomes
    )
    assessed: list[AssessedCandidate] = []
    for outcome in outcomes:
        if outcome.candidate is not None:
            assessed.append(assess_candidate(outcome.candidate, context))
            context.execution_statistics.record_assessed_candidate()
    return assessed, search_budget_exhausted


def evaluate_count_hypothesis(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    *,
    search_scope: PhotoSequenceSearchScope,
    visible_content: ContentRegionObservation,
    larger_count_hypotheses_resolved: bool,
) -> CountHypothesisEvaluation:
    candidates, search_budget_exhausted = _assess_count_hypothesis(
        context,
        hypothesis,
        search_scope,
        visible_content,
    )
    selection = (
        select_candidates(
            tuple(candidates),
            larger_count_hypotheses_resolved=(
                larger_count_hypotheses_resolved
            ),
            candidate_search_budget_exhausted=search_budget_exhausted,
        )
        if candidates
        else None
    )
    return CountHypothesisEvaluation(
        hypothesis=hypothesis,
        candidates=tuple(candidates),
        selection=selection,
        search_budget_exhausted=search_budget_exhausted,
    )
