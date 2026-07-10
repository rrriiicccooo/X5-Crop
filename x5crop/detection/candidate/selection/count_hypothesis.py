from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
from ..assessment.count_hypothesis import CountHypothesisEvaluation
from ..plan.count_hypotheses import CountHypothesisPlan


def count_selection_detail(
    selected: DetectionCandidate,
    plan: CountHypothesisPlan,
    evaluations: list[CountHypothesisEvaluation],
) -> dict[str, Any]:
    selected_evaluation = next(
        (
            evaluation
            for evaluation in evaluations
            if evaluation.hypothesis.count == selected.count
        ),
        None,
    )
    if plan.requested_count is not None:
        reason = "requested_count"
    elif not plan.automatic:
        reason = "format_default_count"
    elif selected_evaluation is not None and selected_evaluation.count_resolved:
        reason = "largest_physically_supported_count"
    else:
        reason = "highest_ranked_candidate_without_physical_resolution"
    return {
        "selected_count": int(selected.count),
        "reason": reason,
        "plan": plan.report_detail(),
        "evaluations": [evaluation.report_detail() for evaluation in evaluations],
        "physical_search_stopped_after_count": next(
            (
                int(evaluation.hypothesis.count)
                for evaluation in evaluations
                if plan.automatic and evaluation.count_resolved
            ),
            None,
        ),
    }
