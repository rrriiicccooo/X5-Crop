from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
import math

import numpy as np

from .content_statistics import ContentColumnStatistics
from ..domain import Box
from ..image.statistics import ImageMeasurementStatistics
from ..geometry.layout import require_work_layout


@dataclass(frozen=True)
class MeasurementParametersKey:
    parameters: Hashable

    def __post_init__(self) -> None:
        hash(self.parameters)


@dataclass(frozen=True)
class MeasurementRegionKey:
    parameters: Hashable
    region: Box

    def __post_init__(self) -> None:
        hash(self.parameters)
        if not self.region.valid():
            raise ValueError("measurement cache region must have positive extent")


@dataclass(frozen=True)
class ThresholdedMeasurementRegionKey:
    parameters: Hashable
    region: Box
    threshold: float

    def __post_init__(self) -> None:
        hash(self.parameters)
        if not self.region.valid():
            raise ValueError("measurement cache region must have positive extent")
        if not math.isfinite(self.threshold):
            raise ValueError("measurement cache threshold must be finite")


@dataclass
class MeasurementCache:
    layout: str
    gray_work: np.ndarray
    content_evidence_work: np.ndarray
    content_evidence_float_work: np.ndarray
    image_statistics: ImageMeasurementStatistics
    separator_profiles: dict[MeasurementRegionKey, np.ndarray] = field(default_factory=dict)
    separator_profiles_full: dict[MeasurementParametersKey, np.ndarray] = field(default_factory=dict)
    content_evidence_thresholds: dict[MeasurementRegionKey, float | None] = field(default_factory=dict)
    content_column_statistics: dict[ThresholdedMeasurementRegionKey, ContentColumnStatistics] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        require_work_layout(self.layout)
        measurements = (
            self.gray_work,
            self.content_evidence_work,
            self.content_evidence_float_work,
        )
        if any(item.ndim != 2 for item in measurements):
            raise ValueError("measurement cache images must be two-dimensional")
        if any(item.shape != self.gray_work.shape for item in measurements[1:]):
            raise ValueError("measurement cache images must share one workspace shape")
