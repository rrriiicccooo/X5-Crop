from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorSupportParameters:
    needed_hard_max: int = 2
    max_equal_gaps_floor: int = 2
    allow_geometry_support: bool = True
    hard_required_all_gaps: bool = True
    edge_pair_min_score_without_broad_width: float = 0.0
    edge_pair_min_score_with_broad_width: float = 0.0
    reliable_gap_min_score: float = 0.28
    min_broad_separator_width_gaps_for_auto: int = 0
    score_min_hard_gaps: int = 2
    score_max_equal_gaps_floor: int = 2
    low_hard_confidence_cap: float = 0.82
    mostly_equal_confidence_cap: float = 0.84
    allow_full_detected_geometry: bool = True

@dataclass(frozen=True)
class LeadingGridFailureParameters:
    enabled: bool = True
    min_expected_gaps: int = 5
    leading_count: int = 3
    low_score: float = 0.35
    very_low_score: float = 0.12
    very_low_count: int = 2
    max_hard_gaps: int = 2

@dataclass(frozen=True)
class SeparatorGeometrySupportParameters:
    detected_geometry_min_hard_ratio: float = 0.60
    detected_geometry_min_joint_score: float = 0.78
    stable_grid_min_hard_ratio: float = 0.35
    stable_grid_min_joint_score: float = 0.65
    max_photo_width_cv: float = 0.040
    max_outer_area_ratio: float = 0.995

@dataclass(frozen=True)
class SeparatorWidthProfileParameters:
    full_enabled: bool = True
    partial_enabled: bool = True
    max_width_ratio: float = 0.060

__all__ = [
    'SeparatorSupportParameters',
    'LeadingGridFailureParameters',
    'SeparatorGeometrySupportParameters',
    'SeparatorWidthProfileParameters',
]
