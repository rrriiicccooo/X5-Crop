from __future__ import annotations

from ....constants import CANDIDATE_SOURCE_SAFETY
from ....domain import Detection
from ....policies.runtime.policy import DetectionPolicy
from ..signals import SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE, add_candidate_signal
from .candidate_gate import candidate_signal_gate_checks
from .confidence_caps import apply_candidate_confidence_cap


SAFETY_CANDIDATE_BLOCKER = SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE


def _detail_list(value: object) -> list:
    return list(value) if isinstance(value, list) else []


def _append_safety_candidate_gate_check(detection: Detection) -> None:
    assessment = detection.detail.get("candidate_assessment")
    if not isinstance(assessment, dict):
        assessment = {}
        detection.detail["candidate_assessment"] = assessment

    gate_checks = candidate_signal_gate_checks([SAFETY_CANDIDATE_BLOCKER])
    checks = [check.report_detail() for check in gate_checks]
    blockers = [check.signal for check in gate_checks if check.severity == "blocker"]
    diagnostics = [check.signal for check in gate_checks if check.severity == "diagnostic"]
    confidence_caps = _detail_list(detection.detail.get("candidate_confidence_caps"))

    assessment["source"] = CANDIDATE_SOURCE_SAFETY
    assessment["blockers"] = blockers
    assessment["diagnostics"] = diagnostics
    assessment["confidence_caps"] = confidence_caps
    assessment["candidate_gate"] = {
        "passed": False,
        "checks": checks,
        "blockers": blockers,
        "diagnostics": diagnostics,
        "confidence_caps": confidence_caps,
    }


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
        SAFETY_CANDIDATE_BLOCKER,
    )
    add_candidate_signal(detection, SAFETY_CANDIDATE_BLOCKER)
    _append_safety_candidate_gate_check(detection)

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
