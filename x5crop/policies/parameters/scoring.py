from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScoringCalibrationParameters:
    hard_full_confidence_floor: float
    geometry_weight: float
    content_weight: float
    separator_weight: float
    separator_source_bias: float
    no_auto_cap_partial: float
    no_auto_cap_full: float

@dataclass(frozen=True)
class BaseDetectionScoreParameters:
    width_cv_norm: float
    gap_weight: float
    width_weight: float
    outer_min_area: float
    outer_max_area: float
    outer_too_large: float
    image_quality_contrast_min: float
    full_width_cv: float
    geometry_floor_tight_cv: float
    geometry_floor_high: float
    geometry_floor_low: float
    unstable_width_cv: float
    full_outer_min_area: float
    low_confidence_floor: float
    partial_one_cap: float
    partial_two_35mm_cap: float
    partial_general_cap: float

@dataclass(frozen=True)
class SeparatorSupportScoreParameters:
    model_grid_credit: float
    model_equal_credit: float
    hard_weight: float
    model_weight: float
    no_expected_confidence_threshold: float
    no_expected_confidence_cap: float

@dataclass(frozen=True)
class GeometrySupportScoreParameters:
    width_cv_norm: float
    outer_min_area: float
    outer_max_area: float
    outer_uncertain_score: float
    aspect_norm: float
    no_aspect_score: float
    width_weight: float
    outer_weight: float
    aspect_weight: float
    count_weight: float

@dataclass(frozen=True)
class CandidateCompetitionParameters:
    top_n: int
    close_margin: float
    confidence_cap: float

__all__ = [
    'ScoringCalibrationParameters',
    'BaseDetectionScoreParameters',
    'SeparatorSupportScoreParameters',
    'GeometrySupportScoreParameters',
    'CandidateCompetitionParameters',
]
