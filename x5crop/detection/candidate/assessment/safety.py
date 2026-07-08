from __future__ import annotations

from ....constants import CANDIDATE_SOURCE_SAFETY
from ....domain import Detection
from ....policies.runtime.policy import DetectionPolicy
from ...gate_checks import GateCheck, unique_signals
from ..signals import SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE, add_candidate_signal
from .confidence_caps import apply_candidate_confidence_cap


SAFETY_CANDIDATE_BLOCKER = SIGNAL_SAFETY_CANDIDATE_NOT_AUTO_ELIGIBLE


def _detail_list(value: object) -> list:
    return list(value) if isinstance(value, list) else []


def _append_safety_candidate_gate_check(detection: Detection) -> None:
    assessment = detection.detail.get("candidate_assessment")
    if not isinstance(assessment, dict):
        assessment = {}
        detection.detail["candidate_assessment"] = assessment

    gate = assessment.get("candidate_gate")
    gate_detail = dict(gate) if isinstance(gate, dict) else {}
    checks = _detail_list(gate_detail.get("checks"))
    safety_check = GateCheck(
        code="candidate_source_auto_allowed",
        stage="candidate",
        bucket="source",
        passed=False,
        severity="blocker",
        signal=SAFETY_CANDIDATE_BLOCKER,
        detail={"source": CANDIDATE_SOURCE_SAFETY},
    )
    checks.append(safety_check.report_detail())

    blockers = unique_signals(
        [
            *[str(reason) for reason in _detail_list(assessment.get("blockers"))],
            *[str(reason) for reason in _detail_list(gate_detail.get("blockers"))],
            SAFETY_CANDIDATE_BLOCKER,
        ]
    )
    diagnostics = unique_signals(
        [
            *[str(reason) for reason in _detail_list(assessment.get("diagnostics"))],
            *[str(reason) for reason in _detail_list(gate_detail.get("diagnostics"))],
        ]
    )
    confidence_caps = _detail_list(detection.detail.get("candidate_confidence_caps"))

    assessment["source"] = CANDIDATE_SOURCE_SAFETY
    assessment["candidate_gate_passed"] = False
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
