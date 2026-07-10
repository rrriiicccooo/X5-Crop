from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PartialHolderParameters:
    minimum_observed_frame_count: int = 2
    min_hard_gaps: int = 1
    min_hard_ratio: float = 0.15
    max_equal_gaps: int = 0
    max_photo_width_cv: float = 0.055
    min_joint_score: float = 0.65
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    leading_content_max_mean: float = 0.20
    leading_content_max_coverage: float = 0.34
    leading_content_band_ratio: float = 0.04
    leading_content_band_min_px: int = 8
    leading_content_band_max_ratio: float = 0.12
    leading_content_signal_threshold: float = 0.20
    min_frame_mean: float = 0.055
    min_frame_coverage: float = 0.10
