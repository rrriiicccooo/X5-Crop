from __future__ import annotations

from ...context import DetectionContext
from ..assessment.candidate import assess_candidate
from ..build.detection import build_frame_sequence_geometry
from ..model import AssessedCandidate
from ..plan.count_hypotheses import CountHypothesis
from ..selection.choose import select_candidates
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
        built = build_frame_sequence_geometry(
            context.request,
            context.policy.physical_spec,
            plan.count_hypothesis,
            sequence_hypothesis,
            context.scan_calibration,
            cache=context.measurement_cache,
            separator_policy=context.policy.separator,
            solver_parameters=context.policy.candidate_plan.sequence_solver,
        )
        assessed.append(assess_candidate(built, context))
    return assessed


def evaluate_count_hypothesis(
    context: DetectionContext,
    hypothesis: CountHypothesis,
    *,
    larger_counts_evaluated: bool,
) -> CountHypothesisEvaluation:
    sequence_plan = frame_sequence_plan(
        context.request,
        context.policy.physical_spec,
        hypothesis,
        cache=context.measurement_cache,
        content_policy=context.policy.content,
        separator_policy=context.policy.separator,
        hypothesis_parameters=context.policy.candidate_plan.sequence_hypotheses,
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
