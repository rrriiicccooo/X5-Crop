from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ..constants import GAP_DETECTED
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
class GapSearchResult:
    detected_gap: Optional[Gap]
    fallback_score: float
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GapSearchContext:
    local: np.ndarray
    lo: int
    expected: float
    pitch: float
    limits: GapWidthLimits
    peak_threshold: float
    band_threshold: float
    max_width_ratio_override: Optional[float]
    config: GapSearchParameters


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
    peak_threshold, band_threshold = gap_score_thresholds(local_max, config)
    return GapSearchContext(
        local=local,
        lo=int(lo),
        expected=float(expected),
        pitch=float(pitch),
        limits=limits,
        peak_threshold=float(peak_threshold),
        band_threshold=float(band_threshold),
        max_width_ratio_override=max_width_ratio_override,
        config=config,
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


def detected_gap_band_evidence(
    local: np.ndarray,
    lo: int,
    band_start: int,
    band_end: int,
    limits: GapWidthLimits,
) -> Optional[DetectedGapBandEvidence]:
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
    center = float(lo + (band_start + band_end - 1) / 2.0)
    return DetectedGapBandEvidence(
        center=center,
        start=float(lo + band_start),
        end=float(lo + band_end),
        width=band_width,
        mean_score=mean_score,
        side_score=side_score,
        prominence=prominence,
    )


def gap_band_has_prominence(evidence: DetectedGapBandEvidence, config: GapSearchParameters) -> bool:
    return (
        evidence.prominence >= config.weak_prominence_min
        or evidence.mean_score >= config.weak_prominence_mean_override
    )


def gap_band_has_width_profile_support(
    evidence: DetectedGapBandEvidence,
    limits: GapWidthLimits,
    max_width_ratio_override: Optional[float],
    config: GapSearchParameters,
) -> bool:
    if max_width_ratio_override is None or evidence.width <= limits.normal_max:
        return True
    return (
        evidence.mean_score >= config.separator_width_min_mean
        and evidence.prominence >= config.separator_width_min_prominence
    )


def detected_gap_acceptance(
    evidence: DetectedGapBandEvidence,
    context: GapSearchContext,
) -> DetectedGapAcceptance:
    if not gap_band_has_prominence(evidence, context.config):
        return DetectedGapAcceptance(False, "weak_prominence")
    if not gap_band_has_width_profile_support(
        evidence,
        context.limits,
        context.max_width_ratio_override,
        context.config,
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
    quality = evidence.mean_score + context.config.quality_prominence_weight * evidence.prominence
    return DetectedGapCandidate(distance, quality, evidence.mean_score, evidence.center, evidence.start, evidence.end)


def detected_gap_candidate_assessment(
    run_start: int,
    run_end: int,
    context: GapSearchContext,
) -> tuple[Optional[DetectedGapCandidate], dict[str, Any]]:
    band_start, band_end = expanded_gap_band(
        context.local,
        run_start,
        run_end,
        context.band_threshold,
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
        return None, detail
    candidate = detected_gap_candidate_from_evidence(assessment.evidence, context)
    detail["distance"] = float(candidate.distance)
    detail["quality"] = float(candidate.quality)
    return candidate, detail


def detected_gap_candidate(
    run_start: int,
    run_end: int,
    context: GapSearchContext,
) -> Optional[DetectedGapCandidate]:
    candidate, _detail = detected_gap_candidate_assessment(run_start, run_end, context)
    return candidate


def detected_gap_candidates_with_detail(
    context: GapSearchContext,
) -> tuple[list[DetectedGapCandidate], list[dict[str, Any]]]:
    candidates: list[DetectedGapCandidate] = []
    evaluations: list[dict[str, Any]] = []
    for run_start, run_end in runs_from_mask(context.local >= context.peak_threshold):
        candidate, detail = detected_gap_candidate_assessment(run_start, run_end, context)
        evaluations.append(detail)
        if candidate is not None:
            candidates.append(candidate)
    return candidates, evaluations


def detected_gap_candidates(
    context: GapSearchContext,
) -> list[DetectedGapCandidate]:
    candidates, _evaluations = detected_gap_candidates_with_detail(context)
    return candidates


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
    lo: int,
    hi: int,
    local_max: float,
    context: GapSearchContext | None,
    evaluations: list[dict[str, Any]] | None = None,
    selected: DetectedGapCandidate | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "index": int(index),
        "expected": float(expected),
        "pitch": float(pitch),
        "window": {"lo": int(lo), "hi": int(hi), "local_max": float(local_max)},
    }
    if context is not None:
        detail["window"].update(
            {
                "peak_threshold": float(context.peak_threshold),
                "band_threshold": float(context.band_threshold),
                "min_width": int(context.limits.min_width),
                "max_width": int(context.limits.max_width),
                "normal_max_width": int(context.limits.normal_max),
                "guard": int(context.limits.guard),
                "max_width_ratio_override": context.max_width_ratio_override,
            }
        )
    evaluations = evaluations or []
    accepted = [item for item in evaluations if bool(item.get("accepted", False))]
    rejected = [item for item in evaluations if not bool(item.get("accepted", False))]
    detail["evaluated_run_count"] = len(evaluations)
    detail["accepted_count"] = len(accepted)
    detail["rejected_count"] = len(rejected)
    detail["accepted"] = accepted[:8]
    detail["rejected"] = rejected[:8]
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
    max_width_ratio_override: Optional[float] = None,
    gap_search: GapSearchParameters | None = None,
) -> GapSearchResult:
    config = gap_search or GapSearchParameters()
    lo, hi = gap_search_window(len(profile), expected, pitch, config)
    if hi <= lo:
        return GapSearchResult(None, 0.0, "empty_window", gap_search_detail(index, expected, pitch, lo, hi, 0.0, None))
    local = profile[lo:hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = config.min_score
    if local.size == 0 or local_max < min_score:
        return GapSearchResult(None, local_max, "below_min_score", gap_search_detail(index, expected, pitch, lo, hi, local_max, None))

    context = gap_search_context(
        local,
        lo,
        expected,
        pitch,
        local_max,
        max_width_ratio_override,
        config,
    )
    candidates, evaluations = detected_gap_candidates_with_detail(context)
    candidate = best_detected_gap_candidate(candidates)
    if candidate is not None:
        return GapSearchResult(
            detected_gap_from_candidate(index, candidate),
            local_max,
            "detected",
            gap_search_detail(index, expected, pitch, lo, hi, local_max, context, evaluations, candidate),
        )

    return GapSearchResult(
        None,
        local_max,
        "no_detected_candidate",
        gap_search_detail(index, expected, pitch, lo, hi, local_max, context, evaluations),
    )


__all__ = [
    "DetectedGapAcceptance",
    "DetectedGapBandAssessment",
    "DetectedGapCandidate",
    "DetectedGapBandEvidence",
    "GapSearchContext",
    "GapSearchResult",
    "GapWidthLimits",
    "best_detected_gap_candidate",
    "detected_gap_acceptance",
    "detected_gap_band_assessment",
    "detected_gap_band_evidence",
    "detected_gap_candidate",
    "detected_gap_candidate_assessment",
    "detected_gap_candidate_from_evidence",
    "detected_gap_candidates",
    "detected_gap_candidates_with_detail",
    "detected_gap_from_candidate",
    "expanded_gap_band",
    "find_detected_gap",
    "gap_search_detail",
    "gap_band_has_prominence",
    "gap_band_has_width_profile_support",
    "gap_search_context",
    "gap_score_thresholds",
    "gap_search_window",
    "gap_width_limits",
]
