from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorSupportParameters:
    needed_hard_max: int = 2
    max_equal_gaps_floor: int = 2
    edge_pair_min_score: float = 0.0
    reliable_gap_min_score: float = 0.28
    score_min_hard_gaps: int = 2
    score_max_equal_gaps_floor: int = 2

@dataclass(frozen=True)
class SeparatorGeometrySupportParameters:
    detected_geometry_min_hard_ratio: float = 0.60
    max_photo_width_cv: float = 0.040
    max_outer_area_ratio: float = 0.995


@dataclass(frozen=True)
class SeparatorWidthProfileParameters:
    band_candidate_count: int = 10
    sequence_candidate_count: int = 4
    max_candidates: int = 4
