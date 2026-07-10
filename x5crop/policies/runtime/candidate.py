from __future__ import annotations

from dataclasses import dataclass

from ..parameters.candidate import PartialHolderParameters
from ..parameters.scoring import (
    BaseDetectionScoreParameters,
    GeometrySupportScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)


@dataclass(frozen=True)
class PartialHolderPolicy:
    enabled: bool
    parameters: PartialHolderParameters
    max_frame_aspect_error: float


@dataclass(frozen=True)
class ScoringPolicy:
    calibration: ScoringCalibrationParameters
    base_detection: BaseDetectionScoreParameters
    geometry_support: GeometrySupportScoreParameters
    separator_support: SeparatorSupportScoreParameters
