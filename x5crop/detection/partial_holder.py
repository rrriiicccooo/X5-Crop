from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..domain import Box, Detection
from ..formats import FormatSpec
from ..image.evidence import make_content_evidence_gray
from ..geometry.layout import work_gray
from ..policies.runtime_policy import DetectionPolicy
from ..policies.registry import get_detection_policy
from ..runtime import AnalysisCache
from ..utils import HARD_REVIEW_REASONS, clamp_int


def partial_safe_wide_like_gap_detail(
    detection: Detection,
    fmt: FormatSpec,
    policy: Optional[DetectionPolicy] = None,
) -> dict[str, Any]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    holder = policy.partial_holder
    min_required = int(holder.requires_wide_like_gaps)
    if min_required <= 0 or detection.strip_mode != "partial":
        return {
            "used": False,
            "reason": "disabled",
            "wide_like_gaps": 0,
            "min_wide_like_gaps": min_required,
        }

    work_outer_detail = detection.detail.get("work_outer", {})
    short_axis = 0.0
    if isinstance(work_outer_detail, dict):
        try:
            short_axis = float(work_outer_detail.get("bottom", 0.0)) - float(work_outer_detail.get("top", 0.0))
        except (TypeError, ValueError):
            short_axis = 0.0
    if short_axis <= 0.0:
        frames = [frame for frame in detection.frames if frame.valid()]
        short_axis = float(np.median(np.array([frame.width for frame in frames], dtype=np.float32))) if frames else 0.0

    min_width = max(1.0, short_axis * float(holder.wide_like_min_width_ratio))
    wide_like_indexes: list[int] = []
    gap_widths: list[float] = []
    for gap in detection.gaps:
        width = 0.0
        if gap.start is not None and gap.end is not None:
            width = max(0.0, float(gap.end) - float(gap.start))
        gap_widths.append(width)
        if gap.method == "wide-separator" or (gap.method in {"detected", "edge-pair"} and width >= min_width):
            wide_like_indexes.append(int(gap.index))

    ok = len(wide_like_indexes) >= min_required
    return {
        "used": True,
        "reason": "ok" if ok else "too_few_wide_like_gaps",
        "wide_like_gaps": int(len(wide_like_indexes)),
        "min_wide_like_gaps": int(min_required),
        "wide_like_gap_indexes": wide_like_indexes,
        "gap_widths": gap_widths,
        "min_width_px": float(min_width),
    }


def partial_safe_leading_content_detail(
    gray: np.ndarray,
    detection: Detection,
    fmt: FormatSpec,
    cache: Optional[AnalysisCache],
    policy: Optional[DetectionPolicy] = None,
) -> dict[str, Any]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    holder = policy.partial_holder
    if not holder.checks_leading_content or detection.strip_mode != "partial":
        return {"used": False, "reason": "disabled"}
    if str(detection.detail.get("outer_candidate_strategy", "")) != "content_outer":
        return {"used": False, "reason": "not_content_outer"}

    work_outer_detail = detection.detail.get("work_outer", {})
    if not isinstance(work_outer_detail, dict):
        return {"used": False, "reason": "missing_work_outer"}
    try:
        left = int(work_outer_detail["left"])
        top = int(work_outer_detail["top"])
        right = int(work_outer_detail["right"])
        bottom = int(work_outer_detail["bottom"])
    except (KeyError, TypeError, ValueError):
        return {"used": False, "reason": "invalid_work_outer"}
    if right <= left or bottom <= top:
        return {"used": False, "reason": "invalid_work_outer"}

    pitch_value = detection.detail.get("pitch", None)
    try:
        pitch = float(pitch_value) if pitch_value is not None else 0.0
    except (TypeError, ValueError):
        pitch = 0.0
    if pitch <= 0.0:
        pitch = (right - left) / float(max(1, detection.count))
    band = clamp_int(
        pitch * float(holder.leading_content_band_ratio),
        8,
        max(8, int(max(8.0, pitch * 0.12))),
    )

    if cache is not None and cache.layout == detection.layout:
        evidence = cache.content_evidence_float_work
    else:
        gray_work = work_gray(gray, detection.layout)
        evidence = make_content_evidence_gray(gray_work).astype(np.float32) / 255.0

    left = max(0, min(left, evidence.shape[1]))
    right = max(0, min(right, evidence.shape[1]))
    top = max(0, min(top, evidence.shape[0]))
    bottom = max(0, min(bottom, evidence.shape[0]))
    band_right = max(left, min(right, left + band))
    sample = evidence[top:bottom, left:band_right]
    if sample.size == 0:
        return {"used": False, "reason": "empty_sample"}

    mean = float(sample.mean())
    coverage = float((sample > 0.20).mean())
    ok = (
        mean <= float(holder.leading_content_max_mean)
        and coverage <= float(holder.leading_content_max_coverage)
    )
    return {
        "used": True,
        "ok": bool(ok),
        "reason": "ok" if ok else "leading_edge_content_too_strong",
        "mean": mean,
        "coverage": coverage,
        "band_px": int(band_right - left),
        "max_mean": float(holder.leading_content_max_mean),
        "max_coverage": float(holder.leading_content_max_coverage),
    }


def partial_safe_frame_content_detail(
    content_detail: dict[str, Any],
    detection: Detection,
    fmt: FormatSpec,
    policy: Optional[DetectionPolicy] = None,
) -> dict[str, Any]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    holder = policy.partial_holder
    if not holder.checks_frame_content or detection.strip_mode != "partial":
        return {"used": False, "reason": "disabled"}
    frame_scores = content_detail.get("frame_scores", [])
    if not isinstance(frame_scores, list) or not frame_scores:
        return {"used": True, "ok": False, "reason": "missing_frame_scores", "frame_count": 0}

    min_mean = float(holder.min_frame_mean)
    min_coverage = float(holder.min_frame_coverage)
    max_aspect_error = float(holder.max_frame_aspect_error)
    weak_frames: list[int] = []
    aspect_conflict_frames: list[int] = []
    normalized_scores: list[dict[str, Any]] = []
    for item in frame_scores:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index", len(normalized_scores) + 1))
            mean = float(item.get("mean", 0.0) or 0.0)
            coverage = float(item.get("coverage", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        aspect_error_value = item.get("aspect_error", None)
        try:
            aspect_error = None if aspect_error_value is None else float(aspect_error_value)
        except (TypeError, ValueError):
            aspect_error = None
        if mean < min_mean and coverage < min_coverage:
            weak_frames.append(index)
        if aspect_error is not None and aspect_error > max_aspect_error:
            aspect_conflict_frames.append(index)
        normalized_scores.append(
            {
                "index": index,
                "mean": mean,
                "coverage": coverage,
                "aspect_error": aspect_error,
            }
        )

    ok = (
        len(normalized_scores) >= detection.count
        and not weak_frames
        and not aspect_conflict_frames
    )
    return {
        "used": True,
        "ok": bool(ok),
        "reason": "ok" if ok else "frame_content_not_stable",
        "frame_count": int(len(normalized_scores)),
        "expected_count": int(detection.count),
        "weak_frames": weak_frames,
        "aspect_conflict_frames": aspect_conflict_frames,
        "min_mean": min_mean,
        "min_coverage": min_coverage,
        "max_aspect_error": max_aspect_error,
        "frame_scores": normalized_scores,
    }


def partial_extra_holder_frames_gate_detail(
    gray: np.ndarray,
    detection: Detection,
    hard_detail: dict[str, Any],
    content_detail: dict[str, Any],
    fmt: FormatSpec,
    source: str,
    joint_score: float,
    content_score: float,
    geometry_score: float,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> dict[str, Any]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    holder = policy.partial_holder
    expected = max(0, int(hard_detail.get("expected_gaps", 0) or 0))
    hard = int(hard_detail.get("hard_gaps", 0) or 0)
    equal = int(hard_detail.get("equal_gaps", 0) or 0)
    grid = int(hard_detail.get("grid_gaps", 0) or 0)
    width_cv_value = detection.detail.get("width_cv", None)
    width_cv = 1.0 if width_cv_value is None else float(width_cv_value)
    outer_area = float(detection.detail.get("outer_area_ratio", 1.0) or 1.0)
    min_count = holder.min_count_35mm if fmt.default_count >= 6 else holder.min_count_small
    hard_ratio = 1.0 if expected <= 0 else hard / float(max(1, expected))
    wide_like_detail = partial_safe_wide_like_gap_detail(detection, fmt, policy)
    leading_content = partial_safe_leading_content_detail(gray, detection, fmt, cache, policy)
    frame_content = partial_safe_frame_content_detail(content_detail, detection, fmt, policy)
    disqualifiers: list[str] = []
    if not holder.safe_extra_frames:
        disqualifiers.append("disabled")
    if detection.strip_mode != "partial":
        disqualifiers.append("not_partial")
    if source != "separator":
        disqualifiers.append("not_separator_candidate")
    if detection.count < min_count:
        disqualifiers.append("count_too_small")
    if expected <= 0:
        disqualifiers.append("no_internal_gaps")
    if str(content_detail.get("support", "")) != "ok":
        disqualifiers.append("content_not_ok")
    if hard < holder.min_hard_gaps:
        disqualifiers.append("too_few_hard_gaps")
    if hard_ratio < holder.min_hard_ratio:
        disqualifiers.append("hard_gap_ratio_low")
    if (
        bool(wide_like_detail.get("used", False))
        and int(wide_like_detail.get("wide_like_gaps", 0) or 0)
        < int(wide_like_detail.get("min_wide_like_gaps", 0) or 0)
    ):
        disqualifiers.append("too_few_wide_like_gaps")
    if equal > holder.max_equal_gaps:
        disqualifiers.append("equal_gap_used")
    if width_cv > holder.max_width_cv:
        disqualifiers.append("width_cv_unstable")
    if joint_score < holder.min_joint_score:
        disqualifiers.append("joint_score_low")
    if content_score < holder.min_content_score:
        disqualifiers.append("content_score_low")
    if geometry_score < holder.min_geometry_score:
        disqualifiers.append("geometry_score_low")
    hard_partial_blockers = HARD_REVIEW_REASONS.difference({"outer_box_too_large", "outer_box_uncertain"})
    if any(reason in detection.review_reasons for reason in hard_partial_blockers):
        disqualifiers.append("hard_review_reason_present")
    if bool(leading_content.get("used", False)) and not bool(leading_content.get("ok", True)):
        disqualifiers.append("partial_outer_leading_content")
    if bool(frame_content.get("used", False)) and not bool(frame_content.get("ok", True)):
        disqualifiers.append("partial_frame_content_unstable")
    return {
        "used": True,
        "ok": not disqualifiers,
        "reason": "safe_extra_holder_frames_accepted" if not disqualifiers else "not_safe_enough_for_auto",
        "disqualifiers": disqualifiers,
        "count": int(detection.count),
        "expected_gaps": int(expected),
        "hard_gaps": int(hard),
        "grid_gaps": int(grid),
        "equal_gaps": int(equal),
        "hard_ratio": float(hard_ratio),
        "width_cv": float(width_cv),
        "outer_area_ratio": float(outer_area),
        "joint_score": float(joint_score),
        "content_score": float(content_score),
        "geometry_score": float(geometry_score),
        "policy_id": policy.policy_id,
        "holder_policy": {
            "safe_extra_frames": holder.safe_extra_frames,
            "requires_wide_like_gaps": holder.requires_wide_like_gaps,
            "checks_leading_content": holder.checks_leading_content,
            "checks_frame_content": holder.checks_frame_content,
            "max_frame_aspect_error": holder.max_frame_aspect_error,
        },
        "wide_like_separator": wide_like_detail,
        "leading_content": leading_content,
        "frame_content": frame_content,
    }


__all__ = [
    "partial_extra_holder_frames_gate_detail",
    "partial_safe_frame_content_detail",
    "partial_safe_leading_content_detail",
    "partial_safe_wide_like_gap_detail",
]
