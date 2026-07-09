from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class PartialHolderParameters:
    enabled: bool = True
    min_count_35mm: int = 2
    min_count_small: int = 2
    min_hard_gaps: int = 1
    min_hard_ratio: float = 0.15
    max_equal_gaps: int = 0
    max_photo_width_cv: float = 0.055
    min_joint_score: float = 0.65
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    min_broad_separator_width_gaps: int = 0
    broad_separator_width_min_ratio: float = 0.033
    leading_content_check: bool = False
    leading_content_max_mean: float = 0.20
    leading_content_max_coverage: float = 0.34
    leading_content_band_ratio: float = 0.04
    leading_content_band_min_px: int = 8
    leading_content_band_max_ratio: float = 0.12
    leading_content_signal_threshold: float = 0.20
    frame_content_check: bool = False
    min_frame_mean: float = 0.055
    min_frame_coverage: float = 0.10

@dataclass(frozen=True)
class ApprovedGeometryAdjustmentParameters:
    long_limit_ratio: float = 0.018
    long_limit_min: int = 20
    long_limit_max: int = 60
    min_ext_ratio: float = 0.0100
    min_ext_min: int = 50
    min_ext_max: int = 120
    side_band_trim_ratio: float = 0.12
    content_threshold_u8: int = 242
    min_active_column_fraction: float = 0.018

__all__ = [
    'PartialHolderParameters',
    'ApprovedGeometryAdjustmentParameters',
]
