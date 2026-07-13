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
) -> list[AssessedCandidate]:
    assessed: list[AssessedCandidate] = []
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
        if outcome.candidate is not None:
            assessed.append(assess_candidate(outcome.candidate, context))
            context.execution_statistics.record_assessed_candidate()
    return assessed


def evaluate_count_hypothesis(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    *,
    larger_counts_evaluated: bool,
) -> CountHypothesisEvaluation:
    sequence_plan = photo_sequence_plan(
        context.request,
        hypothesis,
        cache=context.measurement_cache,
        boundary_parameters=context.configuration.boundary_path,
    )
    candidates = _assess_sequence_plan(context, sequence_plan)
    selection = (
        select_candidates(
            tuple(candidates),
            larger_counts_evaluated=larger_counts_evaluated,
        )
        if candidates
        else None
    )
    return CountHypothesisEvaluation(
        hypothesis=hypothesis,
        candidates=tuple(candidates),
        selection=selection,
    )
