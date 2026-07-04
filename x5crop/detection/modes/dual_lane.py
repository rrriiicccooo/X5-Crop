from __future__ import annotations

import numpy as np

from ...runtime.config import RuntimeConfig
from ...domain import Detection
from ...policies.runtime.policy import DetectionPolicy
from ...cache import AnalysisCache
from .dual_lane_context import build_dual_lane_context
from .dual_lane_detect import detect_dual_lane
from .dual_lane_merge import merge_dual_lane_detections
from .dual_lane_split import split_dual_lanes


def choose_dual_lane_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> Detection:
    context = build_dual_lane_context(policy)
    if config.strip_mode != "full":
        raise ValueError("dual-lane detector is only valid for full mode")

    lanes = split_dual_lanes(cache.gray_work, context.lane_count)
    lane_detections = [
        detect_dual_lane(gray, config, lane, index, cache, context)
        for index, lane in enumerate(lanes, start=1)
    ]
    return merge_dual_lane_detections(gray, config, lanes, lane_detections, context)


__all__ = ["choose_dual_lane_detection"]
