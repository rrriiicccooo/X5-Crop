from __future__ import annotations

import numpy as np

from ..image.gray import BaseGrayParameters
from ..geometry.layout import work_gray
from ..image.statistics import (
    ImageMeasurementStatistics,
    ImageMeasurementStatisticsParameters,
)
from ..image.workspace import workspace_identity_for_gray
from . import MeasurementCache, MeasurementCacheKey


def make_measurement_cache(
    gray: np.ndarray,
    layout: str,
    image_statistics: ImageMeasurementStatistics,
    base_gray_parameters: BaseGrayParameters,
    statistics_parameters: ImageMeasurementStatisticsParameters,
) -> MeasurementCache:
    gray_work = work_gray(gray, layout)
    gray_work.flags.writeable = False
    return MeasurementCache(
        key=MeasurementCacheKey(
            workspace_identity=workspace_identity_for_gray(gray),
            layout=layout,
            base_gray_parameters=base_gray_parameters,
            statistics_parameters=statistics_parameters,
        ),
        gray_work=gray_work,
        image_statistics=image_statistics,
    )
