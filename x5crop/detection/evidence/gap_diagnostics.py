from __future__ import annotations

import copy
from typing import Any, Optional

import numpy as np

from ...domain import Box, Detection, Gap
from ...gap_methods import gap_method_role, is_hard_gap_method, is_model_gap_method
from ...geometry.boxes import box_cache_key
from ...geometry.detection_parameters import SeparatorProfileParameters
from ...geometry.gap_trust import (
    diagnostic_hard_gap_trust_assessment,
    hard_gap_pixel_signals,
    hard_gap_tonal_separator_like,
    hard_gap_width_ratio,
)
from ...geometry.nearby_separator import nearby_separator_search_detail
from ...cache.separator import cached_separator_profile
from ...policies.runtime.diagnostics import NearbySeparatorDiagnosticsPolicy
from ...policies.runtime.output_evidence import OutputOverlapEvidencePolicy
from ...policies.runtime.separator import SeparatorPolicy
from ...cache import AnalysisCache
from ...utils import clamp_int


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
    profile_policy: SeparatorProfileParameters,
    cache: Optional[AnalysisCache] = None,
) -> dict[str, Any]:
    if not is_hard_gap_method(gap.method) or pitch <= 0:
        return {"searched": False, "reason": "not_hard_gap"}
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        cache_key = (
            "nearby_separator",
            profile_policy,
            nearby_policy,
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
    profile = cached_separator_profile(cache, gray_work, work_outer, profile_policy)
    if profile.size == 0:
        return {"searched": False, "reason": "empty_profile"}
    search_gap = Gap(
        gap.index,
        gap.center,
        gap.score,
        gap.method,
        float(start - work_outer.left),
        float(end - work_outer.left),
        gap.lane_box,
    )
    detail = nearby_separator_search_detail(
        profile,
        search_gap,
        pitch,
        nearby_policy,
        score_add=nearby_policy.detail_score_add,
        score_multiplier=nearby_policy.detail_score_multiplier,
        absolute_center_offset=float(work_outer.left),
    ) or {"searched": False, "reason": "empty_search_window"}
    if cache_key is not None and cache is not None:
        cache.nearby_separator_details[cache_key] = copy.deepcopy(detail)
    return detail


def gap_diagnostic_record(
    gray_work: np.ndarray,
    detection: Detection,
    gap: Gap,
    cache: Optional[AnalysisCache] = None,
    *,
    separator_policy: SeparatorPolicy,
    nearby_policy: NearbySeparatorDiagnosticsPolicy,
    output_overlap_policy: OutputOverlapEvidencePolicy,
) -> dict[str, Any]:
    hard_gap_trust_policy = separator_policy.hard_gap_trust
    work_outer = gap_work_outer(detection, gap)
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    origin = float(detection.detail.get("origin", 0.0) or 0.0)
    expected = origin + pitch * float(gap.index) if pitch > 0 else float(gap.center)
    role = gap_method_role(gap.method)
    record: dict[str, Any] = {
        "index": int(gap.index),
        "method": gap.method,
        "role": role,
        "used_for_assessment": True,
        "diagnostic_only": True,
        "center": float(gap.center),
        "expected_center": float(expected),
        "model_delta_px": float(gap.center - expected),
        "score": float(gap.score),
        "width_px": float(gap.width),
        "hard_trust": "not_hard_gap",
        "output_overlap_like": False,
        "output_overlap_class": "none",
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
    signal_gap = Gap(
        gap.index,
        gap.center,
        gap.score,
        gap.method,
        float(start - work_outer.left),
        float(end - work_outer.left),
        gap.lane_box,
    )
    signals = hard_gap_pixel_signals(gray_work, work_outer, signal_gap, pitch, hard_gap_trust_policy)
    if signals is None:
        record["signals"] = {"available": False}
        return record

    nearby = nearby_separator_candidate_detail(
        gray_work,
        work_outer,
        gap,
        pitch,
        start,
        end,
        nearby_policy,
        separator_policy.profile,
        cache,
    )
    record["signals"] = {
        "available": True,
        "core_mean": signals.core_mean,
        "core_content": signals.core_content,
        "core_dark": signals.core_dark,
        "core_activity": signals.core_activity,
        "left_content": signals.left_content,
        "right_content": signals.right_content,
        "side_content": signals.side_content,
        "side_balance": signals.side_balance,
        "continuity": signals.continuity,
        "window": {"start": int(signals.start), "end": int(signals.end), "guard": int(signals.guard)},
    }
    record["nearby_separator_candidate"] = nearby

    width_ratio = hard_gap_width_ratio(gap, pitch)
    model_delta_ratio = abs(float(gap.center - expected)) / max(1.0, float(pitch))
    if is_hard_gap_method(gap.method):
        trust_assessment = diagnostic_hard_gap_trust_assessment(
            gap,
            pitch,
            hard_gap_trust_policy,
            width_ratio=width_ratio,
            model_delta_ratio=model_delta_ratio,
            nearby_separator_conflict=bool(nearby.get("stronger_found", False)),
            signals=signals,
        )
        record["hard_trust"] = trust_assessment.trust
        record["hard_trust_detail"] = trust_assessment.detail()
    elif is_model_gap_method(gap.method):
        if hard_gap_tonal_separator_like(signals, hard_gap_trust_policy):
            output_overlap_class = "none"
        elif (
            signals.continuity >= output_overlap_policy.strong_continuity
            and signals.core_activity >= output_overlap_policy.strong_activity
            and signals.core_mean >= output_overlap_policy.mean_min
        ):
            output_overlap_class = "strong"
        elif (
            signals.continuity >= output_overlap_policy.medium_continuity
            and signals.core_activity >= output_overlap_policy.medium_activity
            and signals.core_mean >= output_overlap_policy.mean_min
        ):
            output_overlap_class = "medium"
        elif (
            signals.continuity >= output_overlap_policy.weak_continuity
            and signals.core_activity >= output_overlap_policy.weak_activity
            and signals.core_mean >= output_overlap_policy.mean_min
        ):
            output_overlap_class = "weak"
        else:
            output_overlap_class = "none"
        record["output_overlap_class"] = output_overlap_class
        record["output_overlap_like"] = output_overlap_class in {"medium", "strong"}
    return record
