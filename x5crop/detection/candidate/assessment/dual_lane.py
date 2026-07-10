from __future__ import annotations

import numpy as np

from ....cache import AnalysisCache
from ....domain import DetectionCandidate
from ....policies.runtime.policy import DetectionPolicy
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.outer_alignment import outer_content_alignment_detail
from ..signals import (
    SIGNAL_CONTENT_ASPECT_CONFLICT,
    SIGNAL_CONTENT_EVIDENCE_WEAK,
    SIGNAL_CONTENT_OUTSIDE_OUTER,
    add_candidate_signals,
)
from .confidence_caps import apply_candidate_confidence_cap


def apply_dual_lane_content_assessment(
    gray: np.ndarray,
    detection: DetectionCandidate,
    cache: AnalysisCache,
    lane_policy: DetectionPolicy,
    confidence_threshold: float,
    horizontal_frame_aspect: float,
) -> None:
    content_detail = content_evidence_detail(
        gray,
        detection,
        cache,
        content_policy=lane_policy.content,
        horizontal_frame_aspect=horizontal_frame_aspect,
    )
    outer_alignment = outer_content_alignment_detail(
        gray,
        detection,
        cache,
        alignment_policy=lane_policy.outer.alignment_evidence,
    )
    detection.detail["content_evidence"] = content_detail
    detection.detail["outer_content_alignment"] = outer_alignment

    candidate_signals: list[str] = []
    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            apply_candidate_confidence_cap(
                detection,
                lane_policy.decision.content_aspect_conflict_cap,
                SIGNAL_CONTENT_ASPECT_CONFLICT,
            )
            candidate_signals.append(SIGNAL_CONTENT_ASPECT_CONFLICT)
        elif support in {"low_content", "weak"} and detection.confidence >= confidence_threshold:
            apply_candidate_confidence_cap(
                detection,
                lane_policy.decision.content_low_confidence_cap,
                SIGNAL_CONTENT_EVIDENCE_WEAK,
            )
            candidate_signals.append(SIGNAL_CONTENT_EVIDENCE_WEAK)
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        apply_candidate_confidence_cap(
            detection,
            lane_policy.decision.outer_mismatch_cap,
            SIGNAL_CONTENT_OUTSIDE_OUTER,
        )
        candidate_signals.append(SIGNAL_CONTENT_OUTSIDE_OUTER)

    add_candidate_signals(detection, candidate_signals)
