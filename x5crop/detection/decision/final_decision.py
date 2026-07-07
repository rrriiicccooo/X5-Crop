from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ...cache import AnalysisCache
from ...constants import (
    CANDIDATE_SOURCE_REVIEW_ONLY,
)
from ...domain import Detection
from ...formats import FormatSpec
from ...policies.runtime.policy import DetectionPolicy
from ...runtime.config import RuntimeConfig
from ..confidence_caps import apply_confidence_cap
from ..evidence.content.containment import content_containment_detail
from ..evidence.content.frame_support import content_evidence_detail
from ..evidence.outer_alignment import outer_content_alignment_detail
from ..evidence.risk import lucky_pass_risk_score_detail
from .pass_review import apply_final_decision_policy
from .reasons import normalized_review_reasons


@dataclass
class FinalDecisionResult:
    detection: Detection
    status: str
    content_detail: dict[str, Any]
    outer_alignment: dict[str, Any]


def apply_detection_decision(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    analysis_cache: AnalysisCache,
    deskew_detail: dict[str, Any],
    policy: DetectionPolicy,
) -> FinalDecisionResult:
    raw_content_detail = content_evidence_detail(gray, detection, analysis_cache, policy.content)
    content_detail = content_containment_detail(
        raw_content_detail,
        policy.content.evidence,
        expected_count=detection.count,
    )
    detection.detail["content_evidence"] = raw_content_detail
    detection.detail["content_containment"] = content_detail
    outer_alignment = (
        outer_content_alignment_detail(gray, detection, analysis_cache, policy=policy)
        if policy.decision.align_outer_to_content
        else {"used": False, "reason": policy.decision.outer_alignment_disabled_reason}
    )
    detection.detail["outer_content_alignment"] = outer_alignment
    _apply_decision_confidence_caps(
        gray,
        detection,
        config,
        policy,
        analysis_cache,
        content_detail,
        outer_alignment,
    )
    detection = apply_final_decision_policy(
        gray,
        detection,
        config,
        fmt,
        content_detail,
        outer_alignment,
    )
    _apply_low_confidence_context_reasons(detection, config, policy, deskew_detail)
    status = _decision_status_for(detection, config.confidence_threshold)
    _sync_decision_summary_status(detection, status)
    return FinalDecisionResult(
        detection=detection,
        status=status,
        content_detail=content_detail,
        outer_alignment=outer_alignment,
    )


def _apply_decision_confidence_caps(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    policy: DetectionPolicy,
    analysis_cache: AnalysisCache,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
) -> None:
    cap_details = detection.detail.setdefault("decision_confidence_caps", [])
    if not isinstance(cap_details, list):
        cap_details = []
        detection.detail["decision_confidence_caps"] = cap_details
    review_only_mode = detection.detail.get("candidate_source") == CANDIDATE_SOURCE_REVIEW_ONLY
    suppress_outer_mismatch = _suppress_outer_mismatch(detection)
    if not review_only_mode and bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            detection.confidence, cap_detail = apply_confidence_cap(
                detection.confidence,
                policy.decision.content_aspect_conflict_cap,
                owner="decision",
                reason="content_aspect_conflict",
            )
            cap_details.append(cap_detail)
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence, cap_detail = apply_confidence_cap(
                detection.confidence,
                policy.decision.content_low_confidence_cap,
                owner="decision",
                reason="content_low_confidence",
            )
            cap_details.append(cap_detail)
    if (
        not review_only_mode
        and not suppress_outer_mismatch
        and bool(outer_alignment.get("used", False))
        and not bool(outer_alignment.get("ok", True))
    ):
        detection.confidence, cap_detail = apply_confidence_cap(
            detection.confidence,
            policy.decision.outer_mismatch_cap,
            owner="decision",
            reason="outer_content_mismatch",
        )
        cap_details.append(cap_detail)
    lucky_pass_risk = lucky_pass_risk_score_detail(
        gray,
        detection,
        config.confidence_threshold,
        analysis_cache,
    )
    detection.detail["lucky_pass_risk_score"] = lucky_pass_risk
    if bool(lucky_pass_risk.get("risk", False)):
        detection.confidence, cap_detail = apply_confidence_cap(
            detection.confidence,
            policy.decision.lucky_pass_risk_cap,
            owner="decision",
            reason="lucky_pass_risk",
        )
        cap_details.append(cap_detail)


def _suppress_outer_mismatch(detection: Detection) -> bool:
    outer_correction_detail = detection.detail.get("outer_correction", {})
    return bool(
        isinstance(outer_correction_detail, dict)
        and outer_correction_detail.get("suppress_outer_mismatch", False)
    )


def _apply_low_confidence_context_reasons(
    detection: Detection,
    config: RuntimeConfig,
    policy: DetectionPolicy,
    deskew_detail: dict[str, Any],
) -> None:
    if detection.confidence < config.confidence_threshold:
        low_confidence_context_reasons: list[str] = []
        reason_inputs = detection.detail.setdefault("decision_reason_inputs", [])
        if not isinstance(reason_inputs, list):
            reason_inputs = []
            detection.detail["decision_reason_inputs"] = reason_inputs

        def append_context_reason(reason: str, signal: str) -> None:
            low_confidence_context_reasons.append(reason)
            detection.review_reasons.append(reason)
            reason_inputs.append(
                {
                    "bucket": "low_confidence_context",
                    "signal": signal,
                    "final_review_reason": reason,
                }
            )

        if float(detection.detail.get("outer_area_spread_ratio", 0.0)) >= 0.20:
            append_context_reason(
                policy.decision.outer_candidate_disagreement_review_reason,
                "outer_area_spread",
            )
        if deskew_detail.get("skipped") == "angle_out_of_range" or deskew_detail.get("reason"):
            append_context_reason(
                policy.decision.deskew_uncertain_review_reason,
                "deskew_uncertain",
            )
        detection.review_reasons = normalized_review_reasons(detection.review_reasons)
        detection.detail["final_review_reasons"] = list(detection.review_reasons)
        decision_summary = detection.detail.get("decision_summary", {})
        if isinstance(decision_summary, dict):
            added = decision_summary.get("final_review_reasons_added", [])
            if not isinstance(added, list):
                added = []
            decision_summary["final_review_reasons_added"] = normalized_review_reasons(
                [*added, *low_confidence_context_reasons]
            )
            decision_summary["final_review_reasons"] = list(detection.review_reasons)
            decision_summary["decision_reason_inputs"] = reason_inputs


def _decision_status_for(detection: Detection, confidence_threshold: float) -> str:
    if detection.confidence >= confidence_threshold and not detection.review_reasons:
        return "approved_auto"
    return "needs_review"


def _sync_decision_summary_status(detection: Detection, status: str) -> None:
    decision_summary = detection.detail.get("decision_summary")
    if isinstance(decision_summary, dict):
        decision_summary["status"] = status
        decision_summary["pass"] = status == "approved_auto"


__all__ = [
    "FinalDecisionResult",
    "apply_detection_decision",
]
