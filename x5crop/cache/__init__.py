from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass
import math

import numpy as np

from .content_statistics import ContentColumnStatistics
from ..domain import BoundaryMeasurementSet, Box
from ..image.content import ContentRegionObservation
from ..image.statistics import ImageMeasurementStatistics
from ..image.separator_profile import SeparatorProfileMeasurement
from ..geometry.layout import require_work_layout


def _require_frozen_parameters(value: object) -> None:
    dataclass_parameters = getattr(type(value), "__dataclass_params__", None)
    if not is_dataclass(value) or not bool(
        dataclass_parameters and dataclass_parameters.frozen
    ):
        raise TypeError("measurement cache keys require frozen parameter objects")
    hash(value)


@dataclass(frozen=True)
class MeasurementParametersKey:
    parameters: object

    def __post_init__(self) -> None:
        _require_frozen_parameters(self.parameters)


@dataclass(frozen=True)
class MeasurementRegionKey:
    parameters: object
    region: Box

    def __post_init__(self) -> None:
        _require_frozen_parameters(self.parameters)
        if not self.region.valid():
            raise ValueError("measurement cache region must have positive extent")


@dataclass(frozen=True)
class ThresholdedMeasurementRegionKey:
    parameters: object
    region: Box
    threshold: float

    def __post_init__(self) -> None:
        _require_frozen_parameters(self.parameters)
        if not self.region.valid():
            raise ValueError("measurement cache region must have positive extent")
        if not math.isfinite(self.threshold):
            raise ValueError("measurement cache threshold must be finite")


@dataclass
class MeasurementCacheStatistics:
    hits: int = 0
    misses: int = 0

    def record_lookup(self, *, found: bool) -> None:
        if found:
            self.hits += 1
        else:
            self.misses += 1


@dataclass
class MeasurementCache:
    layout: str
    gray_work: np.ndarray
    content_evidence_work: np.ndarray
    content_evidence_float_work: np.ndarray
    image_statistics: ImageMeasurementStatistics
    transform_position_uncertainty_px: float
    lookup_statistics: MeasurementCacheStatistics = field(
        default_factory=MeasurementCacheStatistics
    )
    separator_profile_measurements: dict[
        MeasurementRegionKey,
        SeparatorProfileMeasurement,
    ] = field(default_factory=dict)
    boundary_measurements: dict[MeasurementParametersKey, BoundaryMeasurementSet] = field(
        default_factory=dict
    )
    content_evidence_thresholds: dict[MeasurementRegionKey, float | None] = field(default_factory=dict)
    content_region_observations: dict[
        MeasurementRegionKey,
        ContentRegionObservation,
    ] = field(default_factory=dict)
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
        if (
            not math.isfinite(self.transform_position_uncertainty_px)
            or self.transform_position_uncertainty_px < 0.0
        ):
            raise ValueError("transform position uncertainty must be finite")
