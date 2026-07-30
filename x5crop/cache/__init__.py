from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..image.gray import BaseGrayParameters
from ..image.statistics import ImageMeasurementStatistics
from ..image.statistics import ImageMeasurementStatisticsParameters
from ..image.workspace import WorkspaceIdentity
from ..geometry.layout import require_work_layout


@dataclass(frozen=True)
class MeasurementCacheKey:
    workspace_identity: WorkspaceIdentity
    layout: str
    base_gray_parameters: BaseGrayParameters
    statistics_parameters: ImageMeasurementStatisticsParameters

    def __post_init__(self) -> None:
        require_work_layout(self.layout)


@dataclass(frozen=True)
class MeasurementCache:
    key: MeasurementCacheKey
    gray_work: np.ndarray
    image_statistics: ImageMeasurementStatistics

    def __post_init__(self) -> None:
        if (
            self.gray_work.ndim != 2
            or self.gray_work.flags.writeable
        ):
            raise ValueError(
                "measurement cache gray must be immutable and two-dimensional"
            )

    @property
    def layout(self) -> str:
        return self.key.layout
