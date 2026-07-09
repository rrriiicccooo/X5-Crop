from __future__ import annotations

from typing import Any

from ..domain import Detection


CANDIDATE_COMPETITION = "candidate_competition"
CANDIDATE_ASSESSMENT = "candidate_assessment"
CANDIDATE_SIGNALS = "candidate_signals"
CONTENT_EVIDENCE = "content_evidence"
DECISION_POLICY_DETAIL = "decision_policy_detail"
DECISION_SUMMARY = "decision_summary"
DESKEW = "deskew"
DECISION_SIGNALS = "decision_signals"
EVIDENCE_SUMMARY = "evidence_summary"
OUTER_CONTENT_ALIGNMENT = "outer_content_alignment"
OUTPUT_OVERLAP_EVIDENCE = "output_overlap_evidence"
POLICY_ID = "policy_id"
RUNTIME_POLICY_DETAIL = "runtime_policy_detail"
SCAN_CALIBRATION = "scan_calibration"
STRIP_COMPLETENESS = "strip_completeness"
HOLDER_OCCUPANCY = "holder_occupancy"


def detail_dict(detection: Detection, key: str) -> dict[str, Any]:
    value = detection.detail.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def candidate_competition(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, CANDIDATE_COMPETITION)


def candidate_assessment(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, CANDIDATE_ASSESSMENT)


def candidate_signals_from_detail(detection: Detection) -> list[str]:
    signals = detection.detail.get(CANDIDATE_SIGNALS)
    if isinstance(signals, list):
        return [str(signal) for signal in signals if signal]
    return []


def decision_summary(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, DECISION_SUMMARY)


def has_current_decision_summary(detection: Detection) -> bool:
    summary = detection.detail.get(DECISION_SUMMARY)
    return isinstance(summary, dict) and isinstance(summary.get("final_review_reasons"), list)


def decision_schema_diagnostics(detection: Detection) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    summary = detection.detail.get(DECISION_SUMMARY)
    if not isinstance(summary, dict):
        diagnostics.append({"owner": "decision", "reason": "decision_summary_missing"})
        return diagnostics
    if not isinstance(summary.get("final_review_reasons"), list):
        diagnostics.append({"owner": "decision", "reason": "final_review_reasons_missing"})
    if not isinstance(summary.get("decision_gate"), dict):
        diagnostics.append({"owner": "decision", "reason": "decision_gate_missing"})
    return diagnostics


def final_review_reasons_from_detail(detection: Detection) -> list[str]:
    reasons = decision_summary(detection).get("final_review_reasons")
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons]
    return []


def runtime_policy_detail(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, RUNTIME_POLICY_DETAIL)


def policy_id_from_detail(detection: Detection) -> str:
    policy_id = detection.detail.get(POLICY_ID)
    if policy_id:
        return str(policy_id)
    policy = runtime_policy_detail(detection)
    return str(policy.get(POLICY_ID, ""))


__all__ = [
    "CANDIDATE_COMPETITION",
    "CANDIDATE_ASSESSMENT",
    "CANDIDATE_SIGNALS",
    "CONTENT_EVIDENCE",
    "DECISION_POLICY_DETAIL",
    "DECISION_SUMMARY",
    "DECISION_SIGNALS",
    "DESKEW",
    "EVIDENCE_SUMMARY",
    "OUTER_CONTENT_ALIGNMENT",
    "OUTPUT_OVERLAP_EVIDENCE",
    "POLICY_ID",
    "RUNTIME_POLICY_DETAIL",
    "SCAN_CALIBRATION",
    "STRIP_COMPLETENESS",
    "HOLDER_OCCUPANCY",
    "candidate_competition",
    "candidate_assessment",
    "candidate_signals_from_detail",
    "decision_schema_diagnostics",
    "decision_summary",
    "detail_dict",
    "final_review_reasons_from_detail",
    "has_current_decision_summary",
    "policy_id_from_detail",
    "runtime_policy_detail",
]
