from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..runtime.config import RuntimeConfig
from ..domain import Detection
from ..formats import FormatSpec
from ..cache.analysis import make_analysis_cache
from ..runtime.policy_context import RuntimePolicyContext
from ..policies.runtime.policy import DetectionPolicy
from ..cache import AnalysisCache
from .candidate.lifecycle import calibrated_candidates_for_count
from .candidate.plan.counts import candidate_counts_for_format
from .modes.dual_lane import choose_dual_lane_detection
from .modes.review_only import review_only_detection
from .candidate.proposal.safety import hard_safety_detection
from .candidate.selection.choose import select_detection_candidate
from .candidate.extension.outer_correction import outer_correction_candidate_extensions


@dataclass(frozen=True)
class DetectionPipelineResult:
    detection: Detection
    policy: DetectionPolicy


def _attach_runtime_policy_detail(detection: Detection, policy) -> None:
    detection.detail["runtime_policy_detail"] = policy.report_detail()


def choose_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    policy_context: RuntimePolicyContext,
    cache: Optional[AnalysisCache] = None,
) -> DetectionPipelineResult:
    candidates: list[Detection] = []
    policy = policy_context.policy_for(fmt.name, config.strip_mode)
    cache = (
        cache
        if cache is not None and cache.layout == config.layout
        else make_analysis_cache(gray, config.layout, policy.preprocess.content_evidence_image)
    )
    if policy.detector.kind == "dual_lane":
        detection = choose_dual_lane_detection(gray, config, cache, policy, policy_context)
        _attach_runtime_policy_detail(detection, policy)
        return DetectionPipelineResult(detection, policy)
    if policy.detector.kind == "review_only":
        detection = review_only_detection(gray, config, fmt, policy)
        _attach_runtime_policy_detail(detection, policy)
        return DetectionPipelineResult(detection, policy)
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
        return DetectionPipelineResult(detection, policy)

    provisional = select_detection_candidate(candidates, fmt, config.confidence_threshold, policy, policy_context)
    extension_policy = policy_context.policy_for(provisional.film_format, provisional.strip_mode)
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
    detection = select_detection_candidate(candidates, fmt, config.confidence_threshold, extension_policy, policy_context)
    selected_policy = policy_context.policy_for(detection.film_format, detection.strip_mode)
    _attach_runtime_policy_detail(detection, selected_policy)
    return DetectionPipelineResult(detection, selected_policy)
