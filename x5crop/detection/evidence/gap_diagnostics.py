from __future__ import annotations

import copy
from typing import Any, Optional

import numpy as np

from ...constants import HARD_GAP_METHODS, MODEL_GAP_METHODS
from ...domain import Box, Detection, Gap
from ...geometry.boxes import box_cache_key
from ...geometry.detection_parameters import SeparatorProfileParameters
from ...geometry.separator_cache import cached_separator_profile
from ...geometry.separator_profile import interval_mean
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import NearbySeparatorDiagnosticsPolicy
from ...runtime import AnalysisCache
from ...utils import clamp_float, clamp_int, runs_from_mask


def gap_work_outer(detection: Detection, gap: Gap) -> Optional[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return None
    try:
        return Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return None


def nearby_separator_candidate_detail(
    gray_work: np.ndarray,
    work_outer: Box,
    gap: Gap,
    pitch: float,
    start: int,
    end: int,
    nearby_policy: NearbySeparatorDiagnosticsPolicy,
    format_name: str,
    cache: Optional[AnalysisCache] = None,
    profile_policy: Optional[SeparatorProfileParameters] = None,
) -> dict[str, Any]:
    if gap.method not in HARD_GAP_METHODS or pitch <= 0:
        return {"searched": False, "reason": "not_hard_gap"}
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        cache_key = (
            str(format_name),
            "nearby_separator",
            profile_policy or SeparatorProfileParameters(),
            box_cache_key(work_outer),
            int(gap.index),
            str(gap.method),
            round(float(gap.center), 4),
            round(float(gap.score), 6),
            None if gap.start is None else round(float(gap.start), 4),
            None if gap.end is None else round(float(gap.end), 4),
            round(float(pitch), 4),
            int(start),
            int(end),
        )
        cached = cache.nearby_separator_details.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
    crop = gray_work[work_outer.top:work_outer.bottom, work_outer.left:work_outer.right]
    if crop.size == 0:
        return {"searched": False, "reason": "empty_outer"}
    profile = cached_separator_profile(cache, gray_work, work_outer, format_name, profile_policy)
    if profile.size == 0:
        return {"searched": False, "reason": "empty_profile"}

    center = int(round(gap.center))
    current_start = max(0, min(len(profile), int(round(start - work_outer.left))))
    current_end = max(current_start + 1, min(len(profile), int(round(end - work_outer.left))))
    window = clamp_int(
        pitch * nearby_policy.window_ratio,
        nearby_policy.window_min,
        nearby_policy.window_max,
    )
    exclude = max(
        nearby_policy.exclude_min,
        clamp_int(
            max(float(current_end - current_start), pitch * nearby_policy.exclude_ratio),
            nearby_policy.exclude_min,
            nearby_policy.exclude_max,
        ),
    )
    lo = max(0, center - window)
    hi = min(len(profile), center + window + 1)
    current_score = interval_mean(profile, current_start, current_end)
    threshold = max(0.22, float(np.percentile(profile[lo:hi], 82)) if hi > lo else 0.22)
    candidates: list[dict[str, Any]] = []
    for run_start, run_end in runs_from_mask(profile[lo:hi] >= threshold):
        abs_start = lo + run_start
        abs_end = lo + run_end
        if abs_end <= abs_start:
            continue
        if abs_start < current_end + exclude and abs_end > current_start - exclude:
            continue
        width = abs_end - abs_start
        if width > clamp_int(
            pitch * nearby_policy.max_width_ratio,
            nearby_policy.max_width_min,
            nearby_policy.max_width_max,
        ):
            continue
        score = interval_mean(profile, abs_start, abs_end)
        candidate_center = (abs_start + abs_end - 1) / 2.0
        candidates.append(
            {
                "center": float(candidate_center),
                "absolute_center": float(work_outer.left + candidate_center),
                "start": int(abs_start),
                "end": int(abs_end),
                "width_px": int(width),
                "score": float(score),
                "distance_px": float(candidate_center - gap.center),
            }
        )
    candidates.sort(key=lambda item: (float(item["score"]), -abs(float(item["distance_px"]))), reverse=True)
    best = candidates[0] if candidates else None
    stronger = bool(
        best
        and float(best["score"])
        >= max(
            current_score + nearby_policy.detail_score_add,
            current_score * nearby_policy.detail_score_multiplier,
        )
    )
    detail = {
        "searched": True,
        "window_px": int(window),
        "current_profile_score": float(current_score),
        "candidate_count": len(candidates),
        "stronger_found": stronger,
        "best": best,
    }
    if cache_key is not None and cache is not None:
        cache.nearby_separator_details[cache_key] = copy.deepcopy(detail)
    return detail


def gap_diagnostic_record(gray_work: np.ndarray, detection: Detection, gap: Gap, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    policy = get_detection_policy(detection.film_format, detection.strip_mode)
    diagnostics_policy = policy.diagnostics
    hard_gap_trust_policy = policy.separator.hard_gap_trust
    nearby_policy = diagnostics_policy.nearby_separator
    overlap_policy = diagnostics_policy.overlap_bleed_risk
    work_outer = gap_work_outer(detection, gap)
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    origin = float(detection.detail.get("origin", 0.0) or 0.0)
    expected = origin + pitch * float(gap.index) if pitch > 0 else float(gap.center)
    role = "separator_evidence" if gap.method in HARD_GAP_METHODS else "geometry_model"
    record: dict[str, Any] = {
        "index": int(gap.index),
        "method": gap.method,
        "role": role,
        "used_for_decision": True,
        "diagnostic_only": True,
        "center": float(gap.center),
        "expected_center": float(expected),
        "model_delta_px": float(gap.center - expected),
        "score": float(gap.score),
        "width_px": float(gap.width),
        "hard_trust": "not_hard_gap",
        "overlap_like": False,
        "overlap_risk": "none",
        "signals": {},
    }
    if work_outer is None or not work_outer.valid() or pitch <= 0:
        record["signals"] = {"available": False}
        return record

    work_outer = work_outer.clamp(gray_work.shape[1], gray_work.shape[0])
    if not work_outer.valid():
        record["signals"] = {"available": False}
        return record

    if gap.start is not None and gap.end is not None:
        start = int(round(work_outer.left + min(gap.start, gap.end)))
        end = int(round(work_outer.left + max(gap.start, gap.end)))
    else:
        half = clamp_int(pitch * nearby_policy.exclude_ratio, 2, 80)
        center = int(round(work_outer.left + gap.center))
        start, end = center - half, center + half + 1
    start = max(work_outer.left, min(work_outer.right, start))
    end = max(start + 1, min(work_outer.right, end))
    guard = clamp_int(
        max(float(end - start), pitch * hard_gap_trust_policy.guard_ratio),
        hard_gap_trust_policy.guard_min,
        hard_gap_trust_policy.guard_max,
    )
    left_start = max(work_outer.left, start - guard)
    right_end = min(work_outer.right, end + guard)
    core = gray_work[work_outer.top:work_outer.bottom, start:end]
    left = gray_work[work_outer.top:work_outer.bottom, left_start:start]
    right = gray_work[work_outer.top:work_outer.bottom, end:right_end]
    if core.size == 0:
        record["signals"] = {"available": False}
        return record

    core_mean = float(core.mean())
    core_content = float((core < hard_gap_trust_policy.core_content_threshold).mean())
    core_dark = float((core < hard_gap_trust_policy.core_dark_threshold).mean())
    core_activity = float(core.std() / 255.0)
    left_content = float((left < hard_gap_trust_policy.core_content_threshold).mean()) if left.size else 0.0
    right_content = float((right < hard_gap_trust_policy.core_content_threshold).mean()) if right.size else 0.0
    side_content = min(left_content, right_content)
    side_balance = abs(left_content - right_content)
    continuity = min(core_content, side_content)
    nearby = nearby_separator_candidate_detail(
        gray_work,
        work_outer,
        gap,
        pitch,
        start,
        end,
        nearby_policy,
        detection.film_format,
        cache,
        policy.separator.profile,
    )
    record["signals"] = {
        "available": True,
        "core_mean": core_mean,
        "core_content": core_content,
        "core_dark": core_dark,
        "core_activity": core_activity,
        "left_content": left_content,
        "right_content": right_content,
        "side_content": side_content,
        "side_balance": side_balance,
        "continuity": continuity,
        "window": {"start": int(start), "end": int(end), "guard": int(guard)},
    }
    record["nearby_separator_candidate"] = nearby

    narrow_hard = gap.method in HARD_GAP_METHODS and 0.0 < gap.width <= clamp_float(
        pitch * hard_gap_trust_policy.narrow_ratio,
        hard_gap_trust_policy.narrow_min,
        hard_gap_trust_policy.narrow_max,
    )
    width_ratio = float(gap.width) / max(1.0, float(pitch))
    model_delta_ratio = abs(float(gap.center - expected)) / max(1.0, float(pitch))
    content_continuous = (
        continuity >= hard_gap_trust_policy.continuity_min
        and core_activity >= hard_gap_trust_policy.activity_min
    )
    dark_separator_like = (
        core_mean <= hard_gap_trust_policy.dark_mean_max
        and core_dark >= hard_gap_trust_policy.dark_fraction_min
        and core_activity <= hard_gap_trust_policy.dark_activity_max
    )
    weak_dark_gap = (
        core_mean >= hard_gap_trust_policy.weak_mean_min
        and core_content >= hard_gap_trust_policy.weak_content_min
    )
    if gap.method in HARD_GAP_METHODS:
        if bool(nearby.get("stronger_found", False)):
            record["hard_trust"] = "nearby_separator_conflict"
        elif model_delta_ratio >= hard_gap_trust_policy.model_delta_ratio and (
            width_ratio < hard_gap_trust_policy.geometry_width_ratio
            or gap.score < hard_gap_trust_policy.model_conflict_score
        ):
            record["hard_trust"] = "geometry_conflict"
        elif width_ratio < hard_gap_trust_policy.frame_border_width_ratio and dark_separator_like:
            record["hard_trust"] = "suspect_frame_border"
        elif narrow_hard and (content_continuous or weak_dark_gap):
            record["hard_trust"] = "suspect_internal_edge"
        elif narrow_hard:
            record["hard_trust"] = "narrow_but_ok"
        elif (
            dark_separator_like
            or core_content <= hard_gap_trust_policy.strong_core_content_max
            or gap.score >= hard_gap_trust_policy.strong_min_score
        ):
            record["hard_trust"] = "strong_separator"
        else:
            record["hard_trust"] = "weak_or_ambiguous_separator"
    elif gap.method in MODEL_GAP_METHODS:
        if dark_separator_like:
            overlap_risk = "none"
        elif (
            continuity >= overlap_policy.strong_continuity
            and core_activity >= overlap_policy.strong_activity
            and core_mean >= overlap_policy.mean_min
        ):
            overlap_risk = "strong"
        elif (
            continuity >= overlap_policy.medium_continuity
            and core_activity >= overlap_policy.medium_activity
            and core_mean >= overlap_policy.mean_min
        ):
            overlap_risk = "medium"
        elif (
            continuity >= overlap_policy.weak_continuity
            and core_activity >= overlap_policy.weak_activity
            and core_mean >= overlap_policy.mean_min
        ):
            overlap_risk = "weak"
        else:
            overlap_risk = "none"
        record["overlap_risk"] = overlap_risk
        record["overlap_like"] = overlap_risk in {"medium", "strong"}
    return record
