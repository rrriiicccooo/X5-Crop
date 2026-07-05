from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..constants import GAP_DETECTED
from ..domain import Gap
from ..utils import clamp_float, clamp_int, runs_from_mask, sampled_percentile, smooth_1d
from .detection_parameters import SeparatorWidthProfileSearchParameters
from .gap_search_detail import attach_gap_run_evaluation_summary
from .separator_band import SeparatorBand


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
class SeparatorWidthBandCollection:
    bands: list[SeparatorBand]
    edge_margin: float


@dataclass(frozen=True)
class SeparatorWidthGapWindow:
    lo: int
    hi: int


@dataclass(frozen=True)
class SeparatorWidthGapAcceptance:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class SeparatorWidthGapRunAssessment:
    accepted: bool
    reason: str
    run: SeparatorWidthGapRun
    mean_score: float = 0.0
    distance_penalty: float = 0.0
    candidate_score: float | None = None

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "accepted": bool(self.accepted),
            "reason": self.reason,
            "start": int(self.run.start),
            "end": int(self.run.end),
            "width": int(self.run.width),
            "center": float(self.run.center),
            "mean_score": float(self.mean_score),
            "distance_penalty": float(self.distance_penalty),
        }
        if self.candidate_score is not None:
            out["candidate_score"] = float(self.candidate_score)
        return out


@dataclass(frozen=True)
class SeparatorWidthGapCandidateAssessmentResult:
    candidate: Optional[SeparatorWidthGapCandidate]
    assessment: SeparatorWidthGapRunAssessment


@dataclass(frozen=True)
class SeparatorWidthGapCandidateSearchResult:
    candidates: list[SeparatorWidthGapCandidate]
    evaluations: list[dict[str, Any]]


@dataclass(frozen=True)
class SeparatorWidthGapBestCandidateResult:
    candidate: Optional[SeparatorWidthGapCandidate]
    evaluations: list[dict[str, Any]]


@dataclass(frozen=True)
class SeparatorWidthGapSearchResult:
    gap: Optional[Gap]
    reason: str
    detail: dict[str, Any]


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
) -> SeparatorWidthBounds:
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
    return SeparatorWidthBounds(
        min_width=int(min_width),
        max_width=int(max_width),
        max_core_width=float(max_core_width),
    )


def collect_separator_width_bands(
    profile: np.ndarray,
    short_axis: float,
    coordinate_limit: float,
    params: SeparatorWidthProfileSearchParameters | None = None,
) -> SeparatorWidthBandCollection:
    params = params or SeparatorWidthProfileSearchParameters()
    if profile.size <= 0:
        return SeparatorWidthBandCollection([], 0.0)
    edge_margin = clamp_float(
        short_axis * params.edge_margin_ratio,
        params.edge_margin_min,
        max(params.edge_margin_min, short_axis * params.edge_margin_cap_ratio),
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
    return SeparatorWidthBandCollection(bands, float(edge_margin))


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


def separator_width_gap_candidate_assessment(
    profile: np.ndarray,
    start: int,
    end: int,
    expected: float,
    pitch: float,
    bounds: SeparatorWidthBounds,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapCandidateAssessmentResult:
    run = separator_width_gap_run(start, end)
    acceptance = separator_width_gap_run_acceptance(run, bounds)
    mean_score = float(profile[run.start:run.end].mean()) if run.end > run.start else 0.0
    distance_penalty = abs(run.center - expected) / max(1.0, pitch)
    if not acceptance.accepted:
        return SeparatorWidthGapCandidateAssessmentResult(
            candidate=None,
            assessment=SeparatorWidthGapRunAssessment(
                accepted=False,
                reason=acceptance.reason,
                run=run,
                mean_score=mean_score,
                distance_penalty=distance_penalty,
            ),
        )
    candidate = separator_width_gap_candidate_from_accepted_run(profile, run, expected, pitch, params)
    return SeparatorWidthGapCandidateAssessmentResult(
        candidate=candidate,
        assessment=SeparatorWidthGapRunAssessment(
            accepted=True,
            reason=acceptance.reason,
            run=run,
            mean_score=mean_score,
            distance_penalty=distance_penalty,
            candidate_score=float(candidate.score),
        ),
    )


def separator_width_gap_candidates_with_detail(
    profile: np.ndarray,
    window: SeparatorWidthGapWindow,
    expected: float,
    pitch: float,
    bounds: SeparatorWidthBounds,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapCandidateSearchResult:
    candidates: list[SeparatorWidthGapCandidate] = []
    evaluations: list[dict[str, Any]] = []
    for run_start, run_end in runs_from_mask(profile[window.lo:window.hi] >= params.threshold_ratio):
        assessment_result = separator_width_gap_candidate_assessment(
            profile,
            window.lo + int(run_start),
            window.lo + int(run_end),
            expected,
            pitch,
            bounds,
            params,
        )
        evaluations.append(assessment_result.assessment.detail())
        if assessment_result.candidate is not None:
            candidates.append(assessment_result.candidate)
    return SeparatorWidthGapCandidateSearchResult(candidates, evaluations)


def best_separator_width_gap_candidate_with_detail(
    profile: np.ndarray,
    window: SeparatorWidthGapWindow,
    expected: float,
    pitch: float,
    bounds: SeparatorWidthBounds,
    params: SeparatorWidthProfileSearchParameters,
) -> SeparatorWidthGapBestCandidateResult:
    search = separator_width_gap_candidates_with_detail(
        profile,
        window,
        expected,
        pitch,
        bounds,
        params,
    )
    best: Optional[SeparatorWidthGapCandidate] = None
    for candidate in search.candidates:
        if best is None or candidate.rank_key() > best.rank_key():
            best = candidate
    return SeparatorWidthGapBestCandidateResult(best, search.evaluations)


def separator_width_gap_from_candidate(
    index: int,
    candidate: SeparatorWidthGapCandidate,
    profile_length: int,
    bounds: SeparatorWidthBounds,
    params: SeparatorWidthProfileSearchParameters,
) -> Gap:
    start = candidate.start
    end = candidate.end
    if (end - start) > bounds.max_core_width:
        half_width = bounds.max_core_width * 0.5
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


def separator_width_gap_search_detail(
    index: int,
    expected: float,
    pitch: float,
    profile_length: int,
    short_axis: float,
    bounds: SeparatorWidthBounds,
    window: SeparatorWidthGapWindow,
    evaluations: list[dict[str, Any]] | None = None,
    selected: SeparatorWidthGapCandidate | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "index": int(index),
        "expected": float(expected),
        "pitch": float(pitch),
        "profile_length": int(profile_length),
        "short_axis": float(short_axis),
        "window": {"lo": int(window.lo), "hi": int(window.hi)},
        "min_width": int(bounds.min_width),
        "max_width": int(bounds.max_width),
        "max_core_width": float(bounds.max_core_width),
    }
    detail = attach_gap_run_evaluation_summary(detail, evaluations)
    if selected is not None:
        detail["selected"] = {
            "center": float(selected.center),
            "start": int(selected.start),
            "end": int(selected.end),
            "width": int(selected.end - selected.start),
            "score": float(selected.score),
        }
    return detail


def separator_width_gap_at_with_detail(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    short_axis: float,
    params: SeparatorWidthProfileSearchParameters | None = None,
) -> SeparatorWidthGapSearchResult:
    params = params or SeparatorWidthProfileSearchParameters()
    if profile.size <= 0 or pitch <= 0:
        detail = {
            "index": int(index),
            "expected": float(expected),
            "pitch": float(pitch),
            "profile_length": int(profile.size),
            "short_axis": float(short_axis),
        }
        return SeparatorWidthGapSearchResult(None, "empty_profile_or_pitch", detail)
    bounds = separator_width_bounds(short_axis, params)
    window = separator_width_gap_window(len(profile), expected, pitch, params)
    selection = best_separator_width_gap_candidate_with_detail(
        profile,
        window,
        expected,
        pitch,
        bounds,
        params,
    )
    detail = separator_width_gap_search_detail(
        index,
        expected,
        pitch,
        len(profile),
        short_axis,
        bounds,
        window,
        selection.evaluations,
        selection.candidate,
    )
    if selection.candidate is None:
        return SeparatorWidthGapSearchResult(None, "no_width_profile_candidate", detail)
    return SeparatorWidthGapSearchResult(
        separator_width_gap_from_candidate(index, selection.candidate, len(profile), bounds, params),
        "detected",
        detail,
    )


__all__ = [
    "SeparatorWidthGapAcceptance",
    "SeparatorWidthBandCollection",
    "SeparatorWidthGapBestCandidateResult",
    "SeparatorWidthBounds",
    "SeparatorWidthGapCandidate",
    "SeparatorWidthGapCandidateAssessmentResult",
    "SeparatorWidthGapCandidateSearchResult",
    "SeparatorWidthGapWindow",
    "SeparatorWidthGapRun",
    "SeparatorWidthGapRunAssessment",
    "SeparatorWidthGapSearchResult",
    "best_separator_width_gap_candidate_with_detail",
    "collect_separator_width_bands",
    "separator_width_gap_candidate_from_accepted_run",
    "separator_width_gap_candidate_assessment",
    "separator_width_gap_candidates_with_detail",
    "separator_width_gap_from_candidate",
    "separator_width_gap_run",
    "separator_width_gap_run_acceptance",
    "separator_width_gap_search_detail",
    "separator_width_gap_window",
    "separator_width_bounds",
    "separator_width_gap_at_with_detail",
    "separator_width_profile",
]
