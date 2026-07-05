from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from ..domain import Box, Gap
from ..gap_methods import is_hard_gap_method
from ..utils import clamp_float
from .gap_geometry import constrain_gap_to_geometry
from .gap_trust import light_hard_gap_trust
from .model_gaps import grid_model_gap
from .detection_parameters import HardGapTrustParameters, NearbySeparatorCorrectionParameters, RobustGridParameters


GridFit = tuple[int, float, float, float]
GRID_DETAIL_LIMIT = 12


@dataclass(frozen=True)
class GridFitCandidate:
    inliers: int
    pitch: float
    origin: float
    median_residual: float

    def rank_key(self, nominal_pitch: float) -> tuple[int, float, float, float]:
        return (
            self.inliers,
            -self.median_residual,
            -abs(self.pitch - nominal_pitch),
            self.pitch,
        )

    def as_grid_fit(self) -> GridFit:
        return (
            int(self.inliers),
            float(self.pitch),
            float(self.origin),
            float(self.median_residual),
        )

    def detail(self, nominal_pitch: float) -> dict[str, Any]:
        return {
            "inliers": int(self.inliers),
            "pitch": float(self.pitch),
            "origin": float(self.origin),
            "median_residual": float(self.median_residual),
            "pitch_delta": float(self.pitch - nominal_pitch),
        }


@dataclass(frozen=True)
class GridFitAssessment:
    accepted: bool
    reason: str
    residual_threshold: float

    def detail(self) -> dict[str, Any]:
        return {
            "accepted": bool(self.accepted),
            "reason": self.reason,
            "residual_threshold": float(self.residual_threshold),
        }


def grid_anchor_detail(gap: Gap) -> dict[str, Any]:
    return {
        "index": int(gap.index),
        "method": gap.method,
        "center": float(gap.center),
        "score": float(gap.score),
        "width_px": float(gap.width),
    }


def reliable_grid_anchor_gaps(gaps: list[Gap], config: RobustGridParameters) -> list[Gap]:
    return [gap for gap in gaps if is_hard_gap_method(gap.method) and gap.score >= config.reliable_min_score]


def grid_fit_tolerance(pitch: float, strip_mode: str, config: RobustGridParameters) -> float:
    return clamp_float(
        pitch * (config.full_tolerance_ratio if strip_mode == "full" else config.partial_tolerance_ratio),
        config.tolerance_min,
        config.tolerance_max,
    )


def grid_fit_candidate_from_anchor_pair(
    left: Gap,
    right: Gap,
    reliable: list[Gap],
    nominal_pitch: float,
    tolerance: float,
    config: RobustGridParameters,
) -> GridFitCandidate | None:
    dk = right.index - left.index
    if dk == 0:
        return None
    fit_pitch = (right.center - left.center) / float(dk)
    if fit_pitch <= nominal_pitch * config.pitch_min_ratio or fit_pitch >= nominal_pitch * config.pitch_max_ratio:
        return None
    fit_origin = left.center - fit_pitch * left.index
    residuals = [abs(gap.center - (fit_origin + fit_pitch * gap.index)) for gap in reliable]
    inliers = sum(1 for value in residuals if value <= tolerance)
    median_residual = float(np.median(np.array(residuals, dtype=np.float64))) if residuals else 0.0
    return GridFitCandidate(
        inliers=int(inliers),
        pitch=float(fit_pitch),
        origin=float(fit_origin),
        median_residual=float(median_residual),
    )


def best_grid_fit(
    reliable: list[Gap],
    pitch: float,
    strip_mode: str,
    config: RobustGridParameters,
) -> GridFit | None:
    best = best_grid_fit_candidate(reliable, pitch, strip_mode, config)
    return None if best is None else best.as_grid_fit()


def grid_fit_candidates(
    reliable: list[Gap],
    pitch: float,
    strip_mode: str,
    config: RobustGridParameters,
) -> list[GridFitCandidate]:
    candidates: list[GridFitCandidate] = []
    tolerance = grid_fit_tolerance(pitch, strip_mode, config)
    for a_i, a in enumerate(reliable):
        for b in reliable[a_i + 1:]:
            candidate = grid_fit_candidate_from_anchor_pair(a, b, reliable, pitch, tolerance, config)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def best_grid_fit_candidate(
    reliable: list[Gap],
    pitch: float,
    strip_mode: str,
    config: RobustGridParameters,
) -> GridFitCandidate | None:
    return best_grid_fit_candidate_from_candidates(
        grid_fit_candidates(reliable, pitch, strip_mode, config),
        pitch,
    )


def best_grid_fit_candidate_from_candidates(
    candidates: list[GridFitCandidate],
    nominal_pitch: float,
) -> GridFitCandidate | None:
    best: GridFitCandidate | None = None
    for candidate in candidates:
        if best is None or candidate.rank_key(nominal_pitch) > best.rank_key(nominal_pitch):
            best = candidate
    return best


def grid_fit_candidate_details(
    candidates: list[GridFitCandidate],
    nominal_pitch: float,
) -> list[dict[str, Any]]:
    ranked = sorted(candidates, key=lambda item: item.rank_key(nominal_pitch), reverse=True)
    return [candidate.detail(nominal_pitch) for candidate in ranked[:GRID_DETAIL_LIMIT]]


def grid_fit_assessment(
    fit: GridFit,
    nominal_pitch: float,
    config: RobustGridParameters,
) -> GridFitAssessment:
    inlier_count, _fit_pitch, _fit_origin, median_residual = fit
    residual_threshold = clamp_float(
        nominal_pitch * config.reject_residual_ratio,
        config.tolerance_min,
        config.tolerance_max,
    )
    if inlier_count < config.min_reliable:
        return GridFitAssessment(False, "too_few_inliers", residual_threshold)
    if median_residual > residual_threshold:
        return GridFitAssessment(False, "high_residual", residual_threshold)
    return GridFitAssessment(True, "accepted", residual_threshold)


def grid_predicted_center(
    fit_origin: float,
    fit_pitch: float,
    gap: Gap,
    origin: float,
    pitch: float,
    max_shift: float,
) -> float:
    predicted = float(fit_origin + fit_pitch * gap.index)
    theoretical = float(origin + pitch * gap.index)
    return max(theoretical - max_shift, min(theoretical + max_shift, predicted))


def grid_adjusted_gap(
    gap: Gap,
    predicted: float,
    pitch: float,
    allow_hard_protection: bool,
    profile: Optional[np.ndarray],
    gray_work: Optional[np.ndarray],
    outer: Optional[Box],
    hard_gap_trust: HardGapTrustParameters | None,
    nearby_correction: NearbySeparatorCorrectionParameters | None,
    config: RobustGridParameters,
) -> tuple[Gap, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    trust, trust_detail = light_hard_gap_trust(
        gap,
        pitch,
        predicted=predicted,
        profile=profile,
        gray_work=gray_work,
        outer=outer,
        hard_gap_trust=hard_gap_trust,
        nearby_correction=nearby_correction,
    )
    keep_limit = clamp_float(
        pitch * config.hard_keep_ratio,
        config.hard_keep_min,
        config.hard_keep_max,
    )
    detail: dict[str, Any] = {
        "index": int(gap.index),
        "input_method": gap.method,
        "input_center": float(gap.center),
        "predicted": float(predicted),
        "delta_px": float(gap.center - predicted),
        "input_score": float(gap.score),
        "input_width_px": float(gap.width),
        "trust": trust,
        "keep_limit": float(keep_limit),
    }
    if is_hard_gap_method(gap.method) and abs(gap.center - predicted) <= keep_limit:
        detail["action"] = "keep_hard_near_prediction"
        detail["output_method"] = gap.method
        detail["output_center"] = float(gap.center)
        return gap, None, None, detail
    if allow_hard_protection and trust == "strong_separator":
        protected = {
            "index": int(gap.index),
            "method": gap.method,
            "center": float(gap.center),
            "predicted": float(predicted),
            "delta_px": float(gap.center - predicted),
            "width_px": float(gap.width),
            "score": float(gap.score),
            "trust": trust,
            "trust_detail": trust_detail,
        }
        detail["action"] = "protect_strong_hard_gap"
        detail["trust_detail"] = trust_detail
        detail["output_method"] = gap.method
        detail["output_center"] = float(gap.center)
        return gap, protected, None, detail
    overridden = None
    if is_hard_gap_method(gap.method):
        overridden = {
            "index": int(gap.index),
            "method": gap.method,
            "center": float(gap.center),
            "predicted": float(predicted),
            "delta_px": float(gap.center - predicted),
            "width_px": float(gap.width),
            "score": float(gap.score),
            "trust": trust,
            "trust_detail": trust_detail,
        }
        detail["action"] = "override_hard_with_grid_model"
        detail["trust_detail"] = trust_detail
    else:
        detail["action"] = "replace_model_with_grid_model"
    adjusted = grid_model_gap(gap.index, predicted, gap.score)
    detail["output_method"] = adjusted.method
    detail["output_center"] = float(adjusted.center)
    return adjusted, None, overridden, detail


def robust_grid_base_detail(
    gaps: list[Gap],
    constrained: list[Gap],
    reliable: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    config: RobustGridParameters,
    *,
    candidates: list[GridFitCandidate] | None = None,
) -> dict[str, Any]:
    tolerance = grid_fit_tolerance(pitch, strip_mode, config)
    detail: dict[str, Any] = {
        "input_gap_count": int(len(gaps)),
        "constrained_gap_count": int(len(constrained)),
        "reliable_gaps": int(len(reliable)),
        "min_reliable": int(config.min_reliable),
        "origin": float(origin),
        "nominal_pitch": float(pitch),
        "strip_mode": strip_mode,
        "fit_tolerance": float(tolerance),
        "reliable_anchors": [grid_anchor_detail(gap) for gap in reliable[:GRID_DETAIL_LIMIT]],
    }
    if candidates is not None:
        detail["fit_candidate_count"] = int(len(candidates))
        detail["fit_candidates"] = grid_fit_candidate_details(candidates, pitch)
    return detail


def apply_robust_grid(
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    profile: Optional[np.ndarray] = None,
    gray_work: Optional[np.ndarray] = None,
    outer: Optional[Box] = None,
    hard_gap_trust: HardGapTrustParameters | None = None,
    nearby_correction: NearbySeparatorCorrectionParameters | None = None,
    robust_grid: RobustGridParameters | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    if not gaps:
        return gaps, {"grid_used": False}
    config = robust_grid or RobustGridParameters()
    constrained = [constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode, config) for gap in gaps]
    reliable = reliable_grid_anchor_gaps(constrained, config)
    detail = robust_grid_base_detail(gaps, constrained, reliable, origin, pitch, strip_mode, config)
    if len(reliable) < config.min_reliable:
        detail.update({"grid_used": False, "grid_rejected": "too_few_reliable_anchors"})
        return constrained, detail
    candidates = grid_fit_candidates(reliable, pitch, strip_mode, config)
    detail = robust_grid_base_detail(
        gaps,
        constrained,
        reliable,
        origin,
        pitch,
        strip_mode,
        config,
        candidates=candidates,
    )
    best_candidate = best_grid_fit_candidate_from_candidates(candidates, pitch)
    best = None if best_candidate is None else best_candidate.as_grid_fit()
    if best is None:
        detail.update({"grid_used": False, "grid_rejected": "no_pair_model"})
        return constrained, detail
    inlier_count, fit_pitch, fit_origin, median_residual = best
    fit_assessment = grid_fit_assessment(best, pitch, config)
    detail["selected_fit"] = best_candidate.detail(pitch) if best_candidate is not None else None
    detail["fit_assessment"] = fit_assessment.detail()
    if not fit_assessment.accepted:
        detail.update({
            "grid_used": False,
            "grid_rejected": fit_assessment.reason,
        })
        if fit_assessment.reason == "high_residual":
            detail["grid_residual"] = median_residual
        return constrained, detail
    max_shift = clamp_float(
        pitch * (config.full_shift_ratio if strip_mode == "full" else config.partial_shift_ratio),
        config.shift_min,
        config.shift_max,
    )
    hard_protection_residual_threshold = clamp_float(
        pitch * config.hard_protect_ratio,
        config.hard_protect_min,
        config.hard_protect_max,
    )
    allow_hard_protection = median_residual > hard_protection_residual_threshold
    adjusted: list[Gap] = []
    protected_hard: list[dict[str, Any]] = []
    overridden_hard: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    for gap in constrained:
        predicted = grid_predicted_center(fit_origin, fit_pitch, gap, origin, pitch, max_shift)
        adjusted_gap, protected, overridden, adjustment_detail = grid_adjusted_gap(
            gap,
            predicted,
            pitch,
            allow_hard_protection,
            profile,
            gray_work,
            outer,
            hard_gap_trust,
            nearby_correction,
            config,
        )
        adjusted.append(adjusted_gap)
        adjustments.append(adjustment_detail)
        if protected is not None:
            protected_hard.append(protected)
        if overridden is not None:
            overridden_hard.append(overridden)
    detail.update({
        "grid_used": True,
        "grid_inliers": int(inlier_count),
        "grid_pitch": float(fit_pitch),
        "grid_origin": float(fit_origin),
        "grid_residual": median_residual,
        "hard_protection_residual_threshold": float(hard_protection_residual_threshold),
        "hard_protection_allowed": bool(allow_hard_protection),
        "protected_hard_gaps": protected_hard,
        "overridden_hard_gaps": overridden_hard,
        "gap_adjustments": adjustments[:GRID_DETAIL_LIMIT],
        "gap_adjustment_count": int(len(adjustments)),
    })
    return adjusted, detail
