from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ....domain import DetectionCandidate
from ....geometry.layout import work_gray
from ....image.evidence import make_content_evidence_gray
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....utils import clamp_int
from ...evidence.photo_width import photo_width_stability_detail
from ...evidence.separator_summary import separator_support_detail_summary


def partial_edge_safety_leading_content_detail(
    gray: np.ndarray,
    detection: DetectionCandidate,
    cache: Optional[AnalysisCache],
    policy: DetectionPolicy,
) -> dict[str, Any]:
    holder_policy = policy.partial_holder
    holder = holder_policy.parameters
    if not holder_policy.enabled or detection.strip_mode != "partial":
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
    band_min_px = int(holder.leading_content_band_min_px)
    band_max_ratio = float(holder.leading_content_band_max_ratio)
    band = clamp_int(
        pitch * float(holder.leading_content_band_ratio),
        band_min_px,
        max(band_min_px, int(max(float(band_min_px), pitch * band_max_ratio))),
    )

    if cache is not None and cache.layout == detection.layout:
        evidence = cache.content_evidence_float_work
    else:
        gray_work = work_gray(gray, detection.layout)
        evidence = make_content_evidence_gray(
            gray_work,
            policy.content.evidence_image,
        ).astype(np.float32) / 255.0

    left = max(0, min(left, evidence.shape[1]))
    right = max(0, min(right, evidence.shape[1]))
    top = max(0, min(top, evidence.shape[0]))
    bottom = max(0, min(bottom, evidence.shape[0]))
    band_right = max(left, min(right, left + band))
    sample = evidence[top:bottom, left:band_right]
    if sample.size == 0:
        return {"used": False, "reason": "empty_sample"}

    mean = float(sample.mean())
    signal_threshold = float(holder.leading_content_signal_threshold)
    coverage = float((sample > signal_threshold).mean())
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
        "band_min_px": int(band_min_px),
        "band_max_ratio": float(band_max_ratio),
        "signal_threshold": float(signal_threshold),
        "max_mean": float(holder.leading_content_max_mean),
        "max_coverage": float(holder.leading_content_max_coverage),
    }


def partial_edge_safety_frame_content_detail(
    content_detail: dict[str, Any],
    detection: DetectionCandidate,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    holder_policy = policy.partial_holder
    holder = holder_policy.parameters
    if not holder_policy.enabled or detection.strip_mode != "partial":
        return {"used": False, "reason": "disabled"}
    frame_scores = content_detail.get("frame_scores", [])
    if not isinstance(frame_scores, list) or not frame_scores:
        return {"used": True, "ok": False, "reason": "missing_frame_scores", "frame_count": 0}

    min_mean = float(holder.min_frame_mean)
    min_coverage = float(holder.min_frame_coverage)
    max_aspect_error = float(holder_policy.max_frame_aspect_error)
    weak_frames: list[int] = []
    aspect_conflict_frames: list[int] = []
    normalized_scores: list[dict[str, Any]] = []
    content_frame_count = 0
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
        content_present = bool(
            item.get(
                "content_present",
                mean >= min_mean or coverage >= min_coverage,
            )
        )
        if not content_present:
            normalized_scores.append(
                {
                    "index": index,
                    "mean": mean,
                    "coverage": coverage,
                    "aspect_error": aspect_error,
                    "content_present": False,
                }
            )
            continue
        content_frame_count += 1
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
                "content_present": True,
            }
        )

    ok = (
        content_frame_count > 0
        and not weak_frames
        and not aspect_conflict_frames
    )
    return {
        "used": True,
        "ok": bool(ok),
        "reason": "ok" if ok else "frame_content_not_stable",
        "frame_count": int(len(normalized_scores)),
        "content_frame_count": int(content_frame_count),
        "expected_count": int(detection.count),
        "weak_frames": weak_frames,
        "aspect_conflict_frames": aspect_conflict_frames,
        "min_mean": min_mean,
        "min_coverage": min_coverage,
        "max_aspect_error": max_aspect_error,
        "frame_scores": normalized_scores,
    }


def partial_edge_safety_assessment_detail(
    gray: np.ndarray,
    detection: DetectionCandidate,
    hard_detail: dict[str, Any],
    content_detail: dict[str, Any],
    source: str,
    holder_occupancy: dict[str, Any],
    cache: Optional[AnalysisCache],
    *,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    holder_policy = policy.partial_holder
    holder = holder_policy.parameters
    separator_evidence = separator_support_detail_summary(hard_detail)
    expected = separator_evidence.expected_gaps
    hard = separator_evidence.hard_separator_gaps
    equal = separator_evidence.equal_model_gaps
    grid = separator_evidence.grid_model_gaps
    width_cv_value = detection.detail.get("width_cv", None)
    width_cv = 1.0 if width_cv_value is None else float(width_cv_value)
    width_cv_source = str(detection.detail.get("width_cv_source") or "unknown")
    outer_area = float(detection.detail.get("outer_area_ratio", 1.0) or 1.0)
    min_count = holder.minimum_observed_frame_count
    hard_ratio = 1.0 if expected <= 0 else hard / float(max(1, expected))
    leading_content = partial_edge_safety_leading_content_detail(gray, detection, cache, policy)
    frame_content = partial_edge_safety_frame_content_detail(content_detail, detection, policy)
    complete_underfilled_strip = bool(holder_occupancy.get("complete_underfilled_strip", False))
    applicable = bool(
        holder_policy.enabled
        and detection.strip_mode == "partial"
        and source == "separator"
    )
    if not applicable:
        return {
            "used": False,
            "state": "not_applicable",
            "reason": "not_partial_separator_candidate",
            "count": int(detection.count),
            "holder_policy": {"enabled": holder_policy.enabled},
        }

    preservation_failures: list[str] = []
    occupancy_diagnostics: list[str] = []
    leading_content_strong = (
        bool(leading_content.get("used", False))
        and not bool(leading_content.get("ok", True))
    )
    photo_width_stability = photo_width_stability_detail(
        detection.detail,
        float(holder.max_photo_width_cv),
        used_role="photo_width_assessment",
    )
    if not complete_underfilled_strip and leading_content_strong:
        preservation_failures.append("partial_edge_content_present")
    elif complete_underfilled_strip and leading_content_strong:
        occupancy_diagnostics.append("leading_content_not_used_as_holder_edge_blocker_for_complete_underfilled_strip")
    if bool(frame_content.get("used", False)) and not bool(frame_content.get("ok", True)):
        occupancy_diagnostics.append("partial_frame_content_measurement_unavailable")
    boundary_support = bool(
        detection.count >= min_count
        and expected > 0
        and hard >= holder.min_hard_gaps
        and hard_ratio >= holder.min_hard_ratio
        and equal <= holder.max_equal_gaps
        and not bool(photo_width_stability["unstable"])
    )
    return {
        "used": True,
        "state": "contradicted" if preservation_failures else "supported",
        "reason": (
            "partial_edge_safety_supported"
            if not preservation_failures
            else "partial_edge_content_contradicted"
        ),
        "preservation_failures": preservation_failures,
        "boundary_support": boundary_support,
        "count": int(detection.count),
        "expected_gaps": int(expected),
        "hard_gaps": int(hard),
        "grid_gaps": int(grid),
        "equal_gaps": int(equal),
        "hard_ratio": float(hard_ratio),
        "width_cv": float(width_cv),
        "width_cv_source": width_cv_source,
        "photo_width_stability": photo_width_stability,
        "outer_area_ratio": float(outer_area),
        "strip_completeness": holder_occupancy.get("strip_completeness", {}),
        "holder_occupancy": holder_occupancy,
        "complete_underfilled_strip": complete_underfilled_strip,
        "occupancy_diagnostics": occupancy_diagnostics,
        "policy_id": policy.policy_id,
        "holder_policy": {
            "enabled": holder_policy.enabled,
            "max_frame_aspect_error": holder_policy.max_frame_aspect_error,
        },
        "leading_content": leading_content,
        "frame_content": frame_content,
    }
