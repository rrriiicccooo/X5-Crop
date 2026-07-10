from __future__ import annotations

import numpy as np

from ....cache import AnalysisCache
from ....domain import DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....policies.runtime.policy import DetectionPolicy
from ....runtime.config import RuntimeConfig
from .candidate import apply_candidate_assessment_policy


def assess_source_candidates(
    gray: np.ndarray,
    detections: tuple[DetectionCandidate, ...],
    config: RuntimeConfig,
    fmt: FormatPhysicalSpec,
    source: str,
    cache: AnalysisCache,
    policy: DetectionPolicy,
) -> list[DetectionCandidate]:
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
