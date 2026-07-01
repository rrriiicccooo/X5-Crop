from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..common import AnalysisCache, Config, FilmFormat
from ..policies import DetectionPolicy, get_detection_policy


@dataclass(frozen=True)
class DetectionContext:
    gray: np.ndarray
    config: Config
    format: FilmFormat
    policy: DetectionPolicy
    cache: AnalysisCache


def detection_policy_for(config: Config, fmt: FilmFormat) -> DetectionPolicy:
    return get_detection_policy(fmt.name, config.strip_mode)


__all__ = ["DetectionContext", "detection_policy_for"]
