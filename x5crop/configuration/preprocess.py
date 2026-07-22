from __future__ import annotations

from dataclasses import dataclass, field

from ..image.gray import BaseGrayParameters
from ..image.statistics import ImageMeasurementStatisticsParameters


@dataclass(frozen=True)
class PreprocessConfiguration:
    base_gray: BaseGrayParameters = field(default_factory=BaseGrayParameters)
    image_statistics: ImageMeasurementStatisticsParameters = field(
        default_factory=ImageMeasurementStatisticsParameters
    )
