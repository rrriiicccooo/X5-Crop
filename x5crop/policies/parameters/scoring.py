from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class ScoringCalibrationParameters:
    geometry_weight: float = 0.34
    content_weight: float = 0.33
    separator_weight: float = 0.33
    separator_source_bias: float = 0.03
    no_auto_cap_partial: float = 0.82
    no_auto_cap_full: float = 0.84
    dual_lane_below_threshold_cap: float = 0.84
    dual_lane_frame_count_mismatch_cap: float = 0.82

@dataclass(frozen=True)
class BaseDetectionScoreParameters:
    photo_width_cv_norm: float = 0.030
    gap_weight: float = 0.40
    photo_width_weight: float = 0.30
    outer_min_area: float = 0.35
    outer_max_area: float = 0.995
    outer_too_large: float = 0.94
    image_quality_contrast_min: float = 35.0
    full_photo_width_cv: float = 0.040
    geometry_floor_tight_photo_width_cv: float = 0.006
    geometry_floor_high: float = 0.92
    geometry_floor_low: float = 0.88
    unstable_photo_width_cv: float = 0.030
    full_outer_min_area: float = 0.40
    low_confidence_floor: float = 0.85
    partial_one_cap: float = 0.78
    partial_two_frame_dense_sequence_cap: float = 0.82
    image_quality_percentiles: tuple[float, float, float] = (1.0, 50.0, 99.0)
    hard_support_floor_min_expected_gaps: int = 3
    hard_gap_floor_min_count: int = 2
    model_gap_overuse_min_count: int = 2
    partial_ambiguous_count_max: int = 2
    partial_dense_sequence_min_nominal_count: int = 6

@dataclass(frozen=True)
class SeparatorSupportScoreParameters:
    model_grid_credit: float = 0.35
    model_equal_credit: float = 0.12
    hard_weight: float = 0.78
    model_weight: float = 0.22
    no_expected_confidence_threshold: float = 0.85
    no_expected_confidence_cap: float = 0.75

@dataclass(frozen=True)
class GeometrySupportScoreParameters:
    photo_width_cv_norm: float = 0.040
    aspect_norm: float = 0.22
    photo_width_weight: float = 0.34
    aspect_weight: float = 0.26
    count_weight: float = 0.16

@dataclass(frozen=True)
class CandidateCompetitionParameters:
    top_n: int = 8
    close_margin: float = 0.04
    confidence_cap: float = 0.84
