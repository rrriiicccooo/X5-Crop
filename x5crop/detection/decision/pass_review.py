from __future__ import annotations

from typing import Any

import numpy as np

from ...runtime.config import RuntimeConfig
from ...constants import (
    CANDIDATE_SOURCE_CONTENT,
    CANDIDATE_SOURCE_CONTENT_PRIMARY,
    CANDIDATE_SOURCE_HARD_SAFETY,
    CANDIDATE_SOURCE_REVIEW_ONLY,
    REASON_AUTO_GATE_NOT_SATISFIED,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_EVIDENCE_DEPENDENCY_CYCLE_RISK,
    REASON_LUCKY_PASS_RISK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ...domain import Detection
from ...gap_methods import (
    is_content_model_gap_method,
    is_equal_model_gap_method,
    is_grid_model_gap_method,
    is_hard_gap_method,
)
from ..evidence.photo_width import (
    photo_width_stability_detail,
    photo_width_within_limit,
)
from ..evidence.separator_summary import SeparatorGateDetailSummary, separator_gate_detail_summary
from ...formats import FormatSpec
from ...policies.decision.contract import DetectionDecisionContract, decision_contract_for


REASON_NORMALIZATION_MAP = {
    REASON_AUTO_GATE_NOT_SATISFIED: "evidence_combination_insufficient",
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK: "separator_evidence_incomplete",
    REASON_CONTENT_EVIDENCE_WEAK: "content_only_evidence",
    REASON_CONTENT_ASPECT_CONFLICT: "outer_content_mismatch",
    REASON_OUTER_CONTENT_BBOX_MISMATCH: "outer_content_mismatch",
    REASON_LUCKY_PASS_RISK: "overlap_risk",
    REASON_EVIDENCE_DEPENDENCY_CYCLE_RISK: "evidence_dependency_cycle_risk",
    "weak_separators": "separator_evidence_incomplete",
    "mostly_equal_split": "separator_evidence_incomplete",
    "separator_below_threshold": "separator_evidence_incomplete",
    "content_only_not_enough_for_auto": "content_only_evidence",
    "content_confidence_low": "content_only_evidence",
    "content_aspect_uncertain": "outer_content_mismatch",
    "content_coverage_weak": "content_only_evidence",
    "outer_box_too_large": "outer_content_mismatch",
    "outer_box_uncertain": "outer_content_mismatch",
    "photo_width_unstable": "geometry_unstable",
    "unstable_frame_width": "geometry_unstable",
    "candidate_competition_uncertain": "candidate_competition_close",
    "partial_too_ambiguous": "partial_edge_uncertain",
    "likely_partial_strip": "partial_edge_uncertain",
    "partial_outer_leading_content": "partial_edge_uncertain",
    "partial_frame_content_unstable": "partial_edge_uncertain",
    "holder_edge_disambiguation_weak": "partial_edge_uncertain",
    "needs_manual_review": "evidence_combination_insufficient",
}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def normalized_review_reasons(reasons: list[str]) -> list[str]:
    normalized = [REASON_NORMALIZATION_MAP.get(str(reason), str(reason)) for reason in reasons]
    return sorted(set(reason for reason in normalized if reason))


def _gap_method_count(detection: Detection, predicate) -> int:
    return sum(1 for gap in detection.gaps if predicate(gap.method))


def _separator_summary_from_assessment(detection: Detection) -> SeparatorGateDetailSummary:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    hard_detail = _dict(assessment.get("separator_hard_evidence"))
    return separator_gate_detail_summary(
        hard_detail,
        expected_default=max(0, int(detection.count) - 1),
        hard_default=sum(1 for gap in detection.gaps if is_hard_gap_method(gap.method)),
        grid_default=_gap_method_count(detection, is_grid_model_gap_method),
        equal_default=_gap_method_count(detection, is_equal_model_gap_method),
        content_default=_gap_method_count(detection, is_content_model_gap_method),
    )


def _separator_summary(detection: Detection) -> dict[str, Any]:
    return _separator_summary_from_assessment(detection).evidence_detail()


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
    content_quality_score = _float(assessment.get("content_quality_score"), 0.0)
    width_cv = _float(detection.detail.get("width_cv"), 1.0)
    width_cv_source = str(detection.detail.get("width_cv_source") or "unknown")
    photo_width_stability = photo_width_stability_detail(
        detection.detail,
        policy.evidence.max_photo_width_cv_ratio,
        used_role="photo_width_gate",
    )
    photo_width_stability["max_photo_width_cv_ratio"] = policy.evidence.max_photo_width_cv_ratio
    photo_width_ok = bool(photo_width_stability.get("ok", True))
    content_support = str(content_detail.get("support", ""))
    content_containment_ok = bool(content_detail.get("content_containment_ok", False))
    content_harm_risk = bool(content_detail.get("content_harm_risk", True))
    content_quality_ok = content_quality_score >= policy.evidence.min_content_score
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
        and photo_width_within_limit(
            detection.detail,
            policy.evidence.geometry_supported_max_photo_width_cv_ratio,
            unavailable_ok=True,
        )
        and int(separator["equal_gaps"]) <= policy.evidence.max_equal_gap_count
        and content_containment_ok
        and not content_harm_risk
    )
    partial_supported_separator = (
        detection.strip_mode == "partial"
        and partial_edge_safe
        and int(separator["hard_gaps"]) >= 1
        and content_containment_ok
        and not content_harm_risk
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
    outer_area_ok = (
        policy.evidence.min_outer_area_ratio
        <= outer_area_ratio
        <= policy.evidence.max_outer_area_ratio
    )
    outer_alignment_ok = bool(outer_alignment.get("ok", True))
    safe_overcut_allowed = (
        not outer_area_ok
        and outer_area_ratio > policy.evidence.max_outer_area_ratio
        and bool(outer_alignment.get("used", False))
        and outer_alignment_ok
        and bool(outer_alignment.get("overcontainment_allowed", False))
        and content_containment_ok
        and not content_harm_risk
    )
    outer_ok = outer_alignment_ok and (outer_area_ok or safe_overcut_allowed)
    geometry_ok = (
        photo_width_ok
        and geometry_score >= policy.evidence.min_geometry_score
    )
    content_ok = (
        content_containment_ok
        and not content_harm_risk
    )
    return {
        "outer": {
            "ok": bool(outer_ok),
            "outer_area_ratio": outer_area_ratio,
            "min_outer_area_ratio": policy.evidence.min_outer_area_ratio,
            "max_outer_area_ratio": policy.evidence.max_outer_area_ratio,
            "area_ok": bool(outer_area_ok),
            "alignment_ok": bool(outer_alignment_ok),
            "safe_overcut_allowed": bool(safe_overcut_allowed),
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
            "width_cv_source": width_cv_source,
            "photo_width_stability": photo_width_stability,
            "max_photo_width_cv_ratio": policy.evidence.max_photo_width_cv_ratio,
            "geometry_score": geometry_score,
            "min_geometry_score": policy.evidence.min_geometry_score,
        },
        "content": {
            "ok": bool(content_ok),
            "support": content_support,
            "content_containment_ok": bool(content_containment_ok),
            "content_harm_risk": bool(content_harm_risk),
            "content_score": content_score,
            "content_score_role": assessment.get("content_score_role", "content_containment_support"),
            "content_quality_score": content_quality_score,
            "quality_ok": bool(content_quality_ok),
            "score_role": "quality_diagnostic_not_hard_gate",
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
    source = str(assessment.get("source") or detection.detail.get("candidate_source") or "")
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
        "content_only_evidence": source in {CANDIDATE_SOURCE_CONTENT, CANDIDATE_SOURCE_CONTENT_PRIMARY, "content"},
        "safety_or_review_only": (
            detection.detail.get("candidate_source") == CANDIDATE_SOURCE_HARD_SAFETY
            or detection.detail.get("candidate_source") == CANDIDATE_SOURCE_REVIEW_ONLY
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
    if risk["content_only_evidence"] or risk["safety_or_review_only"]:
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
    if bool(evidence["outer"]["ok"]):
        existing_reasons = [
            reason for reason in existing_reasons if reason != policy.decision.outer_content_mismatch_reason
        ]
    if bool(evidence["content"]["ok"]):
        existing_reasons = [
            reason for reason in existing_reasons if reason != policy.decision.content_only_evidence_reason
        ]
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
    return detection
