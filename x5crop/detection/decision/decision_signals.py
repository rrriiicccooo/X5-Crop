from __future__ import annotations

from typing import Any

from ...constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_HARD_SAFETY,
    CANDIDATE_SOURCE_REVIEW_ONLY,
)
from ...domain import DetectionCandidate, OutputProtectionPlan
from ...policies.decision.contract import DetectionDecisionContract


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
    output_protection_plan: OutputProtectionPlan,
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    competition = _dict(detection.detail.get("candidate_competition"))
    exposure_overlap = _dict(detection.detail.get("exposure_overlap_evidence"))
    assessment_source = str(assessment.get("source") or "")
    candidate_source = str(detection.detail.get("candidate_source") or "")
    content_only_evidence = candidate_source == CANDIDATE_SOURCE_CONTENT
    safety_or_review_only = candidate_source in _NON_AUTO_CANDIDATE_SOURCES
    margin_raw = competition.get("margin_to_second")
    margin = None if margin_raw is None else _float(margin_raw)
    partial_edge_safe = bool(evidence["partial_edge"]["ok"])
    partial_full_conflict = bool(competition.get("partial_full_conflict", False))
    candidate_competition_close = (
        (
            (
                margin is not None
                and margin < policy.candidate_selection.close_margin
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
        output_protection_plan.exposure_overlap_detected
        and not output_protection_plan.feasible
    )
    if exposure_overlap_unresolved:
        active_signals.append("exposure_overlap_unresolved")
    partial_edge_uncertain = bool(
        detection.strip_mode == "partial"
        and not partial_edge_safe
    )
    if partial_edge_uncertain:
        active_signals.append("partial_edge_uncertain")
    return {
        "active_signals": active_signals,
        "candidate_source_detail": {
            "assessment_source": assessment_source,
            "candidate_source": candidate_source,
            "content_only_evidence_source": (
                candidate_source if content_only_evidence else ""
            ),
            "safety_or_review_only_source": (
                candidate_source if candidate_source in _NON_AUTO_CANDIDATE_SOURCES else ""
            ),
        },
        "content_only_evidence": bool(content_only_evidence),
        "safety_or_review_only": bool(safety_or_review_only),
        "outer_content_alignment_failed": not bool(evidence["outer"]["ok"]),
        "separator_support_incomplete": not bool(evidence["separator"]["ok"]),
        "photo_geometry_unstable": not bool(evidence["geometry"]["ok"]),
        "content_integrity_failed": not bool(evidence["content"]["ok"]),
        "exposure_overlap_detected": bool(output_protection_plan.exposure_overlap_detected),
        "exposure_overlap_unresolved": exposure_overlap_unresolved,
        "candidate_competition_close": bool(candidate_competition_close),
        "candidate_margin_to_second": margin,
        "partial_full_conflict": bool(partial_full_conflict),
        "selection_uncertainty_inputs": competition.get("selection_uncertainty_inputs", []),
        "partial_edge_uncertain": bool(partial_edge_uncertain),
    }
