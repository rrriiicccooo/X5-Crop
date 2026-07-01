from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Box, Gap
from ..policies.base import GapSearchPolicy, HardGapTrustPolicy, NearbySeparatorCorrectionPolicy, RobustGridPolicy
from ..utils import clamp_float, clamp_int
from .outer_boxes import runs_from_mask
from .separator_profile import interval_mean


def find_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    format_name: str,
    max_width_ratio_override: Optional[float] = None,
    gap_search: GapSearchPolicy | None = None,
) -> Gap:
    policy = gap_search or GapSearchPolicy()
    radius = clamp_int(pitch * policy.radius_ratio, policy.radius_min, policy.radius_max)
    lo = max(1, int(round(expected)) - radius)
    hi = min(len(profile) - 1, int(round(expected)) + radius + 1)
    if hi <= lo:
        return Gap(index, float(expected), 0.0, "equal")
    local = profile[lo:hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = policy.min_score
    if local.size == 0 or local_max < min_score:
        return Gap(index, float(expected), local_max, "equal")

    normal_max_gap_w = clamp_int(pitch * policy.max_width_ratio, policy.max_width_min, policy.max_width_max)
    max_width_ratio = policy.max_width_ratio if max_width_ratio_override is None else max_width_ratio_override
    max_gap_w = clamp_int(pitch * max_width_ratio, policy.max_width_min, policy.max_width_max)
    min_gap_w = clamp_int(pitch * policy.min_width_ratio, policy.min_width_min, policy.min_width_max)
    guard_w = clamp_int(pitch * policy.guard_ratio, policy.guard_min, policy.guard_max)
    peak_threshold = max(min_score, local_max * policy.peak_multiplier)
    band_threshold = max(min_score * 0.86, local_max * policy.band_multiplier)
    candidates: list[tuple[float, float, float, float, float, float, str]] = []

    for run_start, run_end in runs_from_mask(local >= peak_threshold):
        band_start, band_end = run_start, run_end
        while band_start > 0 and local[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_gap_w:
            band_start -= 1
        while band_end < len(local) and local[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_gap_w:
            band_end += 1
        band_width = band_end - band_start
        if band_width < min_gap_w or band_width > max_gap_w:
            continue

        left_guard = local[max(0, band_start - guard_w):band_start]
        right_guard = local[band_end:min(len(local), band_end + guard_w)]
        if left_guard.size == 0 or right_guard.size == 0:
            continue
        mean_score = float(local[band_start:band_end].mean())
        side_score = max(float(left_guard.mean()), float(right_guard.mean()))
        prominence = mean_score - side_score
        if prominence < 0.08 and mean_score < 0.95:
            continue
        method = "detected"
        if max_width_ratio_override is not None and band_width > normal_max_gap_w:
            if mean_score < policy.wide_min_mean or prominence < policy.wide_min_prominence:
                continue
            method = "wide-separator"

        center = float(lo + (band_start + band_end - 1) / 2.0)
        start = float(lo + band_start)
        end = float(lo + band_end)
        distance = abs(center - expected) / max(1.0, pitch)
        quality = mean_score + 0.8 * prominence
        candidates.append((distance, -quality, -mean_score, center, start, end, method))

    if candidates:
        _, neg_quality, _, center, start, end, method = sorted(candidates)[0]
        return Gap(index, center, float(-neg_quality), method, start, end)

    return Gap(index, float(expected), local_max, "equal")


def constrain_gap_to_geometry(
    gap: Gap,
    expected: float,
    pitch: float,
    strip_mode: str,
    robust_grid: RobustGridPolicy | None = None,
) -> Gap:
    if gap.method not in HARD_GAP_METHODS:
        return Gap(gap.index, float(expected), gap.score, "equal")
    policy = robust_grid or RobustGridPolicy()
    max_shift = clamp_float(
        pitch * (policy.constrain_full_shift_ratio if strip_mode == "full" else policy.constrain_partial_shift_ratio),
        policy.constrain_shift_min,
        policy.constrain_shift_max,
    )
    shift = max(-max_shift, min(max_shift, gap.center - expected))
    center = float(expected + shift)
    method = gap.method
    if gap.start is not None and gap.end is not None:
        delta = center - float(gap.center)
        start = float(gap.start + delta)
        end = float(gap.end + delta)
    else:
        start = None
        end = None
    return Gap(gap.index, center, gap.score, method, start, end)


def light_hard_gap_trust(
    gap: Gap,
    pitch: float,
    *,
    predicted: Optional[float] = None,
    profile: Optional[np.ndarray] = None,
    gray_work: Optional[np.ndarray] = None,
    outer: Optional[Box] = None,
    hard_gap_trust: HardGapTrustPolicy | None = None,
    nearby_correction: NearbySeparatorCorrectionPolicy | None = None,
) -> tuple[str, dict[str, Any]]:
    if gap.method not in HARD_GAP_METHODS or pitch <= 0:
        return "not_hard_gap", {"reason": "not_hard_gap"}
    trust_policy = hard_gap_trust or HardGapTrustPolicy()
    width_ratio = float(gap.width) / max(1.0, float(pitch))
    detail: dict[str, Any] = {
        "width_ratio": float(width_ratio),
        "score": float(gap.score),
    }
    if profile is not None:
        nearby = nearby_separator_replacement(profile, gap, pitch, nearby_correction)
        if nearby is not None:
            detail["nearby_separator_candidate"] = nearby
            return "nearby_separator_conflict", detail
    if predicted is not None:
        model_delta_ratio = abs(float(gap.center) - float(predicted)) / max(1.0, float(pitch))
        detail["model_delta_ratio"] = float(model_delta_ratio)
        if model_delta_ratio >= trust_policy.model_delta_ratio and (
            width_ratio < trust_policy.geometry_width_ratio or gap.score < trust_policy.model_conflict_score
        ):
            return "geometry_conflict", detail
    if gray_work is not None and outer is not None and gap.start is not None and gap.end is not None:
        start = int(round(outer.left + min(gap.start, gap.end)))
        end = int(round(outer.left + max(gap.start, gap.end)))
        start = max(outer.left, min(outer.right, start))
        end = max(start + 1, min(outer.right, end))
        guard = clamp_int(
            max(float(end - start), pitch * trust_policy.guard_ratio),
            trust_policy.guard_min,
            trust_policy.guard_max,
        )
        left_start = max(outer.left, start - guard)
        right_end = min(outer.right, end + guard)
        core = gray_work[outer.top:outer.bottom, start:end]
        left = gray_work[outer.top:outer.bottom, left_start:start]
        right = gray_work[outer.top:outer.bottom, end:right_end]
        if core.size:
            core_mean = float(core.mean())
            core_content = float((core < trust_policy.core_content_threshold).mean())
            core_dark = float((core < trust_policy.core_dark_threshold).mean())
            core_activity = float(core.std() / 255.0)
            left_content = float((left < trust_policy.core_content_threshold).mean()) if left.size else 0.0
            right_content = float((right < trust_policy.core_content_threshold).mean()) if right.size else 0.0
            continuity = min(core_content, min(left_content, right_content))
            dark_separator_like = (
                core_mean <= trust_policy.dark_mean_max
                and core_dark >= trust_policy.dark_fraction_min
                and core_activity <= trust_policy.dark_activity_max
            )
            weak_dark_gap = core_mean >= trust_policy.weak_mean_min and core_content >= trust_policy.weak_content_min
            narrow_hard = 0.0 < gap.width <= clamp_float(
                pitch * trust_policy.narrow_ratio,
                trust_policy.narrow_min,
                trust_policy.narrow_max,
            )
            detail["signals"] = {
                "core_mean": core_mean,
                "core_content": core_content,
                "core_dark": core_dark,
                "core_activity": core_activity,
                "continuity": continuity,
            }
            if width_ratio < trust_policy.frame_border_width_ratio and dark_separator_like:
                return "suspect_frame_border", detail
            if narrow_hard and (
                (continuity >= trust_policy.continuity_min and core_activity >= trust_policy.activity_min)
                or weak_dark_gap
            ):
                return "suspect_internal_edge", detail
    if gap.score >= trust_policy.strong_min_score and trust_policy.strong_width_min <= width_ratio <= trust_policy.strong_width_max:
        return "strong_separator", detail
    if gap.score >= trust_policy.narrow_ok_score and trust_policy.narrow_ok_width_min <= width_ratio < trust_policy.narrow_ok_width_max:
        return "narrow_but_ok", detail
    return "weak_or_ambiguous_separator", detail


def gap_width_cv(gaps: list[Gap], origin: float, pitch: float, count: int) -> float:
    if count <= 1:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    widths = np.diff(np.array(cuts, dtype=np.float64))
    if widths.size != count or np.any(widths <= 1):
        return 1.0
    return float(widths.std() / max(1.0, widths.mean()))


def local_gap_geometry_error(gaps: list[Gap], gap_index: int, origin: float, pitch: float, count: int) -> float:
    if count <= 1 or gap_index < 1 or gap_index >= count:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    left_w = cuts[gap_index] - cuts[gap_index - 1]
    right_w = cuts[gap_index + 1] - cuts[gap_index]
    if left_w <= 1 or right_w <= 1:
        return float("inf")
    return abs(left_w - pitch) + abs(right_w - pitch)


def nearby_separator_replacement(
    profile: np.ndarray,
    gap: Gap,
    pitch: float,
    correction_policy: NearbySeparatorCorrectionPolicy | None = None,
) -> Optional[dict[str, Any]]:
    if gap.method not in HARD_GAP_METHODS or pitch <= 0 or gap.start is None or gap.end is None:
        return None
    policy = correction_policy or NearbySeparatorCorrectionPolicy()
    center = int(round(gap.center))
    current_start = max(0, min(len(profile), int(round(min(gap.start, gap.end)))))
    current_end = max(current_start + 1, min(len(profile), int(round(max(gap.start, gap.end)))))
    window = clamp_int(pitch * policy.window_ratio, policy.window_min, policy.window_max)
    exclude = max(
        policy.exclude_min,
        clamp_int(
            max(float(current_end - current_start), pitch * policy.exclude_ratio),
            policy.exclude_min,
            policy.exclude_max,
        ),
    )
    lo = max(0, center - window)
    hi = min(len(profile), center + window + 1)
    if hi <= lo:
        return None
    current_score = interval_mean(profile, current_start, current_end)
    threshold = max(0.22, float(np.percentile(profile[lo:hi], 82)))
    candidates: list[dict[str, Any]] = []
    for run_start, run_end in runs_from_mask(profile[lo:hi] >= threshold):
        abs_start = lo + run_start
        abs_end = lo + run_end
        if abs_end <= abs_start:
            continue
        if abs_start < current_end + exclude and abs_end > current_start - exclude:
            continue
        width = abs_end - abs_start
        if width > clamp_int(pitch * policy.max_width_ratio, policy.max_width_min, policy.max_width_max):
            continue
        score = interval_mean(profile, abs_start, abs_end)
        candidate_center = (abs_start + abs_end - 1) / 2.0
        distance = candidate_center - gap.center
        if abs(distance) > clamp_float(
            pitch * policy.distance_ratio,
            float(policy.window_min),
            float(policy.window_max),
        ):
            continue
        candidates.append(
            {
                "center": float(candidate_center),
                "start": int(abs_start),
                "end": int(abs_end),
                "width_px": int(width),
                "score": float(score),
                "distance_px": float(distance),
            }
        )
    candidates.sort(key=lambda item: (float(item["score"]), -abs(float(item["distance_px"]))), reverse=True)
    best = candidates[0] if candidates else None
    if not best:
        return None
    stronger = float(best["score"]) >= max(
        current_score + policy.score_add,
        current_score * policy.score_multiplier,
    )
    if not stronger:
        return None
    return {
        "searched": True,
        "window_px": int(window),
        "current_profile_score": float(current_score),
        "candidate_count": len(candidates),
        "stronger_found": True,
        "best": best,
    }


def apply_nearby_separator_corrections(
    profile: np.ndarray,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    count: int,
    strip_mode: str,
    correction_policy: NearbySeparatorCorrectionPolicy | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    policy = correction_policy or NearbySeparatorCorrectionPolicy()
    if not policy.enabled or strip_mode != "full" or count <= 1 or len(gaps) != count - 1:
        return gaps, {"used": False, "reason": "not_applicable"}
    if profile.size == 0:
        return gaps, {"used": False, "reason": "empty_profile"}
    original_cv = gap_width_cv(gaps, origin, pitch, count)
    corrected = list(gaps)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for pos, gap in enumerate(list(corrected)):
        replacement = nearby_separator_replacement(profile, gap, pitch, policy)
        if replacement is None:
            continue
        best = replacement["best"]
        proposed_gap = Gap(
            gap.index,
            float(best["center"]),
            float(best["score"]),
            gap.method,
            float(best["start"]),
            float(best["end"]),
            gap.lane_box,
        )
        proposed = list(corrected)
        proposed[pos] = proposed_gap
        if any(b.center <= a.center for a, b in zip(proposed[:-1], proposed[1:])):
            rejected.append({"index": int(gap.index), "reason": "non_monotonic", "candidate": best})
            continue
        before_local = local_gap_geometry_error(corrected, gap.index, origin, pitch, count)
        after_local = local_gap_geometry_error(proposed, gap.index, origin, pitch, count)
        before_cv = gap_width_cv(corrected, origin, pitch, count)
        after_cv = gap_width_cv(proposed, origin, pitch, count)
        local_gain = before_local - after_local
        cv_gain = before_cv - after_cv
        local_ok = local_gain >= clamp_float(
            pitch * policy.local_gain_ratio,
            policy.local_gain_min,
            policy.local_gain_max,
        )
        cv_ok = after_cv <= before_cv + policy.width_cv_slack and after_cv <= original_cv + policy.width_cv_slack
        if not (local_ok and cv_ok):
            rejected.append(
                {
                    "index": int(gap.index),
                    "reason": "geometry_not_better",
                    "candidate": best,
                    "before_local_error": float(before_local),
                    "after_local_error": float(after_local),
                    "before_width_cv": float(before_cv),
                    "after_width_cv": float(after_cv),
                }
            )
            continue
        corrected = proposed
        accepted.append(
            {
                "index": int(gap.index),
                "from_center": float(gap.center),
                "to_center": float(proposed_gap.center),
                "delta_px": float(proposed_gap.center - gap.center),
                "from_score": float(gap.score),
                "to_score": float(proposed_gap.score),
                "from_method": gap.method,
                "to_method": proposed_gap.method,
                "before_local_error": float(before_local),
                "after_local_error": float(after_local),
                "before_width_cv": float(before_cv),
                "after_width_cv": float(after_cv),
                "nearby_separator_candidate": replacement,
            }
        )
    return corrected, {
        "used": True,
        "accepted": accepted,
        "accepted_count": len(accepted),
        "rejected": rejected[:8],
        "rejected_count": len(rejected),
        "original_width_cv": float(original_cv),
        "final_width_cv": float(gap_width_cv(corrected, origin, pitch, count)),
        "confidence_cap_required": bool(accepted),
    }


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
