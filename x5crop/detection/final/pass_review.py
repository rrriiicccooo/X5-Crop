from __future__ import annotations

from typing import Any

import numpy as np

from ...runtime_config import RuntimeConfig
from ...constants import (
    ANALYSIS_SOURCE_CONTENT,
    ANALYSIS_SOURCE_CONTENT_PRIMARY,
    ANALYSIS_SOURCE_HARD_FALLBACK,
    ANALYSIS_SOURCE_REVIEW_ONLY,
    HARD_GAP_METHODS,
    REASON_AUTO_GATE_NOT_SATISFIED,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_LUCKY_PASS_RISK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ...domain import Detection
from ...formats import FormatSpec
from ...policies.decision_contract import DetectionDecisionContract, decision_contract_for


REASON_NORMALIZATION_MAP = {
    REASON_AUTO_GATE_NOT_SATISFIED: "evidence_combination_insufficient",
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK: "separator_evidence_incomplete",
    REASON_CONTENT_EVIDENCE_WEAK: "content_only_evidence",
    REASON_CONTENT_ASPECT_CONFLICT: "outer_content_mismatch",
    REASON_OUTER_CONTENT_BBOX_MISMATCH: "outer_content_mismatch",
    REASON_LUCKY_PASS_RISK: "overlap_risk",
    "weak_separators": "separator_evidence_incomplete",
    "mostly_equal_split": "separator_evidence_incomplete",
    "separator_below_threshold": "separator_evidence_incomplete",
    "content_only_not_enough_for_auto": "content_only_evidence",
    "content_confidence_low": "content_only_evidence",
    "content_aspect_uncertain": "outer_content_mismatch",
    "content_coverage_weak": "content_only_evidence",
    "outer_box_too_large": "outer_content_mismatch",
    "outer_box_uncertain": "outer_content_mismatch",
    "unstable_frame_width": "geometry_unstable",
    "candidate_competition_uncertain": "candidate_competition_close",
    "partial_too_ambiguous": "partial_edge_uncertain",
    "partial_strip_count_candidate": "partial_edge_uncertain",
    "likely_partial_strip": "partial_edge_uncertain",
    "partial_outer_leading_content": "partial_edge_uncertain",
    "partial_frame_content_unstable": "partial_edge_uncertain",
    "too_few_broad_separator_width_gaps": "partial_edge_uncertain",
    "needs_manual_review": "evidence_combination_insufficient",
}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _gap_method_count(detection: Detection, methods: set[str]) -> int:
    return sum(1 for gap in detection.gaps if gap.method in methods)


def normalized_review_reasons(reasons: list[str]) -> list[str]:
    normalized = [REASON_NORMALIZATION_MAP.get(str(reason), str(reason)) for reason in reasons]
    return sorted(set(reason for reason in normalized if reason))


def _separator_summary(detection: Detection) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    hard_detail = _dict(assessment.get("separator_hard_evidence"))
    expected = _int(hard_detail.get("expected_gaps"), max(0, int(detection.count) - 1))
    hard = _int(hard_detail.get("hard_gaps"), _gap_method_count(detection, set(HARD_GAP_METHODS)))
    grid = _int(hard_detail.get("grid_gaps"), _gap_method_count(detection, {"grid"}))
    equal = _int(hard_detail.get("equal_gaps"), _gap_method_count(detection, {"equal"}))
    content = _gap_method_count(detection, {"content"})
    model = grid + equal + content
    denominator = max(1, expected)
    return {
        "expected_gaps": expected,
        "hard_gaps": hard,
        "grid_gaps": grid,
        "equal_gaps": equal,
        "content_gaps": content,
        "model_gaps": model,
        "hard_gap_ratio": hard / float(denominator),
        "model_gap_share": model / float(denominator),
        "gate_reason": hard_detail.get("reason"),
        "geometry_support_mode": hard_detail.get("separator_geometry_support_mode"),
        "hard_detail": hard_detail,
    }


def evidence_summary_for(
    gray: np.ndarray,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    policy: DetectionDecisionContract,
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    separator = _separator_summary(detection)
    outer_area_ratio = _float(
        detection.detail.get("outer_area_ratio"),
        (detection.outer.width * detection.outer.height) / float(max(1, gray.shape[0] * gray.shape[1])),
    )
    geometry_score = _float(assessment.get("geometry_score"), 0.0)
    content_score = _float(assessment.get("content_score"), 0.0)
    width_cv = _float(detection.detail.get("width_cv"), 1.0)
    content_support = str(content_detail.get("support", assessment.get("content_support", "")))
    partial_detail = _dict(assessment.get("partial_safe_extra_frames"))
    partial_edge_safe = bool(partial_detail.get("ok", False))
    expected = int(separator["expected_gaps"])
    hard_ratio = float(separator["hard_gap_ratio"])
    model_share = float(separator["model_gap_share"])
    geometry_support_mode = str(separator.get("geometry_support_mode") or "")
    geometry_supported_separator = (
        policy.evidence.allow_geometry_supported_separator
        and geometry_support_mode in {"detected_geometry", "stable_grid"}
        and hard_ratio >= policy.evidence.geometry_supported_min_hard_ratio
        and width_cv <= policy.evidence.geometry_supported_max_width_cv_ratio
        and int(separator["equal_gaps"]) <= policy.evidence.max_equal_gap_count
        and content_support == "ok"
    )
    partial_supported_separator = (
        detection.strip_mode == "partial"
        and partial_edge_safe
        and int(separator["hard_gaps"]) >= 1
        and content_support == "ok"
    )
    separator_ok = (
        expected <= 0
        or geometry_supported_separator
        or partial_supported_separator
        or (
            int(separator["hard_gaps"]) >= policy.evidence.min_hard_separator_count
            and hard_ratio >= policy.evidence.min_hard_separator_ratio
            and int(separator["equal_gaps"]) <= policy.evidence.max_equal_gap_count
            and int(separator["content_gaps"]) <= policy.evidence.max_content_gap_count
            and model_share <= policy.evidence.max_model_gap_share
        )
    )
    outer_ok = (
        policy.evidence.min_outer_area_ratio
        <= outer_area_ratio
        <= policy.evidence.max_outer_area_ratio
        and bool(outer_alignment.get("ok", True))
    )
    geometry_ok = (
        width_cv <= policy.evidence.max_width_cv_ratio
        and geometry_score >= policy.evidence.min_geometry_score
    )
    content_ok = (
        content_support == "ok"
        and content_score >= policy.evidence.min_content_score
    )
    return {
        "outer": {
            "ok": bool(outer_ok),
            "outer_area_ratio": outer_area_ratio,
            "min_outer_area_ratio": policy.evidence.min_outer_area_ratio,
            "max_outer_area_ratio": policy.evidence.max_outer_area_ratio,
            "outer_content_alignment": outer_alignment,
        },
        "separator": {
            **separator,
            "ok": bool(separator_ok),
            "geometry_supported_separator": bool(geometry_supported_separator),
            "partial_supported_separator": bool(partial_supported_separator),
            "min_hard_separator_ratio": policy.evidence.min_hard_separator_ratio,
            "min_hard_separator_count": policy.evidence.min_hard_separator_count,
            "max_model_gap_share": policy.evidence.max_model_gap_share,
        },
        "geometry": {
            "ok": bool(geometry_ok),
            "width_cv": width_cv,
            "max_width_cv_ratio": policy.evidence.max_width_cv_ratio,
            "geometry_score": geometry_score,
            "min_geometry_score": policy.evidence.min_geometry_score,
        },
        "content": {
            "ok": bool(content_ok),
            "support": content_support,
            "content_score": content_score,
            "min_content_score": policy.evidence.min_content_score,
            "detail": content_detail,
        },
        "partial_edge": {
            "ok": bool(partial_edge_safe),
            "required": bool(detection.strip_mode == "partial" and policy.evidence.partial_requires_safe_edge),
            "detail": partial_detail,
        },
    }


def risk_summary_for(
    detection: Detection,
    evidence: dict[str, Any],
    policy: DetectionDecisionContract,
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    competition = _dict(detection.detail.get("candidate_competition"))
    lucky = _dict(detection.detail.get("lucky_pass_risk_score"))
    source = str(assessment.get("source") or detection.detail.get("analysis_source") or "")
    margin_raw = competition.get("margin_to_second")
    margin = None if margin_raw is None else _float(margin_raw)
    partial_edge_safe = bool(evidence["partial_edge"]["ok"])
    close_competition = (
        margin is not None
        and margin < policy.risk.candidate_close_margin
        and not (
            partial_edge_safe
            and policy.risk.suppress_close_competition_when_partial_edge_safe
        )
    )
    return {
        "content_only_evidence": source in {ANALYSIS_SOURCE_CONTENT, ANALYSIS_SOURCE_CONTENT_PRIMARY, "content"},
        "fallback_or_review_only": (
            detection.detail.get("analysis_source") == ANALYSIS_SOURCE_HARD_FALLBACK
            or detection.detail.get("analysis_source") == ANALYSIS_SOURCE_REVIEW_ONLY
        ),
        "outer_content_mismatch": not bool(evidence["outer"]["ok"]),
        "overlap_risk": bool(lucky.get("risk", False)),
        "candidate_competition_close": bool(close_competition),
        "candidate_margin_to_second": margin,
        "partial_edge_uncertain": bool(
            detection.strip_mode == "partial"
            and policy.evidence.partial_requires_safe_edge
            and not partial_edge_safe
        ),
        "lucky_pass_risk": lucky,
    }


def apply_final_decision_policy(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
) -> Detection:
    policy = decision_contract_for(fmt.name, detection.strip_mode)
    evidence = evidence_summary_for(gray, detection, content_detail, outer_alignment, policy)
    risk = risk_summary_for(detection, evidence, policy)
    reasons: list[str] = []
    if risk["content_only_evidence"] or risk["fallback_or_review_only"]:
        reasons.append(policy.decision.content_only_evidence_reason)
    if not bool(evidence["outer"]["ok"]) and policy.risk.review_on_outer_content_mismatch:
        reasons.append(policy.decision.outer_content_mismatch_reason)
    if not bool(evidence["separator"]["ok"]):
        reasons.append(policy.decision.separator_incomplete_reason)
    if not bool(evidence["geometry"]["ok"]):
        reasons.append(policy.decision.geometry_unstable_reason)
    if not bool(evidence["content"]["ok"]):
        reasons.append(policy.decision.content_only_evidence_reason)
    if risk["candidate_competition_close"] and policy.risk.review_on_close_competition:
        reasons.append(policy.decision.candidate_competition_close_reason)
    if risk["overlap_risk"] and (
        policy.risk.review_on_overlap_risk or policy.risk.review_on_lucky_pass_risk
    ):
        reasons.append(policy.decision.overlap_risk_reason)
    if risk["partial_edge_uncertain"]:
        reasons.append(policy.decision.partial_edge_uncertain_reason)
    if detection.confidence < config.confidence_threshold and not reasons:
        reasons.append(policy.decision.decision_insufficient_reason)

    reasons = normalized_review_reasons(reasons)
    existing_reasons = normalized_review_reasons(list(detection.review_reasons))
    final_reasons = sorted(set(existing_reasons + reasons))
    passed = detection.confidence >= config.confidence_threshold and not final_reasons
    if not passed:
        detection.confidence = min(float(detection.confidence), policy.decision.review_confidence_cap)
    detection.review_reasons = final_reasons
    competition = detection.detail.get("candidate_competition")
    if isinstance(competition, dict):
        selected = competition.get("selected_candidate")
        if isinstance(selected, dict):
            selected["confidence"] = float(detection.confidence)
            selected["review_reasons"] = list(detection.review_reasons)
            selected["decision_status"] = "approved_auto" if passed else "needs_review"
        top = competition.get("top_candidates")
        if isinstance(top, list):
            for candidate in top:
                if isinstance(candidate, dict) and bool(candidate.get("selected", False)):
                    candidate["confidence"] = float(detection.confidence)
                    candidate["review_reasons"] = list(detection.review_reasons)
                    candidate["decision_status"] = "approved_auto" if passed else "needs_review"
    detail = {
        "policy_id": policy.policy_id,
        "schema_version": policy.schema_version,
        "pass": bool(passed),
        "status": "approved_auto" if passed else "needs_review",
        "review_reasons_added": reasons,
        "evidence_summary": evidence,
        "risk_summary": risk,
        "decision_policy_detail": policy.report_detail(),
    }
    detection.detail["decision_summary"] = detail
    detection.detail["evidence_summary"] = evidence
    detection.detail["risk_summary"] = risk
    detection.detail["decision_policy_detail"] = policy.report_detail()
    detection.detail["policy_id"] = policy.policy_id
    detection.detail["policy"] = policy.report_detail()
    return detection
