from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.decision import RuntimeDecisionPolicy


def runtime_decision_policy(params: FormatParameters) -> RuntimeDecisionPolicy:
    decision = params.decision_review
    return RuntimeDecisionPolicy(
        align_outer_to_content=True,
        outer_alignment_disabled_reason="disabled_by_policy",
        outer_candidate_disagreement_review_reason="outer_candidate_disagreement",
        deskew_uncertain_review_reason="deskew_uncertain",
        content_aspect_conflict_cap=float(decision.content_aspect_conflict_cap),
        content_low_confidence_cap=float(decision.content_low_confidence_cap),
        outer_mismatch_cap=float(decision.outer_mismatch_cap),
        lucky_pass_risk_cap=float(decision.lucky_pass_risk_cap),
    )


__all__ = [
    "runtime_decision_policy",
]
