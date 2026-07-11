from __future__ import annotations

from ...context import DetectionContext
from ...guidance.content_separator import content_separator_guidance_for_count
from ..assessment.candidate import assess_candidate
from ..model import AssessedCandidate
from ..plan.count_hypotheses import CountHypothesis
from ..selection.choose import select_candidates
from .source_candidates import (
    SeparatorSequencePlan,
    build_separator_candidate_for_proposal,
    build_separator_candidate_with_guidance,
    separator_extension_sequence_plan,
    separator_primary_sequence_plan,
)
from .model import CountHypothesisEvaluation, OffsetEvaluation


def _assess_sequence_plan(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    offset: float,
    plan: SeparatorSequencePlan,
) -> list[AssessedCandidate]:
    assessed: list[AssessedCandidate] = []
    for sequence_hypothesis in plan.proposals:
        built = build_separator_candidate_for_proposal(
            context.request,
            context.policy.physical_spec,
            hypothesis.count,
            hypothesis.strip_mode,
            offset,
            cache=context.measurement_cache,
            outer_policy=context.policy.outer,
            separator_policy=context.policy.separator,
            scan_calibration=context.scan_calibration,
            proposal=sequence_hypothesis,
            plan=plan,
            gap_max_width_ratio_override=None,
        )
        assessed.append(assess_candidate(built, context))
    return assessed


def _candidates_for_offset(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    offset: float,
    *,
    larger_counts_evaluated: bool = True,
) -> OffsetEvaluation:
    candidates: list[AssessedCandidate] = []
    physical_spec = context.policy.physical_spec
    primary_plan = separator_primary_sequence_plan(
        context.request,
        physical_spec,
        hypothesis.count,
        hypothesis.strip_mode,
        hypothesis,
        cache=context.measurement_cache,
        outer_policy=context.policy.outer,
        separator_policy=context.policy.separator,
        scan_calibration=context.scan_calibration,
    )
    candidates.extend(
        _assess_sequence_plan(context, hypothesis, offset, primary_plan)
    )
    primary_selection = (
        None
        if not candidates
        else select_candidates(
            tuple(candidates),
            context.policy.candidate_selection,
            larger_counts_evaluated=larger_counts_evaluated,
        )
    )
    if (
        primary_selection is not None
        and primary_selection.geometry_resolution.supported
    ):
        return OffsetEvaluation(tuple(candidates), primary_selection)

    extension_plan = separator_extension_sequence_plan(
        context.request,
        physical_spec,
        hypothesis.count,
        hypothesis.strip_mode,
        hypothesis,
        cache=context.measurement_cache,
        outer_policy=context.policy.outer,
        separator_policy=context.policy.separator,
        scan_calibration=context.scan_calibration,
        primary_sequence_hypotheses=primary_plan.comparison_proposals,
    )
    candidates.extend(
        _assess_sequence_plan(context, hypothesis, offset, extension_plan)
    )

    guidance = content_separator_guidance_for_count(
        context.request,
        hypothesis.count,
        context.measurement_cache,
        context.policy.content,
        context.policy.candidate_plan.content_separator_guidance,
    )
    if guidance is not None:
        candidates.extend(
            assess_candidate(
                build_separator_candidate_with_guidance(
                    context.request,
                    physical_spec,
                    hypothesis.count,
                    hypothesis.strip_mode,
                    hypothesis,
                    offset_fraction=offset,
                    sequence_hypothesis=sequence_hypothesis,
                    guidance=guidance,
                    cache=context.measurement_cache,
                    separator_policy=context.policy.separator,
                    scan_calibration=context.scan_calibration,
                ),
                context,
            )
            for sequence_hypothesis in extension_plan.comparison_proposals
        )
    selection = (
        None
        if not candidates
        else select_candidates(
            tuple(candidates),
            context.policy.candidate_selection,
            larger_counts_evaluated=larger_counts_evaluated,
        )
    )
    return OffsetEvaluation(tuple(candidates), selection)


def evaluate_count_hypothesis(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    *,
    larger_counts_evaluated: bool,
) -> CountHypothesisEvaluation:
    candidates: list[AssessedCandidate] = []
    selection = None
    for offset in hypothesis.offsets:
        evaluation = _candidates_for_offset(
            context,
            hypothesis,
            offset,
            larger_counts_evaluated=larger_counts_evaluated,
        )
        candidates.extend(evaluation.candidates)
        if evaluation.geometry_resolved:
            selection = evaluation.selection
            break
    if selection is None and candidates:
        selection = select_candidates(
            tuple(candidates),
            context.policy.candidate_selection,
            larger_counts_evaluated=larger_counts_evaluated,
        )
    return CountHypothesisEvaluation(
        hypothesis=hypothesis,
        candidates=tuple(candidates),
        selection=selection,
    )
