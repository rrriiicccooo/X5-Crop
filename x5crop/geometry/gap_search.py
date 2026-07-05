from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..constants import GAP_DETECTED, GAP_EQUAL
from ..domain import Gap
from ..utils import clamp_int, runs_from_mask
from .detection_parameters import GapSearchParameters


@dataclass(frozen=True)
class GapWidthLimits:
    normal_max: int
    max_width: int
    min_width: int
    guard: int


@dataclass(frozen=True)
class DetectedGapCandidate:
    distance: float
    quality: float
    mean_score: float
    center: float
    start: float
    end: float
    method: str = GAP_DETECTED

    def rank_key(self) -> tuple[float, float, float, float, float, float, str]:
        return (
            self.distance,
            -self.quality,
            -self.mean_score,
            self.center,
            self.start,
            self.end,
            self.method,
        )


def gap_search_window(
    profile_length: int,
    expected: float,
    pitch: float,
    config: GapSearchParameters,
) -> tuple[int, int]:
    radius = clamp_int(pitch * config.radius_ratio, config.radius_min, config.radius_max)
    lo = max(1, int(round(expected)) - radius)
    hi = min(profile_length - 1, int(round(expected)) + radius + 1)
    return lo, hi


def gap_width_limits(
    pitch: float,
    max_width_ratio_override: Optional[float],
    config: GapSearchParameters,
) -> GapWidthLimits:
    normal_max_gap_w = clamp_int(pitch * config.max_width_ratio, config.max_width_min, config.max_width_max)
    max_width_ratio = config.max_width_ratio if max_width_ratio_override is None else max_width_ratio_override
    max_gap_w = clamp_int(pitch * max_width_ratio, config.max_width_min, config.max_width_max)
    min_gap_w = clamp_int(pitch * config.min_width_ratio, config.min_width_min, config.min_width_max)
    guard_w = clamp_int(pitch * config.guard_ratio, config.guard_min, config.guard_max)
    return GapWidthLimits(normal_max_gap_w, max_gap_w, min_gap_w, guard_w)


def gap_score_thresholds(local_max: float, config: GapSearchParameters) -> tuple[float, float]:
    min_score = config.min_score
    peak_threshold = max(min_score, local_max * config.peak_multiplier)
    band_threshold = max(min_score * config.band_min_score_multiplier, local_max * config.band_multiplier)
    return peak_threshold, band_threshold


def expanded_gap_band(
    local: np.ndarray,
    run_start: int,
    run_end: int,
    band_threshold: float,
    max_width: int,
) -> tuple[int, int]:
    band_start, band_end = run_start, run_end
    while band_start > 0 and local[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_width:
        band_start -= 1
    while band_end < len(local) and local[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_width:
        band_end += 1
    return band_start, band_end


def detected_gap_candidate(
    local: np.ndarray,
    lo: int,
    expected: float,
    pitch: float,
    run_start: int,
    run_end: int,
    limits: GapWidthLimits,
    band_threshold: float,
    max_width_ratio_override: Optional[float],
    config: GapSearchParameters,
) -> Optional[DetectedGapCandidate]:
    band_start, band_end = expanded_gap_band(local, run_start, run_end, band_threshold, limits.max_width)
    band_width = band_end - band_start
    if band_width < limits.min_width or band_width > limits.max_width:
        return None

    left_guard = local[max(0, band_start - limits.guard):band_start]
    right_guard = local[band_end:min(len(local), band_end + limits.guard)]
    if left_guard.size == 0 or right_guard.size == 0:
        return None
    mean_score = float(local[band_start:band_end].mean())
    side_score = max(float(left_guard.mean()), float(right_guard.mean()))
    prominence = mean_score - side_score
    if prominence < config.weak_prominence_min and mean_score < config.weak_prominence_mean_override:
        return None
    if max_width_ratio_override is not None and band_width > limits.normal_max:
        if mean_score < config.separator_width_min_mean or prominence < config.separator_width_min_prominence:
            return None

    center = float(lo + (band_start + band_end - 1) / 2.0)
    start = float(lo + band_start)
    end = float(lo + band_end)
    distance = abs(center - expected) / max(1.0, pitch)
    quality = mean_score + config.quality_prominence_weight * prominence
    return DetectedGapCandidate(distance, quality, mean_score, center, start, end)


def find_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    max_width_ratio_override: Optional[float] = None,
    gap_search: GapSearchParameters | None = None,
) -> Gap:
    config = gap_search or GapSearchParameters()
    lo, hi = gap_search_window(len(profile), expected, pitch, config)
    if hi <= lo:
        return Gap(index, float(expected), 0.0, GAP_EQUAL)
    local = profile[lo:hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = config.min_score
    if local.size == 0 or local_max < min_score:
        return Gap(index, float(expected), local_max, GAP_EQUAL)

    limits = gap_width_limits(pitch, max_width_ratio_override, config)
    peak_threshold, band_threshold = gap_score_thresholds(local_max, config)
    candidates: list[DetectedGapCandidate] = []

    for run_start, run_end in runs_from_mask(local >= peak_threshold):
        candidate = detected_gap_candidate(
            local,
            lo,
            expected,
            pitch,
            run_start,
            run_end,
            limits,
            band_threshold,
            max_width_ratio_override,
            config,
        )
        if candidate is not None:
            candidates.append(candidate)

    if candidates:
        candidate = min(candidates, key=lambda item: item.rank_key())
        return Gap(index, candidate.center, float(candidate.quality), candidate.method, candidate.start, candidate.end)

    return Gap(index, float(expected), local_max, GAP_EQUAL)


__all__ = [
    "DetectedGapCandidate",
    "GapWidthLimits",
    "detected_gap_candidate",
    "expanded_gap_band",
    "find_gap",
    "gap_score_thresholds",
    "gap_search_window",
    "gap_width_limits",
]
