from __future__ import annotations

from typing import Optional

import numpy as np

from ...runtime_config import RuntimeConfig
from ...domain import Detection
from ...formats import FormatSpec
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from .content_candidate import content_detection_for_count
from .candidate_assessment import apply_candidate_assessment_policy
from .selection import is_partial_safe_auto_candidate
from .source_policy import fallback_outer_proposals_enabled, should_try_equal_first_before_wide_retry
from .sources import detect_candidate_for_count, detect_fallback_outer_proposal_candidate_for_count


def calibrated_candidates_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset: float,
    cache: AnalysisCache,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[list[Detection], bool]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    content_policy = policy.candidate_run.content_candidate
    candidates: list[Detection] = []
    stop_after_this_count = False
    wide_retry_allowed = bool(policy.separator.wide_retry)
    wide_retry_max_width_ratio = policy.separator.wide_retry_max_width_ratio
    wide_retry_has_room = wide_retry_max_width_ratio > policy.separator.gap_search.max_width_ratio
    equal_first_before_wide_retry = (
        should_try_equal_first_before_wide_retry(policy, strip_mode, count, fmt)
        and wide_retry_allowed
        and wide_retry_has_room
    )
    separator = detect_candidate_for_count(gray, config, fmt, count, strip_mode, offset, cache, policy=policy)
    separator_candidate = apply_candidate_assessment_policy(gray, separator, config, fmt, "separator", cache, policy=policy)
    candidates.append(separator_candidate)
    separator_gate_candidate = separator_candidate
    separator_auto_gate = bool(
        separator_candidate.detail.get("candidate_assessment", {}).get("auto_gate", False)
    )
    if (
        not separator_auto_gate
        and wide_retry_allowed
        and wide_retry_has_room
    ):
        wide_separator = detect_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            gap_max_width_ratio_override=wide_retry_max_width_ratio,
            policy=policy,
        )
        wide_candidate = apply_candidate_assessment_policy(gray, wide_separator, config, fmt, "separator", cache, policy=policy)
        wide_candidate.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
            "retry_gap_max_width_ratio": float(wide_retry_max_width_ratio),
        }
        if equal_first_before_wide_retry:
            wide_candidate.detail["wide_gap_retry"]["equal_first_before_wide_retry"] = True
        candidates.append(wide_candidate)
        if bool(wide_candidate.detail.get("candidate_assessment", {}).get("auto_gate", False)):
            separator_auto_gate = True
            separator_gate_candidate = wide_candidate
    if (
        not separator_auto_gate
        and fallback_outer_proposals_enabled(policy)
    ):
        fallback_proposal = detect_fallback_outer_proposal_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            policy=policy,
        )
        if fallback_proposal is not None:
            fallback_candidate = apply_candidate_assessment_policy(gray, fallback_proposal, config, fmt, "separator", cache, policy=policy)
            fallback_candidate.detail["outer_proposal_fallback_retry"] = {
                "used": True,
                "separator_local_mode": policy.outer.proposal.geometry.separator.local,
                "separator_full_width_mode": policy.outer.proposal.geometry.separator.full_width,
                "strategies": list(policy.candidate_run.fallback.strategies),
            }
            candidates.append(fallback_candidate)
            fallback_auto_gate = bool(
                fallback_candidate.detail.get("candidate_assessment", {}).get("auto_gate", False)
            )
            if fallback_auto_gate:
                separator_auto_gate = True
                separator_gate_candidate = fallback_candidate
    partial_safe_auto = is_partial_safe_auto_candidate(separator_gate_candidate, config.confidence_threshold)
    if partial_safe_auto and policy.candidate_run.partial_stop.stop_after_safe_auto:
        stop_after_this_count = True
    if (
        content_policy.skip_after_separator_auto
        and strip_mode in content_policy.separator_auto_skip_strip_modes
        and separator_auto_gate
        and separator_gate_candidate.confidence >= config.confidence_threshold
    ):
        separator_gate_candidate.detail["content_candidate_skipped"] = content_policy.separator_auto_skip_reason
        return candidates, stop_after_this_count
    if (
        policy.candidate_run.partial_stop.skip_content_after_safe_auto
        and strip_mode in policy.candidate_run.partial_stop.skip_content_after_safe_auto_strip_modes
        and partial_safe_auto
    ):
        separator_gate_candidate.detail["content_candidate_skipped"] = (
            policy.candidate_run.partial_stop.skip_content_after_safe_auto_reason
        )
        return candidates, stop_after_this_count
    if not content_policy.enabled:
        separator_gate_candidate.detail["content_candidate_skipped"] = content_policy.disabled_skip_reason
        return candidates, stop_after_this_count
    content = content_detection_for_count(
        gray,
        config,
        fmt,
        count,
        strip_mode,
        offset,
        cache,
        policy.content,
    )
    if content is not None:
        candidates.append(apply_candidate_assessment_policy(gray, content, config, fmt, "content", cache, policy=policy))
    return candidates, stop_after_this_count
