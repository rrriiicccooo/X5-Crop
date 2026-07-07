from __future__ import annotations

from ....domain import Detection
from ....policies.runtime.policy import DetectionPolicy
from .confidence_caps import apply_candidate_confidence_cap


SAFETY_CANDIDATE_REVIEW_ONLY_REASON = "safety_candidate_review_only"


def apply_safety_candidate_assessment(
    detection: Detection,
    *,
    confidence_threshold: float,
    policy: DetectionPolicy,
) -> None:
    safety_cap = (
        policy.scoring.no_auto_cap_partial
        if detection.strip_mode == "partial"
        else policy.scoring.no_auto_cap_full
    )
    cap = min(float(safety_cap), max(0.0, float(confidence_threshold) - 0.01))
    apply_candidate_confidence_cap(
        detection,
        cap,
        SAFETY_CANDIDATE_REVIEW_ONLY_REASON,
    )
    detection.review_reasons.append(SAFETY_CANDIDATE_REVIEW_ONLY_REASON)
    detection.review_reasons = sorted(set(detection.review_reasons))

    assessment = detection.detail.get("candidate_assessment", {})
    if isinstance(assessment, dict):
        assessment["auto_gate"] = False
        assessment["source"] = "safety_candidate"
        auto_gate_inputs = assessment.get("auto_gate_inputs")
        if isinstance(auto_gate_inputs, dict):
            auto_gate_inputs["source"] = "safety_candidate"

    detection.detail["safety_candidate"] = {
        "used": True,
        "review_only": True,
        "separator_local_mode": policy.outer.proposal.geometry.separator.local.mode,
        "separator_full_width_mode": policy.outer.proposal.geometry.separator.full_width.mode,
        "strategies": list(policy.candidate_plan.safety_candidate.strategies),
    }


__all__ = [
    "SAFETY_CANDIDATE_REVIEW_ONLY_REASON",
    "apply_safety_candidate_assessment",
]
