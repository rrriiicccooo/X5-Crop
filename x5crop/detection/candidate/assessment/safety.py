from __future__ import annotations

from ....domain import DetectionCandidate
from ....policies.runtime.policy import DetectionPolicy
from ..signals import SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE


def apply_safety_candidate_assessment(
    detection: DetectionCandidate,
    *,
    policy: DetectionPolicy,
) -> None:
    detection.detail["safety_candidate"] = {
        "used": True,
        "candidate_gate_eligible": False,
        "candidate_blocker_signal": SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE,
        "separator_local_mode": policy.outer.proposal.geometry.separator.local.mode,
        "separator_full_width_mode": policy.outer.proposal.geometry.separator.full_width.mode,
    }
