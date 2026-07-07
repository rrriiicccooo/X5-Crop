from __future__ import annotations

from typing import Any

from ..domain import Detection


CANDIDATE_COMPETITION = "candidate_competition"
CANDIDATE_ASSESSMENT = "candidate_assessment"
CONTENT_EVIDENCE = "content_evidence"
DECISION_POLICY_DETAIL = "decision_policy_detail"
DECISION_SUMMARY = "decision_summary"
DESKEW = "deskew"
EVIDENCE_SUMMARY = "evidence_summary"
LUCKY_PASS_RISK_SCORE = "lucky_pass_risk_score"
OUTER_CONTENT_ALIGNMENT = "outer_content_alignment"
OVERLAP_BLEED_RISK = "overlap_bleed_risk"
POLICY = "policy"
POLICY_ID = "policy_id"
RISK_SUMMARY = "risk_summary"
RUNTIME_POLICY_DETAIL = "runtime_policy_detail"


def detail_dict(detection: Detection, key: str) -> dict[str, Any]:
    value = detection.detail.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def candidate_competition(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, CANDIDATE_COMPETITION)


def candidate_assessment(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, CANDIDATE_ASSESSMENT)


def decision_summary(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, DECISION_SUMMARY)


def policy_detail(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, POLICY)


def runtime_policy_detail(detection: Detection) -> dict[str, Any]:
    return detail_dict(detection, RUNTIME_POLICY_DETAIL)


def policy_id_from_detail(detection: Detection) -> str:
    policy_id = detection.detail.get(POLICY_ID)
    if policy_id:
        return str(policy_id)
    policy = runtime_policy_detail(detection) or policy_detail(detection)
    return str(policy.get(POLICY_ID, ""))


__all__ = [
    "CANDIDATE_COMPETITION",
    "CANDIDATE_ASSESSMENT",
    "CONTENT_EVIDENCE",
    "DECISION_POLICY_DETAIL",
    "DECISION_SUMMARY",
    "DESKEW",
    "EVIDENCE_SUMMARY",
    "LUCKY_PASS_RISK_SCORE",
    "OUTER_CONTENT_ALIGNMENT",
    "OVERLAP_BLEED_RISK",
    "POLICY",
    "POLICY_ID",
    "RISK_SUMMARY",
    "RUNTIME_POLICY_DETAIL",
    "candidate_competition",
    "candidate_assessment",
    "decision_summary",
    "detail_dict",
    "policy_detail",
    "policy_id_from_detail",
    "runtime_policy_detail",
]
