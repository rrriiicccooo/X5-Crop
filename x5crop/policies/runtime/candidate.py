from __future__ import annotations

from dataclasses import dataclass

from ..parameters.scoring import (
    BaseDetectionScoreParameters,
    GeometrySupportScoreParameters,
    ScoringCalibrationParameters,
)


@dataclass(frozen=True)
class ScoringPolicy:
    calibration: ScoringCalibrationParameters
    base_detection: BaseDetectionScoreParameters
    geometry_support: GeometrySupportScoreParameters
