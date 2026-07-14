from __future__ import annotations

from ....domain import (
    PhotoSequenceSearchScope,
    PhysicalSearchOutcome,
    combined_physical_search_outcome,
)
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
) -> tuple[list[AssessedCandidate], PhysicalSearchOutcome]:
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
    search_scope: PhotoSequenceSearchScope,
    visible_content: ContentRegionObservation,
    larger_count_hypotheses_resolved: bool,
) -> CountHypothesisEvaluation:
    candidates, physical_search = _assess_count_hypothesis(
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
