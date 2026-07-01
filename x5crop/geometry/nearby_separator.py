from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Gap
from ..policies.runtime_policy import NearbySeparatorCorrectionPolicy
from ..utils import clamp_float, clamp_int, runs_from_mask
from .gap_search import gap_width_cv, local_gap_geometry_error
from .separator_profile import interval_mean


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
    }
