from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PartialHolderParameters:
    enabled: bool
    min_count_35mm: int
    min_count_small: int
    min_hard_gaps: int
    min_hard_ratio: float
    max_equal_gaps: int
    max_photo_width_cv: float
    min_joint_score: float
    min_content_score: float
    min_geometry_score: float
    min_broad_separator_width_gaps: int
    broad_separator_width_min_ratio: float
    leading_content_check: bool
    leading_content_max_mean: float
    leading_content_max_coverage: float
    leading_content_band_ratio: float
    frame_content_check: bool
    min_frame_mean: float
    min_frame_coverage: float

@dataclass(frozen=True)
class ApprovedGeometryAdjustmentParameters:
    long_limit_ratio: float
    long_limit_min: int
    long_limit_max: int
    min_ext_ratio: float
    min_ext_min: int
    min_ext_max: int

__all__ = [
    'PartialHolderParameters',
    'ApprovedGeometryAdjustmentParameters',
]
