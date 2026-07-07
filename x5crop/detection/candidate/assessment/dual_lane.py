from __future__ import annotations

import numpy as np

from ....cache import AnalysisCache
from ....constants import (
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
)
from ....domain import Detection
from ....policies.runtime.policy import DetectionPolicy
from ...confidence_caps import apply_confidence_cap
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.outer_alignment import outer_content_alignment_detail


def _apply_dual_lane_candidate_cap(
    detection: Detection,
    cap: float,
    reason: str,
) -> None:
    detection.confidence, cap_detail = apply_confidence_cap(
        detection.confidence,
        cap,
        owner="candidate.assessment",
        reason=reason,
    )
    confidence_caps = detection.detail.setdefault("candidate_confidence_caps", [])
    if not isinstance(confidence_caps, list):
        confidence_caps = []
        detection.detail["candidate_confidence_caps"] = confidence_caps
    confidence_caps.append(cap_detail)


def apply_dual_lane_content_assessment(
    gray: np.ndarray,
    detection: Detection,
    cache: AnalysisCache,
    lane_policy: DetectionPolicy,
    confidence_threshold: float,
) -> None:
    content_detail = content_evidence_detail(gray, detection, cache, lane_policy.content)
    outer_alignment = outer_content_alignment_detail(gray, detection, cache, policy=lane_policy)
    detection.detail["content_evidence"] = content_detail
    detection.detail["outer_content_alignment"] = outer_alignment

    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            _apply_dual_lane_candidate_cap(detection, 0.82, REASON_CONTENT_ASPECT_CONFLICT)
            detection.review_reasons.append(REASON_CONTENT_ASPECT_CONFLICT)
        elif support in {"low_content", "weak"} and detection.confidence >= confidence_threshold:
            _apply_dual_lane_candidate_cap(detection, 0.84, REASON_CONTENT_EVIDENCE_WEAK)
            detection.review_reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        _apply_dual_lane_candidate_cap(detection, 0.84, REASON_OUTER_CONTENT_BBOX_MISMATCH)
        detection.review_reasons.append(REASON_OUTER_CONTENT_BBOX_MISMATCH)

    detection.review_reasons = sorted(set(detection.review_reasons))


__all__ = ["apply_dual_lane_content_assessment"]
