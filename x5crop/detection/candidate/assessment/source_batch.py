from __future__ import annotations

import numpy as np

from ....cache import AnalysisCache
from ....domain import Detection
from ....formats import FormatSpec
from ....policies.runtime.policy import DetectionPolicy
from ....runtime.config import RuntimeConfig
from .candidate import apply_candidate_assessment_policy


def assess_source_candidates(
    gray: np.ndarray,
    detections: tuple[Detection, ...],
    config: RuntimeConfig,
    fmt: FormatSpec,
    source: str,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> list[Detection]:
    return [
        apply_candidate_assessment_policy(
            gray,
            detection,
            config,
            fmt,
            source,
            cache,
            policy=policy,
        )
        for detection in detections
    ]


__all__ = ["assess_source_candidates"]
