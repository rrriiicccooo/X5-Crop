from __future__ import annotations

from typing import Optional

import numpy as np

from ...domain import Detection
from ...formats import FormatSpec
from ...geometry.boxes import original_box_to_work
from ...policies.runtime_policy import DetectionPolicy


def separator_full_width_can_compete(
    detection: Detection,
    gray: np.ndarray,
    policy: DetectionPolicy,
) -> bool:
    competition = policy.candidate_run.separator_full_width_competition
    if not competition.enabled:
        return False
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
        outer_candidate_strategy in competition.content_outer_max_median_aspect_strategies
        and detection.strip_mode in competition.content_outer_max_median_aspect_strip_modes
    ):
        return median_aspect <= competition.content_outer_max_median_aspect
    return median_aspect >= competition.general_min_median_aspect


def fallback_outer_proposals_enabled(policy: DetectionPolicy) -> bool:
    fallback = policy.candidate_run.fallback
    if not fallback.use_outer_proposals:
        return False
    strategies = set(fallback.strategies)
    return bool(
        (policy.outer.separator_local == "fallback" and "separator_outer" in strategies)
        or (policy.outer.edge_anchor == "fallback" and "edge_anchor_outer" in strategies)
        or (policy.outer.separator_full_width == "fallback" and "separator_outer" in strategies)
    )


def should_try_equal_first_before_wide_retry(
    policy: DetectionPolicy,
    strip_mode: str,
    count: int,
    fmt: FormatSpec,
) -> bool:
    retry_policy = policy.candidate_run.equal_first_before_wide_retry
    if not retry_policy.enabled:
        return False
    if retry_policy.requires_wide_geometry_support and not policy.separator.geometry_support.wide_geometry.enabled:
        return False
    if strip_mode not in retry_policy.strip_modes:
        return False
    if retry_policy.requires_default_count and count != fmt.default_count:
        return False
    return True


def separator_outer_gap_max_width_override(
    policy: DetectionPolicy,
    current_override: Optional[float] = None,
) -> Optional[float]:
    if current_override is not None:
        return current_override
    override = policy.outer.separator_gap_search_max_width_ratio
    if override > policy.separator.gap_search.max_width_ratio:
        return override
    return None
