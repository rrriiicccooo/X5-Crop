from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class ContentEvidenceParameters:
    percentile: float = 70.0
    threshold_multiplier: float = 0.70
    threshold_min: float = 0.08
    threshold_max: float = 0.45
    present_mean_min: float = 0.075
    present_coverage_min: float = 0.18
    boundary_band_ratio: float = 0.02
    boundary_band_min_px: int = 2

@dataclass(frozen=True)
class ContentProfileParameters:
    smooth_ratio: float = 0.010
    smooth_min_px: int = 5
    min_run_ratio: float = 0.20
    min_run_width_px: int = 6
    threshold_min: float = 0.035
    threshold_max: float = 0.40
    percentiles: tuple[float, float, float] = (35.0, 65.0, 90.0)
    low_percentile_weight: float = 0.38
    mid_percentile_multiplier: float = 0.82

@dataclass(frozen=True)
class ContentMaskParameters:
    p55_weight: float = 0.34
    p75_multiplier: float = 0.78
    threshold_min: float = 0.045
    threshold_max: float = 0.45
    percentiles: tuple[float, float, float] = (55.0, 75.0, 92.0)
    bbox_min_fraction: float = 0.008
    outer_expand_ratio: float = 0.002

@dataclass(frozen=True)
class ContentSupportParameters:
    coverage_norm: float = 0.22
    mean_norm: float = 0.16
    coverage_weight: float = 0.42
    mean_weight: float = 0.40
