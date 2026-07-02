from __future__ import annotations

import numpy as np

from ...runtime_config import RuntimeConfig
from ...domain import Detection
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from .dual_lane_context import build_dual_lane_context
from .dual_lane_detect import detect_dual_lane
from .dual_lane_merge import merge_dual_lane_detections
from .dual_lane_split import split_dual_lanes
from .unsupported import unsupported_dual_lane_partial_detection


def choose_dual_lane_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> Detection:
    context = build_dual_lane_context(policy)
    if config.strip_mode != "full":
        return unsupported_dual_lane_partial_detection(gray, config, context)

    lanes = split_dual_lanes(cache.gray_work, context.lane_count)
    lane_detections = [
        detect_dual_lane(gray, config, lane, index, cache, context)
        for index, lane in enumerate(lanes, start=1)
    ]
    return merge_dual_lane_detections(gray, config, lanes, lane_detections, context)


__all__ = ["choose_dual_lane_detection"]
