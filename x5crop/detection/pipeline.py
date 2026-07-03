from __future__ import annotations

from typing import Optional

import numpy as np

from ..runtime_config import RuntimeConfig
from ..domain import Detection
from ..formats import FormatSpec
from ..analysis_cache import make_analysis_cache
from ..policies.registry import get_detection_policy
from ..runtime import AnalysisCache
from .candidate.run import calibrated_candidates_for_count
from .candidate.counts import candidate_counts_for_format
from .modes.dual_lane import choose_dual_lane_detection
from .modes.review_only import review_only_detection
from .candidate.safety_candidate import hard_safety_detection
from .candidate.selection import select_detection_candidate


def choose_detection(gray: np.ndarray, config: RuntimeConfig, fmt: FormatSpec, cache: Optional[AnalysisCache] = None) -> Detection:
    candidates: list[Detection] = []
    cache = cache if cache is not None and cache.layout == config.layout else make_analysis_cache(gray, config.layout)
    policy = get_detection_policy(fmt.name, config.strip_mode)
    if policy.detector.kind == "dual_lane":
        detection = choose_dual_lane_detection(gray, config, cache, policy)
        detection.detail["policy"] = policy.report_detail()
        return detection
    if policy.detector.kind == "review_only":
        detection = review_only_detection(gray, config, fmt, policy)
        detection.detail["policy"] = policy.report_detail()
        return detection
    count_specs = candidate_counts_for_format(config, fmt, policy)
    for count, strip_mode, offsets in count_specs:
        if count not in fmt.allowed_counts:
            continue
        stop_after_this_count = False
        for offset in offsets:
            count_candidates, should_stop = calibrated_candidates_for_count(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                offset,
                cache,
                policy,
            )
            candidates.extend(count_candidates)
            stop_after_this_count = stop_after_this_count or should_stop
        if strip_mode == "partial" and stop_after_this_count and config.count_override is None:
            break

    if not candidates:
        detection = hard_safety_detection(gray, config, fmt)
        detection.detail["policy"] = policy.report_detail()
        return detection

    detection = select_detection_candidate(candidates, fmt, config.confidence_threshold, policy)
    detection.detail["policy"] = policy.report_detail()
    return detection
