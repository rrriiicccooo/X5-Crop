from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..constants import GAP_DETECTED
from ..domain import Gap
from ..utils import clamp_float, clamp_int, runs_from_mask, sampled_percentile, smooth_1d
from .detection_parameters import SeparatorWidthProfileSearchParameters
from .separator_band import SeparatorBand


@dataclass(frozen=True)
class SeparatorWidthGapCandidate:
    score: float
    start: int
    end: int
    center: float


def separator_width_profile(
    crop: np.ndarray,
    params: SeparatorWidthProfileSearchParameters | None = None,
) -> np.ndarray:
    params = params or SeparatorWidthProfileSearchParameters()
    if crop.size == 0:
        return np.array([], dtype=np.float32)
    sample = crop[
        :: max(1, crop.shape[0] // max(1, int(params.sample_short_axis_max))),
        :: max(1, crop.shape[1] // max(1, int(params.sample_long_axis_max))),
    ]
    p01, p99 = sampled_percentile(sample, [1, 99])
    span = max(1.0, float(p99 - p01))
    threshold = float(p01) + span * params.threshold_span_ratio
    profile = (crop <= threshold).mean(axis=0).astype(np.float32)
    return smooth_1d(
        profile,
        max(
            params.profile_smooth_min,
            int(round(crop.shape[0] * params.profile_smooth_short_axis_ratio)),
        ),
    )


def separator_width_bounds(
    short_axis: float,
    params: SeparatorWidthProfileSearchParameters | None = None,
) -> tuple[int, int, float]:
    params = params or SeparatorWidthProfileSearchParameters()
    min_width = clamp_int(
        short_axis * params.min_width_ratio,
        params.min_width_min,
        params.min_width_max,
    )
    max_width = clamp_int(
        short_axis * params.max_width_ratio,
        min_width + 1,
        max(params.max_width_floor, int(short_axis * params.max_width_cap_ratio)),
    )
    max_core_width = max(float(min_width), float(short_axis) * params.core_width_cap_ratio)
    return min_width, max_width, max_core_width


def collect_separator_width_bands(
    profile: np.ndarray,
    short_axis: float,
    coordinate_limit: float,
    params: SeparatorWidthProfileSearchParameters | None = None,
) -> tuple[list[SeparatorBand], float]:
    params = params or SeparatorWidthProfileSearchParameters()
    if profile.size <= 0:
        return [], 0.0
    edge_margin = clamp_float(
        short_axis * params.edge_margin_ratio,
        params.edge_margin_min,
        max(params.edge_margin_min, short_axis * params.edge_margin_cap_ratio),
    )
    min_width, max_width, _max_core_width = separator_width_bounds(short_axis, params)
    bands: list[SeparatorBand] = []
    for run_start, run_end in runs_from_mask(profile >= params.threshold_ratio):
        width = int(run_end - run_start)
        if width < min_width or width > max_width:
            continue
        center = (float(run_start) + float(run_end) - 1.0) * 0.5
        if center < edge_margin or center > coordinate_limit - edge_margin:
            continue
        bands.append(
            SeparatorBand(
                start=float(run_start),
                end=float(run_end),
                center=center,
                width=float(width),
                score=float(profile[run_start:run_end].mean()),
            )
        )
    return bands, edge_margin


def separator_width_gap_window(
    profile_length: int,
    expected: float,
    pitch: float,
    params: SeparatorWidthProfileSearchParameters,
) -> tuple[int, int]:
    window = clamp_int(
        pitch * params.gap_window_ratio,
        params.gap_window_min,
        max(params.gap_window_floor, int(pitch * params.gap_window_cap_ratio)),
    )
    lo = max(0, int(round(expected - window)))
    hi = min(profile_length, int(round(expected + window)))
    return lo, hi


def separator_width_gap_candidate_from_run(
    profile: np.ndarray,
    start: int,
    end: int,
    expected: float,
    pitch: float,
    min_width: int,
    max_width: int,
    params: SeparatorWidthProfileSearchParameters,
) -> Optional[SeparatorWidthGapCandidate]:
    width = end - start
    if width < min_width or width > max_width:
        return None
    mean_score = float(profile[start:end].mean())
    center = (start + end - 1) * 0.5
    distance_penalty = abs(center - expected) / max(1.0, pitch)
    score = mean_score - params.gap_distance_penalty_weight * distance_penalty
    return SeparatorWidthGapCandidate(score=score, start=start, end=end, center=float(center))


def best_separator_width_gap_candidate(
    profile: np.ndarray,
    lo: int,
    hi: int,
    expected: float,
    pitch: float,
    min_width: int,
    max_width: int,
    params: SeparatorWidthProfileSearchParameters,
) -> Optional[SeparatorWidthGapCandidate]:
    best: Optional[SeparatorWidthGapCandidate] = None
    for run_start, run_end in runs_from_mask(profile[lo:hi] >= params.threshold_ratio):
        candidate = separator_width_gap_candidate_from_run(
            profile,
            lo + int(run_start),
            lo + int(run_end),
            expected,
            pitch,
            min_width,
            max_width,
            params,
        )
        if candidate is not None and (best is None or candidate.score > best.score):
            best = candidate
    return best


def separator_width_gap_from_candidate(
    index: int,
    candidate: SeparatorWidthGapCandidate,
    profile_length: int,
    max_core_width: float,
    params: SeparatorWidthProfileSearchParameters,
) -> Gap:
    start = candidate.start
    end = candidate.end
    if (end - start) > max_core_width:
        half_width = max_core_width * 0.5
        start = int(round(max(0.0, candidate.center - half_width)))
        end = int(round(min(float(profile_length), candidate.center + half_width)))
    return Gap(
        index,
        float(candidate.center),
        float(params.gap_score_base + max(0.0, candidate.score)),
        GAP_DETECTED,
        float(start),
        float(end),
    )


def separator_width_gap_at(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    short_axis: float,
    params: SeparatorWidthProfileSearchParameters | None = None,
) -> Optional[Gap]:
    params = params or SeparatorWidthProfileSearchParameters()
    if profile.size <= 0 or pitch <= 0:
        return None
    min_width, max_width, max_core_width = separator_width_bounds(short_axis, params)
    lo, hi = separator_width_gap_window(len(profile), expected, pitch, params)
    candidate = best_separator_width_gap_candidate(
        profile,
        lo,
        hi,
        expected,
        pitch,
        min_width,
        max_width,
        params,
    )
    if candidate is None:
        return None
    return separator_width_gap_from_candidate(index, candidate, len(profile), max_core_width, params)


__all__ = [
    "SeparatorWidthGapCandidate",
    "best_separator_width_gap_candidate",
    "collect_separator_width_bands",
    "separator_width_gap_candidate_from_run",
    "separator_width_gap_from_candidate",
    "separator_width_gap_window",
    "separator_width_bounds",
    "separator_width_gap_at",
    "separator_width_profile",
]
