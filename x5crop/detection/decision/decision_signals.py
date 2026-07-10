from __future__ import annotations

from typing import Any

from ...constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_CONTENT_PRIMARY,
    CANDIDATE_SOURCE_HARD_SAFETY,
    CANDIDATE_SOURCE_REVIEW_ONLY,
    CANDIDATE_SOURCE_SAFETY,
)
from ...domain import DetectionCandidate
from ...policies.decision.contract import DetectionDecisionContract


_CONTENT_EVIDENCE_CANDIDATE_SOURCES = frozenset(
    {
        CANDIDATE_SOURCE_CONTENT,
        CANDIDATE_SOURCE_CONTENT_PRIMARY,
        "content",
    }
)

_NON_AUTO_CANDIDATE_SOURCES = frozenset(
    {
        CANDIDATE_SOURCE_HARD_SAFETY,
        CANDIDATE_SOURCE_REVIEW_ONLY,
    }
)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def decision_signals_for(
    detection: DetectionCandidate,
    evidence: dict[str, Any],
    policy: DetectionDecisionContract,
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    competition = _dict(detection.detail.get("candidate_competition"))
    exposure_overlap = _dict(detection.detail.get("exposure_overlap_evidence"))
    output_protection = _dict(detection.detail.get("output_protection_plan"))
    assessment_source = str(assessment.get("source") or "")
    candidate_source = str(detection.detail.get("candidate_source") or "")
    source = assessment_source or candidate_source
    content_only_evidence = source in _CONTENT_EVIDENCE_CANDIDATE_SOURCES
    safety_or_review_only = (
        assessment_source == CANDIDATE_SOURCE_SAFETY
        or candidate_source in _NON_AUTO_CANDIDATE_SOURCES
    )
    margin_raw = competition.get("margin_to_second")
    margin = None if margin_raw is None else _float(margin_raw)
    partial_edge_safe = bool(evidence["partial_edge"]["ok"])
    partial_full_conflict = bool(competition.get("partial_full_conflict", False))
    candidate_competition_close = (
        (
            (
                margin is not None
                and margin < policy.decision.candidate_close_margin
            )
            or partial_full_conflict
        )
        and not partial_edge_safe
    )
    active_signals: list[str] = []
    if content_only_evidence:
        active_signals.append("content_only_evidence")
    if safety_or_review_only:
        active_signals.append("safety_or_review_only")
    if candidate_competition_close:
        active_signals.append("candidate_competition_close")
    exposure_overlap_unresolved = bool(
        exposure_overlap.get("exposure_overlap_detected", False)
        and not output_protection.get("feasible", False)
    )
    if exposure_overlap_unresolved:
        active_signals.append("exposure_overlap_unresolved")
    partial_edge_uncertain = bool(
        detection.strip_mode == "partial"
        and policy.evidence.partial_requires_safe_edge
        and not partial_edge_safe
    )
    if partial_edge_uncertain:
        active_signals.append("partial_edge_uncertain")
    return {
        "active_signals": active_signals,
        "candidate_source_detail": {
            "assessment_source": assessment_source,
            "candidate_source": candidate_source,
            "content_only_evidence_source": source if content_only_evidence else "",
            "safety_or_review_only_source": (
                assessment_source
                if assessment_source == CANDIDATE_SOURCE_SAFETY
                else candidate_source
                if candidate_source in _NON_AUTO_CANDIDATE_SOURCES
                else ""
            ),
        },
        "content_only_evidence": bool(content_only_evidence),
        "safety_or_review_only": bool(safety_or_review_only),
        "outer_content_alignment_failed": not bool(evidence["outer"]["ok"]),
        "separator_support_incomplete": not bool(evidence["separator"]["ok"]),
        "photo_geometry_unstable": not bool(evidence["geometry"]["ok"]),
        "content_integrity_failed": not bool(evidence["content"]["ok"]),
        "exposure_overlap_detected": bool(
            exposure_overlap.get("exposure_overlap_detected", False)
        ),
        "exposure_overlap_unresolved": exposure_overlap_unresolved,
        "exposure_overlap_evidence": exposure_overlap,
        "output_protection_plan": output_protection,
        "candidate_competition_close": bool(candidate_competition_close),
        "candidate_margin_to_second": margin,
        "partial_full_conflict": bool(partial_full_conflict),
        "selection_uncertainty_inputs": competition.get("selection_uncertainty_inputs", []),
        "partial_edge_uncertain": bool(partial_edge_uncertain),
    }
