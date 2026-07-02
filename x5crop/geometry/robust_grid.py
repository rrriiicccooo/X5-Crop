from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Box, Gap
from ..utils import clamp_float
from .gap_search import constrain_gap_to_geometry
from .gap_trust import light_hard_gap_trust
from .detection_parameters import HardGapTrustPolicy, NearbySeparatorCorrectionPolicy, RobustGridPolicy


def apply_robust_grid(
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    format_name: str,
    profile: Optional[np.ndarray] = None,
    gray_work: Optional[np.ndarray] = None,
    outer: Optional[Box] = None,
    hard_gap_trust: HardGapTrustPolicy | None = None,
    nearby_correction: NearbySeparatorCorrectionPolicy | None = None,
    robust_grid: RobustGridPolicy | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    if not gaps:
        return gaps, {"grid_used": False}
    policy = robust_grid or RobustGridPolicy()
    constrained = [constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode, policy) for gap in gaps]
    reliable = [gap for gap in constrained if gap.method in HARD_GAP_METHODS and gap.score >= policy.reliable_min_score]
    if len(reliable) < policy.min_reliable:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable)}
    best: Optional[tuple[int, float, float, float]] = None
    for a_i, a in enumerate(reliable):
        for b in reliable[a_i + 1:]:
            dk = b.index - a.index
            if dk == 0:
                continue
            cand_pitch = (b.center - a.center) / float(dk)
            if cand_pitch <= pitch * policy.pitch_min_ratio or cand_pitch >= pitch * policy.pitch_max_ratio:
                continue
            cand_origin = a.center - cand_pitch * a.index
            residuals = [abs(g.center - (cand_origin + cand_pitch * g.index)) for g in reliable]
            tolerance = clamp_float(
                pitch * (policy.full_tolerance_ratio if strip_mode == "full" else policy.partial_tolerance_ratio),
                policy.tolerance_min,
                policy.tolerance_max,
            )
            inliers = sum(1 for value in residuals if value <= tolerance)
            median_residual = float(np.median(np.array(residuals, dtype=np.float64))) if residuals else 0.0
            rank = (inliers, -median_residual, -abs(cand_pitch - pitch), cand_pitch)
            if best is None or rank > (best[0], -best[3], -abs(best[1] - pitch), best[1]):
                best = (inliers, float(cand_pitch), float(cand_origin), median_residual)
    if best is None:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "no_pair_model"}
    inlier_count, fit_pitch, fit_origin, median_residual = best
    if inlier_count < policy.min_reliable:
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "too_few_inliers"}
    if median_residual > clamp_float(pitch * policy.reject_residual_ratio, policy.tolerance_min, policy.tolerance_max):
        return constrained, {"grid_used": False, "reliable_gaps": len(reliable), "grid_rejected": "high_residual", "grid_residual": median_residual}
    max_shift = clamp_float(
        pitch * (policy.full_shift_ratio if strip_mode == "full" else policy.partial_shift_ratio),
        policy.shift_min,
        policy.shift_max,
    )
    hard_protection_residual_threshold = clamp_float(
        pitch * policy.hard_protect_ratio,
        policy.hard_protect_min,
        policy.hard_protect_max,
    )
    allow_hard_protection = median_residual > hard_protection_residual_threshold
    adjusted: list[Gap] = []
    protected_hard: list[dict[str, Any]] = []
    overridden_hard: list[dict[str, Any]] = []
    for gap in constrained:
        predicted = float(fit_origin + fit_pitch * gap.index)
        theoretical = float(origin + pitch * gap.index)
        predicted = max(theoretical - max_shift, min(theoretical + max_shift, predicted))
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
            pitch * policy.hard_keep_ratio,
            policy.hard_keep_min,
            policy.hard_keep_max,
        ):
            adjusted.append(gap)
        elif allow_hard_protection and trust == "strong_separator":
            adjusted.append(gap)
            protected_hard.append(
                {
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
            )
        else:
            if gap.method in HARD_GAP_METHODS:
                overridden_hard.append(
                    {
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
                )
            adjusted.append(Gap(gap.index, predicted, gap.score, "grid"))
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
