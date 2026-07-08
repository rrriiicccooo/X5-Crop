from __future__ import annotations

from ....constants import CANDIDATE_SOURCE_SAFETY
from ....domain import Detection
from ....policies.runtime.policy import DetectionPolicy
from ..signals import SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE


SAFETY_CANDIDATE_BLOCKER = SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE


def apply_safety_candidate_assessment(
    detection: Detection,
    *,
    confidence_threshold: float,
    policy: DetectionPolicy,
) -> None:
    detection.detail["safety_candidate"] = {
        "used": True,
        "candidate_gate_eligible": False,
        "candidate_blocker_signal": SAFETY_CANDIDATE_BLOCKER,
        "separator_local_mode": policy.outer.proposal.geometry.separator.local.mode,
        "separator_full_width_mode": policy.outer.proposal.geometry.separator.full_width.mode,
        "strategies": list(policy.candidate_plan.safety_candidate.strategies),
    }


__all__ = [
    "SAFETY_CANDIDATE_BLOCKER",
    "apply_safety_candidate_assessment",
]
