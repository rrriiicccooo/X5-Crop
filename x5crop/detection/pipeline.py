from __future__ import annotations

from dataclasses import replace

from .candidate.assessment.candidate import assess_candidate
from .candidate.assessment.review_only import assess_review_only_candidate
from .candidate.execution.count_hypothesis import evaluate_count_hypothesis
from .candidate.execution.model import CountHypothesisEvaluation
from .candidate.model import AssessedCandidate
from .candidate.proposal.sequence import photo_sequence_search_scope
from .candidate.plan.counts import count_hypothesis_plan
from .candidate.plan.model import (
    CountHypothesisPlan,
    CountHypothesisSource,
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
from .modes.review_only import unresolved_dual_lane_candidate
from .evidence.content.regions import cached_content_region_observation
from .physical.model import ReviewOnlyContainment
from ..domain import (
    EvidenceState,
    PhotoSequenceSearchScope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    combined_physical_search_outcome,
)
from ..image.content import ContentRegionObservation


def _candidate_pool_for_count_resolution(
    evaluations: tuple[CountHypothesisEvaluation, ...],
) -> tuple[tuple[AssessedCandidate, ...], PhysicalSearchOutcome]:
    resolved = next(
        (evaluation for evaluation in evaluations if evaluation.geometry_resolved),
        None,
    )
    if resolved is not None:
        return resolved.candidates, resolved.physical_search
    return (
        tuple(
            candidate
            for evaluation in evaluations
            for candidate in evaluation.candidates
        ),
        combined_physical_search_outcome(
            tuple(evaluation.physical_search for evaluation in evaluations)
        ),
    )


def _evaluate_count_hypotheses(
    context: DetectionContext,
    plan: CountHypothesisPlan,
    search_scope: PhotoSequenceSearchScope,
    visible_content: ContentRegionObservation,
) -> tuple[tuple[CountHypothesisEvaluation, ...], int | None]:
    evaluations: list[CountHypothesisEvaluation] = []
    stopped_after_count: int | None = None
    larger_count_hypotheses_resolved = True
    for hypothesis in plan.hypotheses:
        evaluation = evaluate_count_hypothesis(
            context,
            hypothesis,
            search_scope=search_scope,
            visible_content=visible_content,
            larger_count_hypotheses_resolved=(
                larger_count_hypotheses_resolved
            ),
        )
        evaluations.append(evaluation)
        if (
            plan.automatic
            and larger_count_hypotheses_resolved
            and evaluation.geometry_resolved
        ):
            stopped_after_count = hypothesis.count
            break
        if evaluation.hypothesis_state != EvidenceState.CONTRADICTED:
            larger_count_hypotheses_resolved = False
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
    search_scope = photo_sequence_search_scope(
        context.measurement_cache,
        configuration.boundary_path,
    )
    visible_content = cached_content_region_observation(
        context.measurement_cache,
        search_scope.holder_span.box,
        configuration.content,
    )
    plan = count_hypothesis_plan(
        strip_mode=context.request.strip_mode,
        requested_count=context.request.requested_count,
        fmt=physical_spec,
    )
    evaluations, stopped_after_count = _evaluate_count_hypotheses(
        context,
        plan,
        search_scope,
        visible_content,
    )

    candidates, physical_search = _candidate_pool_for_count_resolution(
        evaluations
    )
    if not candidates:
        built = hard_safety_candidate(
            context,
            plan.hard_safety_count,
            search_scope,
            physical_search=physical_search,
        )
        assessed = (
            assess_review_only_candidate(built)
            if isinstance(built.geometry, ReviewOnlyContainment)
            else assess_candidate(built, context)
        )
        context.execution_statistics.record_assessed_candidate()
        candidates = (assessed,)
    selection = select_candidates(
        candidates,
        larger_count_hypotheses_resolved=bool(
            not plan.automatic or stopped_after_count is not None
        ),
        physical_search=physical_search,
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
        assessed = assess_review_only_candidate(
            unresolved_dual_lane_candidate(
                context,
                "dual_lane_partial_not_supported",
            )
        )
        selection = select_candidates(
            (assessed,),
            larger_count_hypotheses_resolved=True,
            physical_search=PhysicalSearchOutcome(
                (PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,),
            ),
        )
        context.execution_statistics.record_assessed_candidate()
    else:
        selection = _choose_standard_detection(context)
    return selection
