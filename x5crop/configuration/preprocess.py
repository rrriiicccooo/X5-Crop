from __future__ import annotations

from dataclasses import dataclass, field

from ..image.deskew_parameters import DeskewParameters
from ..image.evidence import (
    DeskewFallbackEvidenceParameters,
)
from ..image.gray import BaseGrayParameters
from ..image.statistics import ImageMeasurementStatisticsParameters


@dataclass(frozen=True)
class PreprocessConfiguration:
    base_gray: BaseGrayParameters = field(default_factory=BaseGrayParameters)
    deskew: DeskewParameters = field(default_factory=DeskewParameters)
    deskew_fallback_evidence: DeskewFallbackEvidenceParameters = field(
        default_factory=DeskewFallbackEvidenceParameters
    )
    image_statistics: ImageMeasurementStatisticsParameters = field(
        default_factory=ImageMeasurementStatisticsParameters
    )
