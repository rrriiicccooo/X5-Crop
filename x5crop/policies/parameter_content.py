from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ContentEvidenceParameters:
    percentile: float
    threshold_multiplier: float
    threshold_min: float
    threshold_max: float
    aspect_ok_max: float
    present_mean_min: float
    present_coverage_min: float

@dataclass(frozen=True)
class ContentProfileParameters:
    smooth_ratio: float
    min_run_ratio: float
    threshold_min: float
    threshold_max: float
    p35_weight: float
    p65_multiplier: float

@dataclass(frozen=True)
class ContentMaskParameters:
    p55_weight: float
    p75_multiplier: float
    threshold_min: float
    threshold_max: float
    percentiles: tuple[float, float, float]
    bbox_min_fraction: float
    outer_min_width_ratio: float
    outer_min_height_ratio: float
    outer_min_width_px: int
    outer_min_height_px: int
    outer_expand_ratio: float

@dataclass(frozen=True)
class ContentCandidateParameters:
    expected_width_min_px: float
    coverage_weight: float
    mean_weight: float
    run_weight: float
    aspect_weight: float
    coverage_norm: float
    mean_norm: float
    aspect_norm: float
    weak_coverage: float
    aspect_uncertain: float
    grid_fallback_cap: float
    run_mismatch_cap: float
    runs_incomplete_cap: float
    weak_coverage_cap: float
    aspect_uncertain_cap: float

@dataclass(frozen=True)
class ContentSupportParameters:
    coverage_norm: float
    mean_norm: float
    aspect_norm: float
    coverage_weight: float
    mean_weight: float
    aspect_weight: float
    gate_ok: float
    gate_weak: float
    gate_low_content: float
    gate_aspect_conflict: float
    gate_unknown: float

__all__ = [
    'ContentEvidenceParameters',
    'ContentProfileParameters',
    'ContentMaskParameters',
    'ContentCandidateParameters',
    'ContentSupportParameters',
]
