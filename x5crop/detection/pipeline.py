from __future__ import annotations

from typing import Optional

import numpy as np

from ..runtime.config import RuntimeConfig
from ..domain import Detection
from ..formats import FormatSpec
from ..cache.analysis import make_analysis_cache
from ..policies.registry import get_detection_policy
from ..cache import AnalysisCache
from .candidate.plan.run import calibrated_candidates_for_count
from .candidate.plan.counts import candidate_counts_for_format
from .modes.dual_lane import choose_dual_lane_detection
from .modes.review_only import review_only_detection
from .candidate.proposal.safety import hard_safety_detection
from .candidate.selection.choose import select_detection_candidate
from .candidate.extension.outer_correction import outer_correction_candidate_extensions


def _attach_runtime_policy_detail(detection: Detection, policy) -> None:
    detection.detail["runtime_policy_detail"] = policy.report_detail()


def choose_detection(gray: np.ndarray, config: RuntimeConfig, fmt: FormatSpec, cache: Optional[AnalysisCache] = None) -> Detection:
    candidates: list[Detection] = []
    cache = cache if cache is not None and cache.layout == config.layout else make_analysis_cache(gray, config.layout)
    policy = get_detection_policy(fmt.name, config.strip_mode)
    if policy.detector.kind == "dual_lane":
        detection = choose_dual_lane_detection(gray, config, cache, policy)
        _attach_runtime_policy_detail(detection, policy)
        return detection
    if policy.detector.kind == "review_only":
        detection = review_only_detection(gray, config, fmt, policy)
        _attach_runtime_policy_detail(detection, policy)
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
        _attach_runtime_policy_detail(detection, policy)
        return detection

    provisional = select_detection_candidate(candidates, fmt, config.confidence_threshold, policy)
    extension_policy = get_detection_policy(provisional.film_format, provisional.strip_mode)
    extension_candidates = outer_correction_candidate_extensions(
        gray,
        config,
        fmt,
        provisional,
        cache,
        extension_policy,
    )
    if extension_candidates:
        candidates.extend(extension_candidates)
    detection = select_detection_candidate(candidates, fmt, config.confidence_threshold, extension_policy)
    selected_policy = get_detection_policy(detection.film_format, detection.strip_mode)
    _attach_runtime_policy_detail(detection, selected_policy)
    return detection
