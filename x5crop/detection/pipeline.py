from __future__ import annotations

from dataclasses import replace

from .candidate.assessment.candidate import assess_candidate
from .candidate.assessment.review_only import assess_review_only_candidate
from .candidate.execution.count_hypothesis import evaluate_count_hypothesis
from .candidate.execution.model import CountHypothesisEvaluation
from .candidate.model import AssessedCandidate
from .candidate.plan.count_hypotheses import (
    CountHypothesisPlan,
    CountHypothesisSource,
    count_hypothesis_plan,
)
from .candidate.proposal.hard_safety import hard_safety_candidate
from .candidate.selection.choose import select_candidates
from .candidate.selection.model import (
    CountResolution,
    CountResolutionOutcome,
    SelectionResult,
)
from .context import DetectionContext
from .modes.dual_lane import choose_dual_lane_detection
from .modes.review_only import review_only_candidate


def _candidate_pool_for_count_resolution(
    evaluations: tuple[CountHypothesisEvaluation, ...],
) -> tuple[AssessedCandidate, ...]:
    resolved = next(
        (evaluation for evaluation in evaluations if evaluation.geometry_resolved),
        None,
    )
    if resolved is not None:
        return resolved.candidates
    return tuple(
        candidate
        for evaluation in evaluations
        for candidate in evaluation.candidates
    )


def _evaluate_count_hypotheses(
    context: DetectionContext,
    plan: CountHypothesisPlan,
) -> tuple[tuple[CountHypothesisEvaluation, ...], int | None]:
    evaluations: list[CountHypothesisEvaluation] = []
    stopped_after_count: int | None = None
    for hypothesis in plan.hypotheses:
        evaluation = evaluate_count_hypothesis(
            context,
            hypothesis,
            larger_counts_evaluated=True,
        )
        evaluations.append(evaluation)
        if plan.automatic and evaluation.geometry_resolved:
            stopped_after_count = hypothesis.count
            break
    return tuple(evaluations), stopped_after_count


def _count_resolution(
    selection: SelectionResult,
    search_order: tuple[int, ...],
    evaluations: tuple[CountHypothesisEvaluation, ...],
    stopped_after_count: int | None,
    requested_count: int | None,
) -> CountResolution:
    if requested_count is not None:
        outcome = CountResolutionOutcome.REQUESTED_COUNT
    elif (
        selection.selected.count_hypothesis.source
        == CountHypothesisSource.FORMAT_DEFAULT
    ):
        outcome = CountResolutionOutcome.FORMAT_DEFAULT_COUNT
    elif selection.geometry_resolution.supported:
        outcome = CountResolutionOutcome.LARGEST_PHYSICALLY_RESOLVED_COUNT
    else:
        outcome = (
            CountResolutionOutcome.BEST_COVERAGE_WITHOUT_PHYSICAL_RESOLUTION
        )
    return CountResolution(
        selected_count=selection.selected.geometry.count,
        search_order=search_order,
        evaluated_counts=tuple(
            evaluation.hypothesis.count for evaluation in evaluations
        ),
        stopped_after_count=stopped_after_count,
        outcome=outcome,
    )


def _choose_standard_detection(context: DetectionContext) -> SelectionResult:
    configuration = context.configuration
    physical_spec = configuration.physical_spec
    plan = count_hypothesis_plan(
        strip_mode=context.request.strip_mode,
        requested_count=context.request.requested_count,
        fmt=physical_spec,
    )
    evaluations, stopped_after_count = _evaluate_count_hypotheses(context, plan)

    candidates = _candidate_pool_for_count_resolution(evaluations)
    if not candidates:
        built = hard_safety_candidate(context, plan.hard_safety_count)
        candidates = (assess_candidate(built, context),)
    selection = select_candidates(
        candidates,
        larger_counts_evaluated=True,
    )
    count_resolution = _count_resolution(
        selection,
        tuple(hypothesis.count for hypothesis in plan.hypotheses),
        evaluations,
        stopped_after_count,
        plan.requested_count,
    )
    return replace(selection, count_resolution=count_resolution)


def choose_detection(context: DetectionContext) -> SelectionResult:
    configuration = context.configuration
    if context.measurement_cache.layout != context.request.layout:
        raise ValueError("analysis cache layout does not match detection context")
    if configuration.detector_kind == "dual_lane":
        selection = choose_dual_lane_detection(
            context,
            _choose_standard_detection,
        )
    elif configuration.detector_kind == "review_only":
        assessed = assess_review_only_candidate(review_only_candidate(context))
        selection = select_candidates(
            (assessed,),
            larger_counts_evaluated=True,
        )
    else:
        selection = _choose_standard_detection(context)
    return selection
