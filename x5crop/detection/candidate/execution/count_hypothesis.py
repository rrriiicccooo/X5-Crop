from __future__ import annotations

from ...context import DetectionContext
from ..assessment.candidate import assess_candidate
from ..build.sequence_candidate import build_sequence_candidate
from ..model import AssessedCandidate
from ..plan.count_hypotheses import CountHypothesis
from ..selection.choose import select_candidates
from ...physical.photo_size import frame_dimension_priors
from .source_candidates import (
    PhotoSequencePlan,
    photo_sequence_plan,
)
from .model import CountHypothesisEvaluation


def _assess_sequence_plan(
    context: DetectionContext,
    plan: PhotoSequencePlan,
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
            plan.count_hypothesis,
            plan.search_scope,
            dimensions,
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
    larger_count_hypotheses_resolved: bool,
) -> CountHypothesisEvaluation:
    sequence_plan = photo_sequence_plan(
        context.request,
        hypothesis,
        cache=context.measurement_cache,
        boundary_parameters=context.configuration.boundary_path,
    )
    candidates, search_budget_exhausted = _assess_sequence_plan(
        context,
        sequence_plan,
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
