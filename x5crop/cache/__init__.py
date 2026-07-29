from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..image.statistics import ImageMeasurementStatistics
from ..geometry.layout import require_work_layout

@dataclass
class MeasurementCache:
    layout: str
    gray_work: np.ndarray
    image_statistics: ImageMeasurementStatistics

    def __post_init__(self) -> None:
        require_work_layout(self.layout)
        if self.gray_work.ndim != 2:
            raise ValueError("measurement cache gray must be two-dimensional")
