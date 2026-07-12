from __future__ import annotations

from dataclasses import replace

from .candidate.assessment.candidate import assess_candidate
from .candidate.execution.count_hypothesis import evaluate_count_hypothesis
from .candidate.execution.model import CountHypothesisEvaluation
from .candidate.plan.count_hypotheses import count_hypothesis_plan
from .candidate.proposal.hard_safety import hard_safety_candidate
from .candidate.selection.choose import select_candidates
from .candidate.selection.model import CountResolution, SelectionResult
from .context import DetectionContext
from .modes.dual_lane import choose_dual_lane_detection
from .modes.review_only import review_only_candidate

def _count_resolution(
    selection: SelectionResult,
    search_order: tuple[int, ...],
    evaluations: tuple[CountHypothesisEvaluation, ...],
    stopped_after_count: int | None,
    requested_count: int | None,
) -> CountResolution:
    if requested_count is not None:
        reason = "requested_count"
    elif selection.geometry_resolution.supported:
        reason = "largest_physically_resolved_count"
    else:
        reason = "best_coverage_without_physical_resolution"
    return CountResolution(
        selected_count=selection.selected.geometry.count,
        search_order=search_order,
        evaluated_counts=tuple(
            evaluation.hypothesis.count for evaluation in evaluations
        ),
        stopped_after_count=stopped_after_count,
        reason=reason,
    )


def _choose_standard_detection(context: DetectionContext) -> SelectionResult:
    configuration = context.configuration
    physical_spec = configuration.physical_spec
    plan = count_hypothesis_plan(
        strip_mode=context.request.strip_mode,
        requested_count=context.request.requested_count,
        fmt=physical_spec,
    )
    evaluations: list[CountHypothesisEvaluation] = []
    candidates = []
    stopped_after_count: int | None = None
    for hypothesis in plan.hypotheses:
        evaluation = evaluate_count_hypothesis(
            context,
            hypothesis,
            larger_counts_evaluated=True,
        )
        evaluations.append(evaluation)
        candidates.extend(evaluation.candidates)
        if plan.automatic and evaluation.geometry_resolved:
            stopped_after_count = hypothesis.count
            break

    if not candidates:
        built = hard_safety_candidate(context, plan.hard_safety_count)
        candidates.append(assess_candidate(built, context))
    selection = select_candidates(
        tuple(candidates),
        larger_counts_evaluated=True,
    )
    count_resolution = _count_resolution(
        selection,
        tuple(hypothesis.count for hypothesis in plan.hypotheses),
        tuple(evaluations),
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
        assessed = assess_candidate(review_only_candidate(context), context)
        selection = select_candidates(
            (assessed,),
            larger_counts_evaluated=True,
        )
    else:
        selection = _choose_standard_detection(context)
    return selection
