from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..constants import GAP_DETECTED
from ..domain import MeasurementProvenance, SeparatorBandObservation
from ..units import ScanCalibration
from ..utils import clamp_int, runs_from_mask
from .detection_parameters import GapSearchParameters


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


@dataclass(frozen=True)
class GapSearchResult:
    detected_gap: Optional[SeparatorBandObservation]
    model_gap_score: float
    reason: str


@dataclass(frozen=True)
class GapSearchContext:
    local: np.ndarray
    lo: int
    expected: float
    pitch: float
    limits: GapWidthLimits
    thresholds: GapScoreThresholds
    acceptance: GapAcceptanceLimits
    quality_prominence_weight: float
    max_width_ratio_override: Optional[float]


def gap_search_window(
    profile_length: int,
    expected: float,
    pitch: float,
    config: GapSearchParameters,
    calibration: ScanCalibration,
    axis: str,
) -> GapSearchWindow:
    radius = config.radius.resolve_px(
        calibration,
        axis=axis,
        reference_px=pitch,
    )
    lo = max(1, int(round(expected)) - radius)
    hi = min(profile_length - 1, int(round(expected)) + radius + 1)
    return GapSearchWindow(int(lo), int(hi))


def gap_width_limits(
    pitch: float,
    max_width_ratio_override: Optional[float],
    config: GapSearchParameters,
    calibration: ScanCalibration,
    axis: str,
) -> GapWidthLimits:
    normal_max_gap_w = config.max_width.resolve_px(
        calibration,
        axis=axis,
        reference_px=pitch,
    )
    max_gap_w = (
        normal_max_gap_w
        if max_width_ratio_override is None
        else clamp_int(
            pitch * max_width_ratio_override,
            config.max_width.min_px,
            config.max_width.max_px,
        )
    )
    min_gap_w = config.min_width.resolve_px(
        calibration,
        axis=axis,
        reference_px=pitch,
    )
    guard_w = config.guard.resolve_px(
        calibration,
        axis=axis,
        reference_px=pitch,
    )
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


def gap_search_context(
    local: np.ndarray,
    lo: int,
    expected: float,
    pitch: float,
    local_max: float,
    max_width_ratio_override: Optional[float],
    config: GapSearchParameters,
    calibration: ScanCalibration,
    axis: str,
) -> GapSearchContext:
    limits = gap_width_limits(
        pitch,
        max_width_ratio_override,
        config,
        calibration,
        axis,
    )
    thresholds = gap_score_thresholds(local_max, config)
    return GapSearchContext(
        local=local,
        lo=int(lo),
        expected=float(expected),
        pitch=float(pitch),
        limits=limits,
        thresholds=thresholds,
        acceptance=gap_acceptance_limits(config),
        quality_prominence_weight=float(config.quality_prominence_weight),
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
        prominence=mean_score - side_score,
    )
    acceptance = detected_gap_acceptance(evidence, context)
    return DetectedGapBandAssessment(acceptance.accepted, acceptance.reason, evidence)


def detected_gap_candidate_from_evidence(
    evidence: DetectedGapBandEvidence,
    context: GapSearchContext,
) -> DetectedGapCandidate:
    distance = abs(evidence.center - context.expected) / max(1.0, context.pitch)
    quality = (
        evidence.mean_score
        + context.quality_prominence_weight * evidence.prominence
    )
    return DetectedGapCandidate(distance, quality, evidence.mean_score, evidence.center, evidence.start, evidence.end)


def detected_gap_run_assessment(
    run_start: int,
    run_end: int,
    context: GapSearchContext,
) -> DetectedGapCandidate | None:
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
    if not assessment.accepted or assessment.evidence is None:
        return None
    return detected_gap_candidate_from_evidence(assessment.evidence, context)


def detected_gap_candidates(
    context: GapSearchContext,
) -> list[DetectedGapCandidate]:
    candidates: list[DetectedGapCandidate] = []
    for run_start, run_end in runs_from_mask(context.local >= context.thresholds.peak):
        candidate = detected_gap_run_assessment(run_start, run_end, context)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def best_detected_gap_candidate(candidates: list[DetectedGapCandidate]) -> Optional[DetectedGapCandidate]:
    if not candidates:
        return None
    return min(candidates, key=lambda item: item.rank_key())


def detected_gap_from_candidate(index: int, candidate: DetectedGapCandidate) -> SeparatorBandObservation:
    return SeparatorBandObservation(
        index=index,
        center=candidate.center,
        score=float(candidate.quality),
        method=candidate.method,
        provenance=MeasurementProvenance(
            root_measurement="separator_profile",
            source="detected_band",
            dependencies=("gray_work", "film_span"),
        ),
        start=candidate.start,
        end=candidate.end,
        tonal_evidence=float(candidate.quality),
    )


def find_detected_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    gap_search: GapSearchParameters,
    calibration: ScanCalibration,
    axis: str,
    *,
    max_width_ratio_override: Optional[float] = None,
) -> GapSearchResult:
    window = gap_search_window(
        len(profile),
        expected,
        pitch,
        gap_search,
        calibration,
        axis,
    )
    if window.empty:
        return GapSearchResult(None, 0.0, "empty_window")
    local = profile[window.lo:window.hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = gap_search.min_score
    if local.size == 0 or local_max < min_score:
        return GapSearchResult(None, local_max, "below_min_score")

    context = gap_search_context(
        local,
        window.lo,
        expected,
        pitch,
        local_max,
        max_width_ratio_override,
        gap_search,
        calibration,
        axis,
    )
    candidate = best_detected_gap_candidate(detected_gap_candidates(context))
    if candidate is not None:
        return GapSearchResult(
            detected_gap_from_candidate(index, candidate),
            local_max,
            GAP_DETECTED,
        )

    return GapSearchResult(
        None,
        local_max,
        "no_detected_candidate",
    )
