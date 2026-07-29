from __future__ import annotations

import numpy as np

from ..geometry.layout import work_gray
from ..image.statistics import (
    ImageMeasurementStatistics,
)
from . import MeasurementCache


def make_measurement_cache(
    gray: np.ndarray,
    layout: str,
    image_statistics: ImageMeasurementStatistics,
) -> MeasurementCache:
    gray_work = work_gray(gray, layout)
    return MeasurementCache(
        layout=layout,
        gray_work=gray_work,
        image_statistics=image_statistics,
    )
