from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Box, Gap
from ..utils import clamp_float
from .gap_geometry import constrain_gap_to_geometry
from .gap_trust import light_hard_gap_trust
from .model_gaps import grid_model_gap
from .detection_parameters import HardGapTrustParameters, NearbySeparatorCorrectionParameters, RobustGridParameters


GridFit = tuple[int, float, float, float]


def reliable_grid_anchor_gaps(gaps: list[Gap], config: RobustGridParameters) -> list[Gap]:
    return [gap for gap in gaps if gap.method in HARD_GAP_METHODS and gap.score >= config.reliable_min_score]


def grid_fit_tolerance(pitch: float, strip_mode: str, config: RobustGridParameters) -> float:
    return clamp_float(
        pitch * (config.full_tolerance_ratio if strip_mode == "full" else config.partial_tolerance_ratio),
        config.tolerance_min,
        config.tolerance_max,
    )


def best_grid_fit(
    reliable: list[Gap],
    pitch: float,
    strip_mode: str,
    config: RobustGridParameters,
) -> GridFit | None:
    best: GridFit | None = None
    tolerance = grid_fit_tolerance(pitch, strip_mode, config)
    for a_i, a in enumerate(reliable):
        for b in reliable[a_i + 1:]:
            dk = b.index - a.index
            if dk == 0:
                continue
            cand_pitch = (b.center - a.center) / float(dk)
            if cand_pitch <= pitch * config.pitch_min_ratio or cand_pitch >= pitch * config.pitch_max_ratio:
                continue
            cand_origin = a.center - cand_pitch * a.index
            residuals = [abs(g.center - (cand_origin + cand_pitch * g.index)) for g in reliable]
            inliers = sum(1 for value in residuals if value <= tolerance)
            median_residual = float(np.median(np.array(residuals, dtype=np.float64))) if residuals else 0.0
            rank = (inliers, -median_residual, -abs(cand_pitch - pitch), cand_pitch)
            if best is None or rank > (best[0], -best[3], -abs(best[1] - pitch), best[1]):
                best = (inliers, float(cand_pitch), float(cand_origin), median_residual)
    return best


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
    if gap.method in HARD_GAP_METHODS and abs(gap.center - predicted) <= clamp_float(
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
    if gap.method in HARD_GAP_METHODS:
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
    if inlier_count < config.min_reliable:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "too_few_inliers"}
    if median_residual > clamp_float(pitch * config.reject_residual_ratio, config.tolerance_min, config.tolerance_max):
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "high_residual", "grid_residual": median_residual}
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
