from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ..constants import GAP_DETECTED
from ..domain import Gap
from ..utils import clamp_int, runs_from_mask
from .detection_parameters import GapSearchParameters
from .gap_search_detail import attach_gap_run_evaluation_summary


@dataclass(frozen=True)
class GapWidthLimits:
    normal_max: int
    max_width: int
    min_width: int
    guard: int


@dataclass(frozen=True)
class GapScoreThresholds:
    min_score: float
    peak: float
    band: float


@dataclass(frozen=True)
class GapAcceptanceLimits:
    weak_prominence_min: float
    weak_prominence_mean_override: float
    separator_width_min_mean: float
    separator_width_min_prominence: float


@dataclass(frozen=True)
class GapRankingWeights:
    quality_prominence_weight: float


@dataclass(frozen=True)
class GapSearchWindow:
    lo: int
    hi: int

    @property
    def empty(self) -> bool:
        return self.hi <= self.lo


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


@dataclass(frozen=True)
class DetectedGapBandEvidence:
    center: float
    start: float
    end: float
    width: int
    mean_score: float
    side_score: float
    prominence: float


@dataclass(frozen=True)
class DetectedGapAcceptance:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class DetectedGapBandAssessment:
    accepted: bool
    reason: str
    evidence: Optional[DetectedGapBandEvidence] = None

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "accepted": bool(self.accepted),
            "reason": self.reason,
        }
        if self.evidence is not None:
            out.update(
                {
                    "center": float(self.evidence.center),
                    "start": float(self.evidence.start),
                    "end": float(self.evidence.end),
                    "width": int(self.evidence.width),
                    "mean_score": float(self.evidence.mean_score),
                    "side_score": float(self.evidence.side_score),
                    "prominence": float(self.evidence.prominence),
                }
            )
        return out


@dataclass(frozen=True)
class DetectedGapRunAssessment:
    candidate: Optional[DetectedGapCandidate]
    detail: dict[str, Any]


@dataclass(frozen=True)
class DetectedGapCandidateSearchResult:
    candidates: list[DetectedGapCandidate]
    evaluations: list[dict[str, Any]]


@dataclass(frozen=True)
class GapSearchResult:
    detected_gap: Optional[Gap]
    model_gap_score: float
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GapSearchContext:
    local: np.ndarray
    lo: int
    expected: float
    pitch: float
    limits: GapWidthLimits
    thresholds: GapScoreThresholds
    acceptance: GapAcceptanceLimits
    ranking: GapRankingWeights
    max_width_ratio_override: Optional[float]


def gap_search_window(
    profile_length: int,
    expected: float,
    pitch: float,
    config: GapSearchParameters,
) -> GapSearchWindow:
    radius = clamp_int(pitch * config.radius_ratio, config.radius_min, config.radius_max)
    lo = max(1, int(round(expected)) - radius)
    hi = min(profile_length - 1, int(round(expected)) + radius + 1)
    return GapSearchWindow(int(lo), int(hi))


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


def gap_score_thresholds(local_max: float, config: GapSearchParameters) -> GapScoreThresholds:
    min_score = config.min_score
    peak_threshold = max(min_score, local_max * config.peak_multiplier)
    band_threshold = max(min_score * config.band_min_score_multiplier, local_max * config.band_multiplier)
    return GapScoreThresholds(
        min_score=float(min_score),
        peak=float(peak_threshold),
        band=float(band_threshold),
    )


def gap_acceptance_limits(config: GapSearchParameters) -> GapAcceptanceLimits:
    return GapAcceptanceLimits(
        weak_prominence_min=float(config.weak_prominence_min),
        weak_prominence_mean_override=float(config.weak_prominence_mean_override),
        separator_width_min_mean=float(config.separator_width_min_mean),
        separator_width_min_prominence=float(config.separator_width_min_prominence),
    )


def gap_ranking_weights(config: GapSearchParameters) -> GapRankingWeights:
    return GapRankingWeights(
        quality_prominence_weight=float(config.quality_prominence_weight),
    )


def gap_search_context(
    local: np.ndarray,
    lo: int,
    expected: float,
    pitch: float,
    local_max: float,
    max_width_ratio_override: Optional[float],
    config: GapSearchParameters,
) -> GapSearchContext:
    limits = gap_width_limits(pitch, max_width_ratio_override, config)
    thresholds = gap_score_thresholds(local_max, config)
    return GapSearchContext(
        local=local,
        lo=int(lo),
        expected=float(expected),
        pitch=float(pitch),
        limits=limits,
        thresholds=thresholds,
        acceptance=gap_acceptance_limits(config),
        ranking=gap_ranking_weights(config),
        max_width_ratio_override=max_width_ratio_override,
    )


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


def gap_band_has_prominence(evidence: DetectedGapBandEvidence, limits: GapAcceptanceLimits) -> bool:
    return (
        evidence.prominence >= limits.weak_prominence_min
        or evidence.mean_score >= limits.weak_prominence_mean_override
    )


def gap_band_has_width_profile_support(
    evidence: DetectedGapBandEvidence,
    limits: GapWidthLimits,
    max_width_ratio_override: Optional[float],
    acceptance: GapAcceptanceLimits,
) -> bool:
    if max_width_ratio_override is None or evidence.width <= limits.normal_max:
        return True
    return (
        evidence.mean_score >= acceptance.separator_width_min_mean
        and evidence.prominence >= acceptance.separator_width_min_prominence
    )


def detected_gap_acceptance(
    evidence: DetectedGapBandEvidence,
    context: GapSearchContext,
) -> DetectedGapAcceptance:
    if not gap_band_has_prominence(evidence, context.acceptance):
        return DetectedGapAcceptance(False, "weak_prominence")
    if not gap_band_has_width_profile_support(
        evidence,
        context.limits,
        context.max_width_ratio_override,
        context.acceptance,
    ):
        return DetectedGapAcceptance(False, "width_profile_unsupported")
    return DetectedGapAcceptance(True, "accepted")


def detected_gap_band_assessment(
    local: np.ndarray,
    lo: int,
    band_start: int,
    band_end: int,
    context: GapSearchContext,
) -> DetectedGapBandAssessment:
    band_width = band_end - band_start
    if band_width < context.limits.min_width:
        return DetectedGapBandAssessment(False, "width_too_narrow")
    if band_width > context.limits.max_width:
        return DetectedGapBandAssessment(False, "width_too_wide")

    left_guard = local[max(0, band_start - context.limits.guard):band_start]
    right_guard = local[band_end:min(len(local), band_end + context.limits.guard)]
    if left_guard.size == 0 or right_guard.size == 0:
        return DetectedGapBandAssessment(False, "missing_guard")

    mean_score = float(local[band_start:band_end].mean())
    side_score = max(float(left_guard.mean()), float(right_guard.mean()))
    evidence = DetectedGapBandEvidence(
        center=float(lo + (band_start + band_end - 1) / 2.0),
        start=float(lo + band_start),
        end=float(lo + band_end),
        width=band_width,
        mean_score=mean_score,
        side_score=side_score,
        prominence=mean_score - side_score,
    )
    acceptance = detected_gap_acceptance(evidence, context)
    return DetectedGapBandAssessment(acceptance.accepted, acceptance.reason, evidence)


def detected_gap_candidate_from_evidence(
    evidence: DetectedGapBandEvidence,
    context: GapSearchContext,
) -> DetectedGapCandidate:
    distance = abs(evidence.center - context.expected) / max(1.0, context.pitch)
    quality = evidence.mean_score + context.ranking.quality_prominence_weight * evidence.prominence
    return DetectedGapCandidate(distance, quality, evidence.mean_score, evidence.center, evidence.start, evidence.end)


def detected_gap_run_assessment(
    run_start: int,
    run_end: int,
    context: GapSearchContext,
) -> DetectedGapRunAssessment:
    band_start, band_end = expanded_gap_band(
        context.local,
        run_start,
        run_end,
        context.thresholds.band,
        context.limits.max_width,
    )
    assessment = detected_gap_band_assessment(
        context.local,
        context.lo,
        band_start,
        band_end,
        context,
    )
    detail = {
        "run_start": int(context.lo + run_start),
        "run_end": int(context.lo + run_end),
        "band_start": int(context.lo + band_start),
        "band_end": int(context.lo + band_end),
    }
    detail.update(assessment.detail())
    if not assessment.accepted or assessment.evidence is None:
        return DetectedGapRunAssessment(None, detail)
    candidate = detected_gap_candidate_from_evidence(assessment.evidence, context)
    detail["distance"] = float(candidate.distance)
    detail["quality"] = float(candidate.quality)
    return DetectedGapRunAssessment(candidate, detail)


def detected_gap_candidates_with_detail(
    context: GapSearchContext,
) -> DetectedGapCandidateSearchResult:
    candidates: list[DetectedGapCandidate] = []
    evaluations: list[dict[str, Any]] = []
    for run_start, run_end in runs_from_mask(context.local >= context.thresholds.peak):
        assessment = detected_gap_run_assessment(run_start, run_end, context)
        evaluations.append(assessment.detail)
        if assessment.candidate is not None:
            candidates.append(assessment.candidate)
    return DetectedGapCandidateSearchResult(candidates, evaluations)


def best_detected_gap_candidate(candidates: list[DetectedGapCandidate]) -> Optional[DetectedGapCandidate]:
    if not candidates:
        return None
    return min(candidates, key=lambda item: item.rank_key())


def detected_gap_from_candidate(index: int, candidate: DetectedGapCandidate) -> Gap:
    return Gap(index, candidate.center, float(candidate.quality), candidate.method, candidate.start, candidate.end)


def gap_search_detail(
    index: int,
    expected: float,
    pitch: float,
    window: GapSearchWindow,
    local_max: float,
    context: GapSearchContext | None,
    evaluations: list[dict[str, Any]] | None = None,
    selected: DetectedGapCandidate | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "index": int(index),
        "expected": float(expected),
        "pitch": float(pitch),
        "window": {"lo": int(window.lo), "hi": int(window.hi), "local_max": float(local_max)},
    }
    if context is not None:
        detail["window"].update(
            {
                "peak_threshold": float(context.thresholds.peak),
                "band_threshold": float(context.thresholds.band),
                "min_width": int(context.limits.min_width),
                "max_width": int(context.limits.max_width),
                "normal_max_width": int(context.limits.normal_max),
                "guard": int(context.limits.guard),
                "max_width_ratio_override": context.max_width_ratio_override,
            }
        )
    detail = attach_gap_run_evaluation_summary(detail, evaluations)
    if selected is not None:
        detail["selected"] = {
            "center": float(selected.center),
            "start": float(selected.start),
            "end": float(selected.end),
            "distance": float(selected.distance),
            "quality": float(selected.quality),
            "mean_score": float(selected.mean_score),
            "method": selected.method,
        }
    return detail


def find_detected_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    gap_search: GapSearchParameters,
    *,
    max_width_ratio_override: Optional[float] = None,
) -> GapSearchResult:
    window = gap_search_window(len(profile), expected, pitch, gap_search)
    if window.empty:
        return GapSearchResult(None, 0.0, "empty_window", gap_search_detail(index, expected, pitch, window, 0.0, None))
    local = profile[window.lo:window.hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = gap_search.min_score
    if local.size == 0 or local_max < min_score:
        return GapSearchResult(None, local_max, "below_min_score", gap_search_detail(index, expected, pitch, window, local_max, None))

    context = gap_search_context(
        local,
        window.lo,
        expected,
        pitch,
        local_max,
        max_width_ratio_override,
        gap_search,
    )
    candidate_search = detected_gap_candidates_with_detail(context)
    candidate = best_detected_gap_candidate(candidate_search.candidates)
    if candidate is not None:
        return GapSearchResult(
            detected_gap_from_candidate(index, candidate),
            local_max,
            GAP_DETECTED,
            gap_search_detail(
                index,
                expected,
                pitch,
                window,
                local_max,
                context,
                candidate_search.evaluations,
                candidate,
            ),
        )

    return GapSearchResult(
        None,
        local_max,
        "no_detected_candidate",
        gap_search_detail(index, expected, pitch, window, local_max, context, candidate_search.evaluations),
    )
