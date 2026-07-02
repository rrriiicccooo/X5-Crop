from __future__ import annotations

from typing import Optional

from ...domain import Detection
from ...formats import FormatSpec
from ...policies.runtime_policy import DetectionPolicy
from .partial_holder import partial_safe_wide_like_gap_detail


def has_partial_safe_wide_like_candidate(
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> bool:
    for detection in candidates:
        candidate_wide_like = partial_safe_wide_like_gap_detail(detection, fmt, policy)
        if (
            bool(candidate_wide_like.get("used", False))
            and int(candidate_wide_like.get("wide_like_gaps", 0) or 0)
            >= int(candidate_wide_like.get("min_wide_like_gaps", 0) or 0)
            and int(detection.detail.get("equal_gaps", 0) or 0) == 0
        ):
            return True
    return False


def partial_wide_separator_retry_needed(
    current_best: Detection,
    candidates: list[Detection],
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> bool:
    retry_policy = policy.candidate_run.wide_separator_retry
    if (
        not retry_policy.try_partial_when_no_safe_wide_like_candidate
        or has_partial_safe_wide_like_candidate(candidates, fmt, policy)
    ):
        return False
    wide_like_detail = partial_safe_wide_like_gap_detail(current_best, fmt, policy)
    equal_gaps = int(current_best.detail.get("equal_gaps", 0) or 0)
    insufficient_wide_like = (
        bool(wide_like_detail.get("used", False))
        and int(wide_like_detail.get("wide_like_gaps", 0) or 0)
        < int(wide_like_detail.get("min_wide_like_gaps", 0) or 0)
    )
    return (
        retry_policy.partial_retry_on_equal_gaps
        and equal_gaps > 0
    ) or (
        retry_policy.partial_retry_on_insufficient_wide_like_gaps
        and insufficient_wide_like
    )


def should_try_wide_separator_candidates(
    policy: DetectionPolicy,
    strip_mode: str,
    count: int,
    fmt: FormatSpec,
    candidates: list[Detection],
    current_best: Optional[Detection],
) -> bool:
    if policy.outer.wide_separator == "off":
        return False
    retry_policy = policy.candidate_run.wide_separator_retry
    if strip_mode in retry_policy.partial_retry_strip_modes:
        return current_best is not None and partial_wide_separator_retry_needed(current_best, candidates, fmt, policy)
    if strip_mode in retry_policy.full_retry_strip_modes:
        if not retry_policy.try_full_default_count:
            return False
        if retry_policy.full_retry_requires_default_count and count != fmt.default_count:
            return False
        return True
    return False
