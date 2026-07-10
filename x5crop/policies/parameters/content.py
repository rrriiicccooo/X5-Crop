from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class ContentEvidenceParameters:
    percentile: float = 70.0
    threshold_multiplier: float = 0.70
    threshold_min: float = 0.08
    threshold_max: float = 0.45
    aspect_ok_max: float = 0.22
    present_mean_min: float = 0.075
    present_coverage_min: float = 0.18

@dataclass(frozen=True)
class ContentProfileParameters:
    smooth_ratio: float = 0.010
    min_run_ratio: float = 0.20
    threshold_min: float = 0.035
    threshold_max: float = 0.40
    p35_weight: float = 0.38
    p65_multiplier: float = 0.82

@dataclass(frozen=True)
class ContentMaskParameters:
    p55_weight: float = 0.34
    p75_multiplier: float = 0.78
    threshold_min: float = 0.045
    threshold_max: float = 0.45
    percentiles: tuple[float, float, float] = (55.0, 75.0, 92.0)
    bbox_min_fraction: float = 0.008
    outer_min_width_ratio: float = 0.08
    outer_min_height_ratio: float = 0.08
    outer_min_width_px: int = 60
    outer_min_height_px: int = 30
    outer_expand_ratio: float = 0.002

@dataclass(frozen=True)
class ContentCandidateParameters:
    expected_width_min_px: float = 8.0
    coverage_weight: float = 0.38
    mean_weight: float = 0.30
    run_weight: float = 0.22
    aspect_weight: float = 0.10
    coverage_norm: float = 0.22
    mean_norm: float = 0.16
    aspect_norm: float = 0.18
    weak_coverage: float = 0.14
    aspect_uncertain: float = 0.18
    grid_fallback_cap: float = 0.82
    run_mismatch_cap: float = 0.84
    runs_incomplete_cap: float = 0.84
    weak_coverage_cap: float = 0.82
    aspect_uncertain_cap: float = 0.82

@dataclass(frozen=True)
class ContentSupportParameters:
    coverage_norm: float = 0.22
    mean_norm: float = 0.16
    aspect_norm: float = 0.22
    coverage_weight: float = 0.42
    mean_weight: float = 0.40
    aspect_weight: float = 0.18
    score_ok: float = 1.0
    score_weak: float = 0.72
    score_low_content: float = 0.58
    score_aspect_conflict: float = 0.35
    score_unknown: float = 0.50

__all__ = [
    'ContentEvidenceParameters',
    'ContentProfileParameters',
    'ContentMaskParameters',
    'ContentCandidateParameters',
    'ContentSupportParameters',
]
