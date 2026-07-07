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
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.outer_alignment import outer_content_alignment_detail
from ..reasons import add_candidate_reasons
from .confidence_caps import apply_candidate_confidence_cap


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

    candidate_blockers: list[str] = []
    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            apply_candidate_confidence_cap(detection, 0.82, REASON_CONTENT_ASPECT_CONFLICT)
            candidate_blockers.append(REASON_CONTENT_ASPECT_CONFLICT)
        elif support in {"low_content", "weak"} and detection.confidence >= confidence_threshold:
            apply_candidate_confidence_cap(detection, 0.84, REASON_CONTENT_EVIDENCE_WEAK)
            candidate_blockers.append(REASON_CONTENT_EVIDENCE_WEAK)
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        apply_candidate_confidence_cap(detection, 0.84, REASON_OUTER_CONTENT_BBOX_MISMATCH)
        candidate_blockers.append(REASON_OUTER_CONTENT_BBOX_MISMATCH)

    add_candidate_reasons(detection, candidate_blockers)


__all__ = ["apply_dual_lane_content_assessment"]
