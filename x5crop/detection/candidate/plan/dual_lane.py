from __future__ import annotations

from dataclasses import asdict, replace
from typing import Optional

import numpy as np

from ....cache import AnalysisCache
from ....domain import Box, Detection
from ....formats import FormatSpec
from ....geometry.boxes import translate_box
from ....policies.runtime.policy import DetectionPolicy
from ....runtime.config import RuntimeConfig
from ...physical.outer.base import base_outer_candidates
from ..assessment.candidate import apply_candidate_assessment_policy
from ..assessment.dual_lane import apply_dual_lane_content_assessment
from ..build.detection import build_detection_for_outer
from ..selection.choose import calibrated_candidate_rank


def select_dual_lane_candidate(
    gray: np.ndarray,
    config: RuntimeConfig,
    lane: Box,
    lane_index: int,
    cache: AnalysisCache,
    lane_format_id: str,
    lane_format_spec: FormatSpec,
    lane_policy: DetectionPolicy,
) -> Optional[Detection]:
    lane_crop = cache.gray_work[lane.top:lane.bottom, lane.left:lane.right]
    if lane_crop.size == 0:
        return None

    lane_config = replace(
        config,
        film_format=lane_format_id,
        count=lane_format_spec.default_count,
        count_override=lane_format_spec.default_count,
    )

    candidates = [
        _assessed_lane_candidate(
            gray,
            lane_config,
            lane,
            lane_index,
            cache,
            lane_format_spec,
            lane_policy,
            outer_candidate,
        )
        for outer_candidate in base_outer_candidates(
            lane_crop,
            lane_policy.outer.proposal.base.candidates,
        )
    ]
    if not candidates:
        return None

    best = max(candidates, key=lambda d: calibrated_candidate_rank(d, config.confidence_threshold))
    apply_dual_lane_content_assessment(gray, best, cache, lane_policy, config.confidence_threshold)
    return best


def _assessed_lane_candidate(
    gray: np.ndarray,
    lane_config: RuntimeConfig,
    lane: Box,
    lane_index: int,
    cache: AnalysisCache,
    lane_format_spec: FormatSpec,
    lane_policy: DetectionPolicy,
    outer_candidate,
) -> Detection:
    lane_outer = translate_box(outer_candidate.box, lane.left, lane.top)
    raw = build_detection_for_outer(
        gray,
        lane_config,
        lane_format_spec,
        lane_format_spec.default_count,
        "full",
        lane_outer,
        0.0,
        f"dual_lane_{lane_index}_{outer_candidate.name}",
        outer_candidate.strategy,
        outer_candidate_detail={
            **outer_candidate.detail,
            "dual_lane_index": int(lane_index),
            "lane_box": asdict(lane),
        },
        cache=cache,
        policy=lane_policy,
    )
    assessed = apply_candidate_assessment_policy(
        gray,
        raw,
        lane_config,
        lane_format_spec,
        "separator",
        cache,
        policy=lane_policy,
    )
    assessed.detail["dual_lane_index"] = lane_index
    assessed.detail["dual_lane_work_box"] = asdict(lane)
    return assessed


__all__ = ["select_dual_lane_candidate"]
