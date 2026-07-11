from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..constants import GAP_DETECTED
from ..domain import MeasurementProvenance, SeparatorBandObservation
from ..utils import clamp_int, runs_from_mask, sampled_percentile, smooth_1d
from .detection_parameters import SeparatorWidthProfileSearchParameters
from .separator_band import SeparatorBand, SeparatorBandCollection
from ..units import ScanCalibration
from .sampling import sampling_step_for_limit


@dataclass(frozen=True)
class SeparatorWidthGapCandidate:
    score: float
    start: int
    end: int
    center: float

    def rank_key(self) -> tuple[float]:
        return (self.score,)


@dataclass(frozen=True)
class SeparatorWidthGapRun:
    start: int
    end: int
    width: int
    center: float


@dataclass(frozen=True)
class SeparatorWidthBounds:
    min_width: int
    max_width: int
    max_core_width: float


@dataclass(frozen=True)
class SeparatorWidthGapWindow:
    lo: int
    hi: int

    @property
    def empty(self) -> bool:
        return self.hi <= self.lo


@dataclass(frozen=True)
class SeparatorWidthGapAcceptance:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class SeparatorWidthGapSearchResult:
    gap: SeparatorBandObservation | None
    reason: str


def separator_width_profile(
    crop: np.ndarray,
    params: SeparatorWidthProfileSearchParameters,
) -> np.ndarray:
    if crop.size == 0:
        return np.array([], dtype=np.float32)
    short_axis_step = sampling_step_for_limit(
        crop.shape[0],
        params.sample_short_axis_max,
    )
    long_axis_step = sampling_step_for_limit(
        crop.shape[1],
        params.sample_long_axis_max,
    )
    profile_sample = crop[::short_axis_step, :]
    percentile_sample = profile_sample[:, ::long_axis_step]
    low, high = sampled_percentile(percentile_sample, params.normalization_percentiles)
    span = max(1.0, float(high - low))
    threshold = float(low) + span * params.threshold_span_ratio
    profile = (profile_sample <= threshold).mean(axis=0).astype(np.float32)
    return smooth_1d(
        profile,
        max(
            params.profile_smooth_min,
            int(round(crop.shape[0] * params.profile_smooth_short_axis_ratio)),
        ),
    )


def separator_width_bounds(
    short_axis: float,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthBounds:
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
    return SeparatorWidthBounds(
        min_width=int(min_width),
        max_width=int(max_width),
        max_core_width=float(max_core_width),
    )


def collect_separator_width_bands(
    profile: np.ndarray,
    short_axis: float,
    coordinate_limit: float,
    params: SeparatorWidthProfileSearchParameters,
    calibration: ScanCalibration,
    long_axis: str,
) -> SeparatorBandCollection:
    if profile.size <= 0:
        return SeparatorBandCollection([], 0.0)
    edge_margin = params.edge_margin.resolve_px(
        calibration,
        axis=long_axis,
        reference_px=short_axis,
    )
    bounds = separator_width_bounds(short_axis, params)
    bands: list[SeparatorBand] = []
    for run_start, run_end in runs_from_mask(profile >= params.threshold_ratio):
        width = int(run_end - run_start)
        if width < bounds.min_width or width > bounds.max_width:
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
    return SeparatorBandCollection(bands, float(edge_margin))


def separator_width_gap_window(
    profile_length: int,
    expected: float,
    pitch: float,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapWindow:
    window = clamp_int(
        pitch * params.gap_window_ratio,
        params.gap_window_min,
        max(params.gap_window_floor, int(pitch * params.gap_window_cap_ratio)),
    )
    lo = max(0, int(round(expected - window)))
    hi = min(profile_length, int(round(expected + window)))
    return SeparatorWidthGapWindow(lo=int(lo), hi=int(hi))


def separator_width_gap_run(start: int, end: int) -> SeparatorWidthGapRun:
    width = int(end - start)
    center = (float(start) + float(end) - 1.0) * 0.5
    return SeparatorWidthGapRun(start=int(start), end=int(end), width=width, center=float(center))


def separator_width_gap_run_acceptance(
    run: SeparatorWidthGapRun,
    bounds: SeparatorWidthBounds,
) -> SeparatorWidthGapAcceptance:
    if run.width < bounds.min_width:
        return SeparatorWidthGapAcceptance(False, "too_narrow")
    if run.width > bounds.max_width:
        return SeparatorWidthGapAcceptance(False, "too_wide")
    return SeparatorWidthGapAcceptance(True, "accepted")


def separator_width_gap_candidate_from_accepted_run(
    profile: np.ndarray,
    run: SeparatorWidthGapRun,
    expected: float,
    pitch: float,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapCandidate:
    mean_score = float(profile[run.start:run.end].mean())
    distance_penalty = abs(run.center - expected) / max(1.0, pitch)
    score = mean_score - params.gap_distance_penalty_weight * distance_penalty
    return SeparatorWidthGapCandidate(score=score, start=run.start, end=run.end, center=run.center)


def separator_width_gap_candidate(
    profile: np.ndarray,
    start: int,
    end: int,
    expected: float,
    pitch: float,
    bounds: SeparatorWidthBounds,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapCandidate | None:
    run = separator_width_gap_run(start, end)
    acceptance = separator_width_gap_run_acceptance(run, bounds)
    if not acceptance.accepted:
        return None
    return separator_width_gap_candidate_from_accepted_run(
        profile,
        run,
        expected,
        pitch,
        params,
    )


def separator_width_gap_candidates(
    profile: np.ndarray,
    window: SeparatorWidthGapWindow,
    expected: float,
    pitch: float,
    bounds: SeparatorWidthBounds,
    params: SeparatorWidthProfileSearchParameters,
) -> tuple[SeparatorWidthGapCandidate, ...]:
    candidates: list[SeparatorWidthGapCandidate] = []
    if window.empty:
        return ()
    for run_start, run_end in runs_from_mask(profile[window.lo:window.hi] >= params.threshold_ratio):
        candidate = separator_width_gap_candidate(
            profile,
            window.lo + int(run_start),
            window.lo + int(run_end),
            expected,
            pitch,
            bounds,
            params,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def best_separator_width_gap_candidate(
    candidates: tuple[SeparatorWidthGapCandidate, ...],
) -> SeparatorWidthGapCandidate | None:
    best: SeparatorWidthGapCandidate | None = None
    for candidate in candidates:
        if best is None or candidate.rank_key() > best.rank_key():
            best = candidate
    return best


def separator_width_gap_from_candidate(
    index: int,
    candidate: SeparatorWidthGapCandidate,
    profile_length: int,
    bounds: SeparatorWidthBounds,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorBandObservation:
    start = candidate.start
    end = candidate.end
    if (end - start) > bounds.max_core_width:
        half_width = bounds.max_core_width * 0.5
        start = int(round(max(0.0, candidate.center - half_width)))
        end = int(round(min(float(profile_length), candidate.center + half_width)))
    return SeparatorBandObservation(
        index=index,
        center=float(candidate.center),
        score=float(params.gap_score_base + max(0.0, candidate.score)),
        method=GAP_DETECTED,
        provenance=MeasurementProvenance(
            root_measurement="separator_width_profile",
            source="observed_width_band",
            dependencies=("gray_work", "film_span"),
        ),
        start=float(start),
        end=float(end),
        tonal_evidence=float(candidate.score),
    )


def separator_width_gap_at(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    short_axis: float,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapSearchResult:
    if profile.size <= 0 or pitch <= 0:
        return SeparatorWidthGapSearchResult(None, "empty_profile_or_pitch")
    bounds = separator_width_bounds(short_axis, params)
    window = separator_width_gap_window(len(profile), expected, pitch, params)
    search = separator_width_gap_candidates(
        profile,
        window,
        expected,
        pitch,
        bounds,
        params,
    )
    candidate = best_separator_width_gap_candidate(search)
    if candidate is None:
        return SeparatorWidthGapSearchResult(None, "no_width_profile_candidate")
    return SeparatorWidthGapSearchResult(
        separator_width_gap_from_candidate(index, candidate, len(profile), bounds, params),
        GAP_DETECTED,
    )
