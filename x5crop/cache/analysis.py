from __future__ import annotations

import numpy as np

from ..image.evidence import (
    ContentEvidenceImageParameters,
    make_content_evidence_gray,
)
from ..geometry.layout import work_gray
from ..image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)
from . import MeasurementCache


def make_measurement_cache(
    gray: np.ndarray,
    layout: str,
    content_evidence_params: ContentEvidenceImageParameters,
    statistics_parameters: ImageMeasurementStatisticsParameters,
) -> MeasurementCache:
    gray_work = work_gray(gray, layout)
    statistics = image_measurement_statistics(
        gray_work,
        statistics_parameters,
    )
    content_evidence = make_content_evidence_gray(
        gray_work,
        statistics,
        content_evidence_params,
    )
    return MeasurementCache(
        layout=layout,
        gray_work=gray_work,
        content_evidence_work=content_evidence,
        content_evidence_float_work=content_evidence.astype(np.float32) / 255.0,
        image_statistics=statistics,
    )
