from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import Config
from ..format_specs import FilmFormat
from ..policies.base import DetectionPolicy
from ..policies.registry import get_detection_policy
from ..runtime import AnalysisCache


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
