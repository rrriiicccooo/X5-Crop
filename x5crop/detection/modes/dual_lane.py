from __future__ import annotations

import numpy as np

from ...runtime_config import RuntimeConfig
from ...domain import Detection
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from .parallel_lane_detect import detect_parallel_strip_lane
from .parallel_lane_merge import merge_parallel_lane_detections
from .parallel_lane_split import split_parallel_strip_lanes
from .unsupported import unsupported_parallel_lane_partial_detection


def choose_parallel_lane_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> Detection:
    if config.strip_mode != "full":
        return unsupported_parallel_lane_partial_detection(gray, config)

    lanes = split_parallel_strip_lanes(cache.gray_work, policy.detector.dual_lane.lane_count)
    lane_detections = [
        detect_parallel_strip_lane(gray, config, lane, index, cache, policy)
        for index, lane in enumerate(lanes, start=1)
    ]
    return merge_parallel_lane_detections(gray, config, lanes, lane_detections, policy)


__all__ = ["choose_parallel_lane_detection"]
