from __future__ import annotations

import numpy as np

from ..image.evidence import make_content_evidence_gray
from ..geometry.layout import work_gray
from ..image.statistics import (
    ImageMeasurementStatistics,
)
from ..image.constants import UINT8_MAX_VALUE
from . import MeasurementCache, MeasurementCacheStatistics


def make_measurement_cache(
    gray: np.ndarray,
    layout: str,
    image_statistics: ImageMeasurementStatistics,
    transform_position_uncertainty_px: float,
    lookup_statistics: MeasurementCacheStatistics,
) -> MeasurementCache:
    gray_work = work_gray(gray, layout)
    content_evidence = make_content_evidence_gray(gray_work)
    return MeasurementCache(
        layout=layout,
        gray_work=gray_work,
        content_evidence_work=content_evidence,
        content_evidence_float_work=(
            content_evidence.astype(np.float32) / UINT8_MAX_VALUE
        ),
        image_statistics=image_statistics,
        transform_position_uncertainty_px=transform_position_uncertainty_px,
        lookup_statistics=lookup_statistics,
    )
