from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .content_statistics import ContentColumnStatistics
from ..image.statistics import ImageMeasurementStatistics


@dataclass
class MeasurementCache:
    layout: str
    gray_work: np.ndarray
    content_evidence_work: np.ndarray
    content_evidence_float_work: np.ndarray
    image_statistics: ImageMeasurementStatistics
    separator_profiles: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    separator_profiles_full: dict[tuple[Any, ...], np.ndarray] = field(default_factory=dict)
    content_evidence_thresholds: dict[tuple[Any, ...], float | None] = field(default_factory=dict)
    content_column_statistics: dict[tuple[Any, ...], ContentColumnStatistics] = field(
        default_factory=dict
    )
