from __future__ import annotations

from typing import Optional

from ..common import *
from ..policies import DetectionPolicy, get_detection_policy

def raw_detection_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        -float(detection.detail.get("width_cv", 1.0)),
    )

def candidate_counts_for_format(
    config: Config,
    fmt: FilmFormat,
    policy: Optional[DetectionPolicy] = None,
) -> list[tuple[int, str, tuple[float, ...]]]:
    policy = policy or get_detection_policy(fmt.name, config.strip_mode)
    return policy.counts.count_specs(
        fmt,
        config.strip_mode,
        int(config.count),
        config.count_override,
    )

def wide_separator_retry_allowed_for_strip(tuning: FormatTuning, strip_mode: str) -> bool:
    return bool(
        (strip_mode == "full" and tuning.wide_gap_retry_enabled)
        or (strip_mode == "partial" and tuning.wide_gap_retry_partial_enabled)
    )

__all__ = [
    "wide_separator_retry_allowed_for_strip",
    "raw_detection_rank",
    "candidate_counts_for_format",
]
