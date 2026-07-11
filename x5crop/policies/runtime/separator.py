from __future__ import annotations

from dataclasses import dataclass

from ...geometry.detection_parameters import (
    SeparatorContinuityParameters,
    SeparatorProfileParameters,
)
from ..parameters.separator import (
    FrameDimensionEstimateParameters,
    SeparatorObservationParameters,
)


@dataclass(frozen=True)
class SeparatorPolicy:
    observation: SeparatorObservationParameters
    frame_dimension_estimate: FrameDimensionEstimateParameters
    continuity: SeparatorContinuityParameters
    profile: SeparatorProfileParameters
