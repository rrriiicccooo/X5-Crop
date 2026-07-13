from __future__ import annotations

from ...context import DetectionContext
from ..assessment.candidate import assess_candidate
from ..build.sequence_candidate import build_sequence_candidate
from ..model import AssessedCandidate
from ..plan.count_hypotheses import CountHypothesis
from ..selection.choose import select_candidates
from ...physical.photo_size import frame_dimension_priors
from .source_candidates import (
    FrameSequencePlan,
    frame_sequence_plan,
)
from .model import CountHypothesisEvaluation


def _assess_sequence_plan(
    context: DetectionContext,
    plan: FrameSequencePlan,
) -> list[AssessedCandidate]:
    assessed: list[AssessedCandidate] = []
    for sequence_hypothesis in plan.hypotheses:
        for dimensions in frame_dimension_priors(
            sequence_hypothesis.visible_sequence_span,
            context.configuration.physical_spec,
            context.scan_calibration,
            layout=context.request.layout,
        ):
            outcome = build_sequence_candidate(
                context.request,
                context.configuration.physical_spec,
                plan.count_hypothesis,
                sequence_hypothesis,
                dimensions,
                cache=context.measurement_cache,
                separator_configuration=context.configuration.separator,
                solver_parameters=context.configuration.candidate_plan.sequence_solver,
                planning_budget_exhausted=plan.search_budget_exhausted,
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
    sequence_plan = frame_sequence_plan(
        context.request,
        context.configuration.physical_spec,
        hypothesis,
        cache=context.measurement_cache,
        boundary_parameters=context.configuration.boundary_path,
        content_configuration=context.configuration.content,
        separator_configuration=context.configuration.separator,
        hypothesis_parameters=context.configuration.candidate_plan.sequence_hypotheses,
        scan_calibration=context.scan_calibration,
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
