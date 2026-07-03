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
from .source_policy import safety_candidate_outer_proposals_enabled
from .sources import detect_candidate_for_count, detect_safety_outer_proposal_candidate_for_count


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
    content_policy = policy.candidate_plan.content_candidate
    candidates: list[Detection] = []
    stop_after_this_count = False
    separator = detect_candidate_for_count(gray, config, fmt, count, strip_mode, offset, cache, policy=policy)
    separator_candidate = apply_candidate_assessment_policy(gray, separator, config, fmt, "separator", cache, policy=policy)
    candidates.append(separator_candidate)
    separator_gate_candidate = separator_candidate
    separator_auto_gate = bool(
        separator_candidate.detail.get("candidate_assessment", {}).get("auto_gate", False)
    )
    if safety_candidate_outer_proposals_enabled(policy):
        safety_proposal = detect_safety_outer_proposal_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            policy=policy,
        )
        if safety_proposal is not None:
            safety_candidate = apply_candidate_assessment_policy(gray, safety_proposal, config, fmt, "separator", cache, policy=policy)
            safety_cap = policy.scoring.no_auto_cap_partial if strip_mode == "partial" else policy.scoring.no_auto_cap_full
            safety_candidate.confidence = min(
                safety_candidate.confidence,
                safety_cap,
                max(0.0, config.confidence_threshold - 0.01),
            )
            safety_candidate.review_reasons.append("safety_candidate_review_only")
            safety_candidate.review_reasons = sorted(set(safety_candidate.review_reasons))
            assessment = safety_candidate.detail.get("candidate_assessment", {})
            if isinstance(assessment, dict):
                assessment["auto_gate"] = False
                assessment["source"] = "safety_candidate"
            safety_candidate.detail["safety_candidate"] = {
                "used": True,
                "review_only": True,
                "separator_local_mode": policy.outer.proposal.geometry.separator.local.mode,
                "separator_full_width_mode": policy.outer.proposal.geometry.separator.full_width.mode,
                "strategies": list(policy.candidate_plan.safety_candidate.strategies),
            }
            candidates.append(safety_candidate)
    partial_safe_auto = is_partial_safe_auto_candidate(separator_gate_candidate, config.confidence_threshold)
    if partial_safe_auto and policy.candidate_plan.partial_stop.stop_after_safe_auto:
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
        policy.candidate_plan.partial_stop.skip_content_after_safe_auto
        and strip_mode in policy.candidate_plan.partial_stop.skip_content_after_safe_auto_strip_modes
        and partial_safe_auto
    ):
        separator_gate_candidate.detail["content_candidate_skipped"] = (
            policy.candidate_plan.partial_stop.skip_content_after_safe_auto_reason
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
