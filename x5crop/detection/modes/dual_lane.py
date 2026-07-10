from __future__ import annotations

import numpy as np

from ...run_config import RunConfig
from ...domain import DetectionCandidate
from ...policies.runtime.bundle import DetectionPolicyBundle
from ...policies.runtime.policy import DetectionPolicy
from ...cache import AnalysisCache
from .dual_lane_context import build_dual_lane_context
from .dual_lane_candidate import select_dual_lane_candidate
from .dual_lane_merge import merge_dual_lane_detections
from .dual_lane_split import split_dual_lanes


def choose_dual_lane_detection(
    gray: np.ndarray,
    config: RunConfig,
    cache: AnalysisCache,
    policy: DetectionPolicy,
    policy_bundle: DetectionPolicyBundle,
) -> DetectionCandidate:
    context = build_dual_lane_context(policy, policy_bundle)
    if config.strip_mode != "full":
        raise ValueError("dual-lane detector is only valid for full mode")

    lanes = split_dual_lanes(cache.gray_work, context.lane_count)
    lane_detections = [
        select_dual_lane_candidate(
            gray,
            config,
            lane,
            index,
            cache,
            context.lane_format_id,
            context.lane_format_spec,
            context.lane_policy,
        )
        for index, lane in enumerate(lanes, start=1)
    ]
    return merge_dual_lane_detections(gray, config, lanes, lane_detections, context)


__all__ = ["choose_dual_lane_detection"]
