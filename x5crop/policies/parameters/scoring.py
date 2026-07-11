from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class ScoringCalibrationParameters:
    geometry_weight: float = 0.34
    content_weight: float = 0.33
    separator_weight: float = 0.33

@dataclass(frozen=True)
class BaseDetectionScoreParameters:
    photo_width_cv_norm: float = 0.030
    separator_weight: float = 0.40
    photo_width_weight: float = 0.30
    maximum_photo_width_cv: float = 0.030

@dataclass(frozen=True)
class GeometrySupportScoreParameters:
    photo_width_cv_norm: float = 0.040
    aspect_norm: float = 0.22
    photo_width_weight: float = 0.34
    aspect_weight: float = 0.26
    count_weight: float = 0.16

@dataclass(frozen=True)
class SelectionConsensusParameters:
    confidence_tie_margin: float = 0.04
    geometry_tolerance_ratio: float = 0.04
