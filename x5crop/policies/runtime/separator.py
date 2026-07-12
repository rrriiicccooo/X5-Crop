from __future__ import annotations

from dataclasses import dataclass

from ...geometry.detection_parameters import (
    SeparatorContinuityParameters,
    SeparatorProfileParameters,
)
from ..parameters.separator import (
    FrameDimensionPriorParameters,
    SeparatorObservationParameters,
)


@dataclass(frozen=True)
class SeparatorPolicy:
    observation: SeparatorObservationParameters
    frame_dimension_prior: FrameDimensionPriorParameters
    continuity: SeparatorContinuityParameters
    profile: SeparatorProfileParameters
