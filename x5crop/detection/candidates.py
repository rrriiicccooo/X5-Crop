from __future__ import annotations

from typing import Optional

from ..config import Config
from ..domain import Detection
from ..formats import FormatSpec
from ..policies.base import DetectionPolicy
from ..policies.registry import get_detection_policy

def raw_detection_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        -float(detection.detail.get("width_cv", 1.0)),
    )

def candidate_counts_for_format(
    config: Config,
    fmt: FormatSpec,
    policy: Optional[DetectionPolicy] = None,
) -> list[tuple[int, str, tuple[float, ...]]]:
    policy = policy or get_detection_policy(fmt.name, config.strip_mode)
    return policy.counts.count_specs(
        fmt,
        config.strip_mode,
        int(config.count),
        config.count_override,
    )

__all__ = [
    "raw_detection_rank",
    "candidate_counts_for_format",
]
