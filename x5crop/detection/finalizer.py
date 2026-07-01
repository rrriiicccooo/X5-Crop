from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import RuntimeConfig
from ..domain import Detection
from ..formats import FormatSpec
from .final_geometry import (
    apply_approved_geometry_adjustment,
    apply_edge_bleed_protection,
    apply_output_bleed,
    detection_geometry_config,
    detection_has_overlap_bleed_risk,
    output_bleed_config_for_detection,
)
from ..policies.registry import get_detection_policy
from ..runtime import AnalysisCache
from .diagnostics import (
    attach_read_only_diagnostics,
    lucky_pass_risk_score_detail,
    overlap_bleed_risk_detail,
)
from .final_decision import apply_final_decision_policy, normalized_review_reasons
from .content import content_evidence_detail
from .outer_retry import (
    outer_content_alignment_detail,
    retry_with_outer_correction_proposals,
)
from ..constants import (
    ANALYSIS_SOURCE_HARD_FALLBACK,
    ANALYSIS_SOURCE_UNSUPPORTED,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_LUCKY_PASS_RISK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
)


@dataclass
class DetectionFinalizationResult:
    detection: Detection
    status: str
    output_config: RuntimeConfig
    content_detail: dict[str, Any]
    outer_alignment: dict[str, Any]


def finalize_detection(
    gray: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    analysis_cache: AnalysisCache,
    deskew_detail: dict[str, Any],
) -> DetectionFinalizationResult:
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    detection_config = detection_geometry_config(config, policy.output)
    content_detail = content_evidence_detail(gray, detection, analysis_cache, policy.content)
    detection.detail["content_evidence"] = content_detail
    outer_alignment = (
        outer_content_alignment_detail(gray, detection, analysis_cache, policy=policy)
        if policy.finalization.align_outer_to_content
        else {"used": False, "reason": policy.finalization.outer_alignment_disabled_reason}
    )
    detection.detail["outer_content_alignment"] = outer_alignment
    unsupported_mode = detection.detail.get("analysis_source") == ANALYSIS_SOURCE_UNSUPPORTED

    allow_outer_retry = (
        detection.detail.get("analysis_source") != ANALYSIS_SOURCE_HARD_FALLBACK
        and bool(policy.finalization.retry_uncertain_outer)
    )
    suppress_outer_mismatch = False
    if allow_outer_retry and not unsupported_mode:
        detection, content_detail, outer_alignment, suppress_outer_mismatch = retry_with_outer_correction_proposals(
            gray,
            detection_config,
            fmt,
            detection,
            content_detail,
            outer_alignment,
            analysis_cache,
        )

    if not unsupported_mode and bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            detection.confidence = min(detection.confidence, policy.finalization.content_aspect_conflict_cap)
            detection.review_reasons.append(REASON_CONTENT_ASPECT_CONFLICT)
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence = min(detection.confidence, policy.finalization.content_low_confidence_cap)
            detection.review_reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    if not unsupported_mode and not suppress_outer_mismatch and bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        detection.confidence = min(detection.confidence, policy.finalization.outer_mismatch_cap)
        detection.review_reasons.append(REASON_OUTER_CONTENT_BBOX_MISMATCH)
    lucky_pass_risk = lucky_pass_risk_score_detail(gray, detection, config.confidence_threshold, analysis_cache)
    detection.detail["lucky_pass_risk_score"] = lucky_pass_risk
    if bool(lucky_pass_risk.get("risk", False)):
        detection.confidence = min(detection.confidence, policy.finalization.lucky_pass_risk_cap)
        detection.review_reasons.append(REASON_LUCKY_PASS_RISK)

    detection = apply_final_decision_policy(
        gray,
        detection,
        config,
        fmt,
        content_detail,
        outer_alignment,
    )

    if detection.confidence < config.confidence_threshold:
        if detection.detail.get("partial_best"):
            detection.review_reasons.append(policy.finalization.likely_partial_review_reason)
        if float(detection.detail.get("outer_area_spread_ratio", 0.0)) >= 0.20:
            detection.review_reasons.append(policy.finalization.outer_candidate_disagreement_review_reason)
        if deskew_detail.get("skipped") == "angle_out_of_range" or deskew_detail.get("reason"):
            detection.review_reasons.append(policy.finalization.deskew_uncertain_review_reason)
        detection.review_reasons = normalized_review_reasons(detection.review_reasons)
    status = "approved_auto" if detection.confidence >= config.confidence_threshold else "needs_review"
    if policy.finalization.apply_approved_geometry_adjustment:
        apply_approved_geometry_adjustment(
            detection,
            gray,
            config,
            status,
            policy.finalization.approved_geometry_adjustment,
        )
    if policy.diagnostics.overlap_bleed_risk.enabled and not detection_has_overlap_bleed_risk(detection):
        detection.detail["overlap_bleed_risk"] = overlap_bleed_risk_detail(gray, detection, analysis_cache)
    output_config = output_bleed_config_for_detection(config, detection, policy.output)
    if policy.finalization.apply_output_bleed:
        apply_output_bleed(detection, detection_config, output_config, gray.shape[1], gray.shape[0])
        apply_edge_bleed_protection(
            detection,
            output_config,
            gray.shape[1],
            gray.shape[0],
            policy.output.edge_bleed_protection,
        )
    if not policy.diagnostics.attach_read_only_when_requested or config.diagnostics:
        attach_read_only_diagnostics(gray, detection, analysis_cache)
    return DetectionFinalizationResult(
        detection=detection,
        status=status,
        output_config=output_config,
        content_detail=content_detail,
        outer_alignment=outer_alignment,
    )
