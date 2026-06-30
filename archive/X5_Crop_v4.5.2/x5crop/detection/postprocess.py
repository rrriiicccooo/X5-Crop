from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..common import AnalysisCache, Config, Detection, FilmFormat
from ..geometry import (
    apply_approved_geometry_polish,
    apply_edge_bleed_protection,
    apply_output_bleed,
    detection_geometry_config,
    detection_has_overlap_bleed_risk,
    output_bleed_config_for_detection,
)
from .diagnostics import (
    attach_read_only_diagnostics,
    lucky_pass_risk_score_detail,
    overlap_bleed_risk_detail,
)
from ..constants import (
    ANALYSIS_SOURCE_HARD_FALLBACK,
    ANALYSIS_SOURCE_UNSUPPORTED,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_LUCKY_PASS_RISK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
)
from .pipeline import (
    content_evidence_detail,
    outer_content_alignment_detail,
    retry_with_outer_correction_proposals,
)


@dataclass
class PostprocessResult:
    detection: Detection
    status: str
    output_config: Config
    content_detail: dict[str, Any]
    outer_alignment: dict[str, Any]


def finalize_detection_decision(
    gray: np.ndarray,
    detection: Detection,
    config: Config,
    fmt: FilmFormat,
    tuning: Any,
    analysis_cache: AnalysisCache,
    deskew_detail: dict[str, Any],
) -> PostprocessResult:
    detection_config = detection_geometry_config(config)
    content_detail = content_evidence_detail(gray, detection, analysis_cache)
    detection.detail["content_evidence"] = content_detail
    outer_alignment = outer_content_alignment_detail(gray, detection, analysis_cache)
    detection.detail["outer_content_alignment"] = outer_alignment
    unsupported_mode = detection.detail.get("analysis_source") == ANALYSIS_SOURCE_UNSUPPORTED

    allow_outer_retry = detection.detail.get("analysis_source") != ANALYSIS_SOURCE_HARD_FALLBACK and tuning.outer_retry_enabled
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
            detection.confidence = min(detection.confidence, tuning.post_content_aspect_conflict_cap)
            detection.review_reasons.append(REASON_CONTENT_ASPECT_CONFLICT)
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence = min(detection.confidence, tuning.post_content_low_confidence_cap)
            detection.review_reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    if not unsupported_mode and not suppress_outer_mismatch and bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        detection.confidence = min(detection.confidence, tuning.post_outer_mismatch_cap)
        detection.review_reasons.append(REASON_OUTER_CONTENT_BBOX_MISMATCH)
    lucky_pass_risk = lucky_pass_risk_score_detail(gray, detection, config.confidence_threshold, analysis_cache)
    detection.detail["lucky_pass_risk_score"] = lucky_pass_risk
    if bool(lucky_pass_risk.get("risk", False)):
        detection.confidence = min(detection.confidence, tuning.post_lucky_pass_risk_cap)
        detection.review_reasons.append(REASON_LUCKY_PASS_RISK)

    if detection.confidence < config.confidence_threshold:
        if detection.detail.get("partial_best"):
            detection.review_reasons.append("likely_partial_strip")
        if float(detection.detail.get("outer_area_spread_ratio", 0.0)) >= 0.20:
            detection.review_reasons.append("outer_candidate_disagreement")
        if deskew_detail.get("skipped") == "angle_out_of_range" or deskew_detail.get("reason"):
            detection.review_reasons.append("deskew_uncertain")
        detection.review_reasons = sorted(set(detection.review_reasons))
    status = "approved_auto" if detection.confidence >= config.confidence_threshold else "needs_review"
    apply_approved_geometry_polish(detection, gray, config, status)
    diagnostic_overlap_bleed_enabled = (
        config.strip_mode == "partial"
        or fmt.name == "half"
        or fmt.family == "120"
    )
    if diagnostic_overlap_bleed_enabled and not detection_has_overlap_bleed_risk(detection):
        detection.detail["overlap_bleed_risk"] = overlap_bleed_risk_detail(gray, detection, analysis_cache)
    output_config = output_bleed_config_for_detection(config, detection)
    apply_output_bleed(detection, detection_config, output_config, gray.shape[1], gray.shape[0])
    apply_edge_bleed_protection(detection, output_config, gray.shape[1], gray.shape[0])
    if config.diagnostics:
        attach_read_only_diagnostics(gray, detection, analysis_cache)
    return PostprocessResult(
        detection=detection,
        status=status,
        output_config=output_config,
        content_detail=content_detail,
        outer_alignment=outer_alignment,
    )
