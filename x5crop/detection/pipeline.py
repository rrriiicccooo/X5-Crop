from __future__ import annotations

from dataclasses import replace

from .candidate.assessment.candidate import assess_candidate
from .candidate.execution.count_hypothesis import evaluate_count_hypothesis
from .candidate.execution.model import CountHypothesisEvaluation
from .candidate.execution.count_placement import resolve_automatic_count_placement
from .candidate.extension.outer_correction import (
    outer_correction_candidate_extensions,
)
from .candidate.plan.count_hypotheses import count_hypothesis_plan
from .candidate.proposal.hard_safety import hard_safety_candidate
from .candidate.selection.choose import select_candidates
from .candidate.selection.model import CountResolution, SelectionResult
from .context import DetectionContext
from .evidence.count_planning import CountPlanningEvidence, count_planning_evidence
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
    policy = context.policy
    physical_spec = policy.physical_spec
    planning_evidence = (
        count_planning_evidence(
            context.measurement_cache.gray_work,
            physical_spec,
            context.measurement_cache,
            outer_parameters=policy.outer.proposal.base,
            separator_profile_parameters=policy.separator.profile,
            gap_search_parameters=policy.separator.gap_search,
            separator_band_parameters=(
                policy.outer.proposal.geometry.separator.band
            ),
            calibration=context.scan_calibration,
            long_axis=(
                "x" if context.request.layout == "horizontal" else "y"
            ),
        )
        if (
            context.request.strip_mode == "partial"
            and context.request.requested_count is None
        )
        else CountPlanningEvidence.unavailable()
    )
    plan = count_hypothesis_plan(
        strip_mode=context.request.strip_mode,
        requested_count=context.request.requested_count,
        fmt=physical_spec,
        partial_offsets=policy.partial_count_offsets,
        planning_evidence=planning_evidence,
    )
    evaluations: list[CountHypothesisEvaluation] = []
    candidates = []
    stopped_after_count: int | None = None
    for hypothesis in plan.hypotheses:
        plan, resolved_hypothesis = resolve_automatic_count_placement(
            plan,
            hypothesis,
            context.measurement_cache,
            physical_spec,
            policy.content,
            policy.separator.width_profile_search,
            context.scan_calibration,
            "x" if context.request.layout == "horizontal" else "y",
        )
        evaluation = evaluate_count_hypothesis(
            context,
            resolved_hypothesis,
            larger_counts_evaluated=True,
        )
        evaluations.append(evaluation)
        candidates.extend(evaluation.candidates)
        if plan.automatic and evaluation.geometry_resolved:
            stopped_after_count = resolved_hypothesis.count
            break

    if not candidates:
        built = hard_safety_candidate(context, plan.hard_safety_count)
        candidates.append(assess_candidate(built, context))
    selection = select_candidates(
        tuple(candidates),
        policy.candidate_selection,
        larger_counts_evaluated=True,
    )
    extensions = outer_correction_candidate_extensions(selection, context)
    if extensions:
        candidates.extend(extensions)
        selection = select_candidates(
            tuple(candidates),
            policy.candidate_selection,
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
    policy = context.policy
    if context.measurement_cache.layout != context.request.layout:
        raise ValueError("analysis cache layout does not match detection context")
    if policy.detector_kind == "dual_lane":
        selection = choose_dual_lane_detection(
            context,
            _choose_standard_detection,
        )
    elif policy.detector_kind == "review_only":
        assessed = assess_candidate(review_only_candidate(context), context)
        selection = select_candidates(
            (assessed,),
            policy.candidate_selection,
            larger_counts_evaluated=True,
        )
    else:
        selection = _choose_standard_detection(context)
    return selection
