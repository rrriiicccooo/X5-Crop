from __future__ import annotations

from typing import Optional

from ...domain import Detection
from ...formats import FormatSpec
from ...policies.runtime_policy import DetectionPolicy
from .partial_holder import partial_safe_broad_separator_width_gap_detail


def has_partial_safe_broad_separator_width_candidate(
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> bool:
    for detection in candidates:
        candidate_broad_separator_width = partial_safe_broad_separator_width_gap_detail(detection, fmt, policy)
        if (
            bool(candidate_broad_separator_width.get("used", False))
            and int(candidate_broad_separator_width.get("broad_separator_width_gaps", 0) or 0)
            >= int(candidate_broad_separator_width.get("min_broad_separator_width_gaps", 0) or 0)
            and int(detection.detail.get("equal_gaps", 0) or 0) == 0
        ):
            return True
    return False


def partial_relaxed_separator_width_retry_needed(
    current_best: Detection,
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> bool:
    retry_policy = policy.candidate_run.relaxed_separator_width_retry
    if (
        not retry_policy.try_partial_when_no_safe_broad_separator_width_candidate
        or has_partial_safe_broad_separator_width_candidate(candidates, fmt, policy)
    ):
        return False
    broad_separator_width_detail = partial_safe_broad_separator_width_gap_detail(current_best, fmt, policy)
    equal_gaps = int(current_best.detail.get("equal_gaps", 0) or 0)
    insufficient_broad_separator_width = (
        bool(broad_separator_width_detail.get("used", False))
        and int(broad_separator_width_detail.get("broad_separator_width_gaps", 0) or 0)
        < int(broad_separator_width_detail.get("min_broad_separator_width_gaps", 0) or 0)
    )
    return (
        retry_policy.partial_retry_on_equal_gaps
        and equal_gaps > 0
    ) or (
        retry_policy.partial_retry_on_insufficient_broad_separator_width_gaps
        and insufficient_broad_separator_width
    )


def should_try_relaxed_separator_width_candidates(
    policy: DetectionPolicy,
    strip_mode: str,
    count: int,
    fmt: FormatSpec,
    candidates: list[Detection],
    current_best: Optional[Detection],
) -> bool:
    if policy.outer.proposal.geometry.separator.width_profile_mode == "off":
        return False
    retry_policy = policy.candidate_run.relaxed_separator_width_retry
    if strip_mode in retry_policy.partial_retry_strip_modes:
        return current_best is not None and partial_relaxed_separator_width_retry_needed(current_best, candidates, fmt, policy)
    if strip_mode in retry_policy.full_retry_strip_modes:
        if not retry_policy.try_full_default_count:
            return False
        if retry_policy.full_retry_requires_default_count and count != fmt.default_count:
            return False
        return True
    return False


__all__ = [
    "has_partial_safe_broad_separator_width_candidate",
    "partial_relaxed_separator_width_retry_needed",
    "should_try_relaxed_separator_width_candidates",
]
