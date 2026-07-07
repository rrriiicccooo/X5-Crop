from __future__ import annotations

from typing import Any

from ...constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_CONTENT_PRIMARY,
    CANDIDATE_SOURCE_HARD_SAFETY,
    CANDIDATE_SOURCE_REVIEW_ONLY,
    CANDIDATE_SOURCE_SAFETY,
)
from ...domain import Detection
from ...policies.decision.contract import DetectionDecisionContract


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def risk_summary_for(
    detection: Detection,
    evidence: dict[str, Any],
    policy: DetectionDecisionContract,
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    competition = _dict(detection.detail.get("candidate_competition"))
    lucky = _dict(detection.detail.get("lucky_pass_risk_score"))
    source = str(assessment.get("source") or detection.detail.get("candidate_source") or "")
    margin_raw = competition.get("margin_to_second")
    margin = None if margin_raw is None else _float(margin_raw)
    partial_edge_safe = bool(evidence["partial_edge"]["ok"])
    partial_full_conflict = bool(competition.get("partial_full_conflict", False))
    close_competition = (
        (
            (
                margin is not None
                and margin < policy.risk.candidate_close_margin
            )
            or partial_full_conflict
        )
        and not (
            partial_edge_safe
            and policy.risk.suppress_close_competition_when_partial_edge_safe
        )
    )
    return {
        "content_only_evidence": source in {CANDIDATE_SOURCE_CONTENT, CANDIDATE_SOURCE_CONTENT_PRIMARY, "content"},
        "safety_or_review_only": (
            source == CANDIDATE_SOURCE_SAFETY
            or detection.detail.get("candidate_source") == CANDIDATE_SOURCE_HARD_SAFETY
            or detection.detail.get("candidate_source") == CANDIDATE_SOURCE_REVIEW_ONLY
        ),
        "outer_content_mismatch": not bool(evidence["outer"]["ok"]),
        "overlap_risk": bool(lucky.get("risk", False)),
        "candidate_competition_close": bool(close_competition),
        "candidate_margin_to_second": margin,
        "partial_full_conflict": bool(partial_full_conflict),
        "selection_risk_inputs": detection.detail.get("selection_risk_inputs", []),
        "partial_edge_uncertain": bool(
            detection.strip_mode == "partial"
            and policy.evidence.partial_requires_safe_edge
            and not partial_edge_safe
        ),
        "lucky_pass_risk": lucky,
    }


__all__ = [
    "risk_summary_for",
]
