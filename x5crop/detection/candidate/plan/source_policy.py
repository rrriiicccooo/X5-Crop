from __future__ import annotations

from typing import Optional

import numpy as np

from ....domain import DetectionCandidate
from ....geometry.boxes import original_box_to_work
from ....policies.runtime.policy import DetectionPolicy


def separator_full_width_can_compete(
    detection: DetectionCandidate,
    gray: np.ndarray,
    policy: DetectionPolicy,
) -> bool:
    competition = policy.candidate_plan.separator_full_width_competition
    outer_candidate_strategy = str(detection.detail.get("outer_candidate_strategy", ""))
    frames = [original_box_to_work(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in detection.frames]
    aspects = [
        frame.width / max(1.0, float(frame.height))
        for frame in frames
        if frame.valid() and frame.height > 0
    ]
    if not aspects:
        return False
    median_aspect = float(np.median(np.array(aspects, dtype=np.float32)))
    if (
        outer_candidate_strategy == "content_outer"
        and detection.strip_mode == "partial"
    ):
        return median_aspect <= competition.content_outer_max_median_aspect
    return median_aspect >= competition.general_min_median_aspect


def safety_candidate_outer_proposals_enabled(policy: DetectionPolicy) -> bool:
    separator_policy = policy.outer.proposal.geometry.separator
    return bool(
        separator_policy.local.mode == "safety"
        or separator_policy.full_width.mode == "safety"
    )


def separator_outer_gap_max_width_override(
    policy: DetectionPolicy,
    current_override: Optional[float] = None,
) -> Optional[float]:
    if current_override is not None:
        return current_override
    override = policy.outer.proposal.geometry.separator.separator_gap_search_max_width_ratio
    if override > policy.separator.gap_search.max_width_ratio:
        return override
    return None
