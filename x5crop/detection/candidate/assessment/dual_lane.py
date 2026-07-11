from __future__ import annotations

import numpy as np

from ....cache import AnalysisCache
from ....domain import DetectionCandidate
from ....policies.runtime.policy import DetectionPolicy
from ...evidence.content.frame_support import content_evidence_detail
from ...evidence.outer_alignment import outer_content_alignment_detail


def apply_dual_lane_content_assessment(
    gray: np.ndarray,
    detection: DetectionCandidate,
    cache: AnalysisCache,
    lane_policy: DetectionPolicy,
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

    diagnostics: list[str] = []
    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            diagnostics.append("content_aspect_uncertain")
        elif support in {"low_content", "weak"}:
            diagnostics.append("content_quality_low")
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        diagnostics.append("outer_alignment_measurement_conflict")
    assessment = detection.detail.get("candidate_assessment")
    if isinstance(assessment, dict):
        assessment["diagnostics"] = sorted(
            set([*assessment.get("diagnostics", []), *diagnostics])
        )
