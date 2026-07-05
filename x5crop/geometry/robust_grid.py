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


@dataclass(frozen=True)
class GridFitAssessment:
    accepted: bool
    reason: str
    residual_threshold: float


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
    best: GridFitCandidate | None = None
    tolerance = grid_fit_tolerance(pitch, strip_mode, config)
    for a_i, a in enumerate(reliable):
        for b in reliable[a_i + 1:]:
            candidate = grid_fit_candidate_from_anchor_pair(a, b, reliable, pitch, tolerance, config)
            if candidate is not None and (best is None or candidate.rank_key(pitch) > best.rank_key(pitch)):
                best = candidate
    return None if best is None else best.as_grid_fit()


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
) -> tuple[Gap, dict[str, Any] | None, dict[str, Any] | None]:
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
    if is_hard_gap_method(gap.method) and abs(gap.center - predicted) <= clamp_float(
        pitch * config.hard_keep_ratio,
        config.hard_keep_min,
        config.hard_keep_max,
    ):
        return gap, None, None
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
        return gap, protected, None
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
    return grid_model_gap(gap.index, predicted, gap.score), None, overridden


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
    if len(reliable) < config.min_reliable:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable)}
    best = best_grid_fit(reliable, pitch, strip_mode, config)
    if best is None:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "no_pair_model"}
    inlier_count, fit_pitch, fit_origin, median_residual = best
    fit_assessment = grid_fit_assessment(best, pitch, config)
    if not fit_assessment.accepted:
        detail = {
            "grid_used": False,
            "reliable_gaps": len(reliable),
            "grid_rejected": fit_assessment.reason,
        }
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
    for gap in constrained:
        predicted = grid_predicted_center(fit_origin, fit_pitch, gap, origin, pitch, max_shift)
        adjusted_gap, protected, overridden = grid_adjusted_gap(
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
        if protected is not None:
            protected_hard.append(protected)
        if overridden is not None:
            overridden_hard.append(overridden)
    return adjusted, {
        "grid_used": True,
        "reliable_gaps": len(reliable),
        "grid_inliers": int(inlier_count),
        "grid_pitch": float(fit_pitch),
        "grid_origin": float(fit_origin),
        "grid_residual": median_residual,
        "hard_protection_residual_threshold": float(hard_protection_residual_threshold),
        "hard_protection_allowed": bool(allow_hard_protection),
        "protected_hard_gaps": protected_hard,
        "overridden_hard_gaps": overridden_hard,
    }
