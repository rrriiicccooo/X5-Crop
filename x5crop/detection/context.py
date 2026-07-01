from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import RuntimeConfig
from ..formats import FormatSpec
from ..policies.runtime_policy import DetectionPolicy
from ..policies.registry import get_detection_policy
from ..runtime import AnalysisCache


@dataclass(frozen=True)
class DetectionContext:
    gray: np.ndarray
    config: RuntimeConfig
    format: FormatSpec
    policy: DetectionPolicy
    cache: AnalysisCache


def detection_policy_for(config: RuntimeConfig, fmt: FormatSpec) -> DetectionPolicy:
    return get_detection_policy(fmt.name, config.strip_mode)


__all__ = ["DetectionContext", "detection_policy_for"]
