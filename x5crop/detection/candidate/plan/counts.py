from __future__ import annotations

from ....domain import Detection
from ...evidence.photo_width import photo_width_cv_from_detail
from ....formats import FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ....runtime.config import RuntimeConfig

def raw_detection_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    photo_width_cv = photo_width_cv_from_detail(detection.detail)
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        -float(photo_width_cv) if photo_width_cv is not None else -1.0,
    )

def candidate_counts_for_format(
    config: RuntimeConfig,
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> list[tuple[int, str, tuple[float, ...]]]:
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
