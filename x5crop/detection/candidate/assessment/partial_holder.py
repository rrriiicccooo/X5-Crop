from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ....domain import Box, Detection
from ....formats import FormatSpec
from ....geometry.layout import work_gray
from ....image.evidence import make_content_evidence_gray
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....cache import AnalysisCache
from ....utils import clamp_int
from ...evidence.photo_width import photo_width_stability_detail
from ...evidence.separator_summary import separator_gate_detail_summary
from ...evidence.separator_width import separator_width_evidence_detail, separator_width_requirement_detail
from ..signals import (
    SIGNAL_PARTIAL_LEADING_CONTENT_RISK,
    candidate_signals,
)
from .candidate_gate import candidate_signal_blocker_signals


def partial_safe_holder_edge_disambiguation_detail(
    detection: Detection,
    fmt: FormatSpec,
    policy: Optional[DetectionPolicy] = None,
) -> dict[str, Any]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    holder = policy.partial_holder
    min_required = int(holder.requires_broad_separator_width_gaps)
    if min_required <= 0 or detection.strip_mode != "partial":
        return {
            "used": False,
            "reason": "disabled",
            "holder_edge_disambiguation_gaps": 0,
            "min_holder_edge_disambiguation_gaps": min_required,
        }

    existing_detail = detection.detail.get("separator_width_evidence")
    if isinstance(existing_detail, dict) and bool(existing_detail.get("used", False)):
        width_detail = separator_width_requirement_detail(existing_detail, min_required)
        count = int(width_detail.get("separator_width_gap_count", width_detail.get("broad_separator_width_gaps", 0)) or 0)
        ok = count >= min_required
        return {
            "used": True,
            "ok": bool(ok),
            "reason": "ok" if ok else "holder_edge_disambiguation_weak",
            "evidence_source": "separator_width_evidence",
            "holder_edge_disambiguation_gaps": int(count),
            "min_holder_edge_disambiguation_gaps": int(min_required),
            "separator_width_evidence": width_detail,
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

    width_detail = separator_width_evidence_detail(
        detection.gaps,
        short_axis,
        float(holder.broad_separator_width_min_ratio),
        min_required,
    )
    count = int(width_detail.get("separator_width_gap_count", width_detail.get("broad_separator_width_gaps", 0)) or 0)
    ok = count >= min_required
    return {
        "used": True,
        "ok": bool(ok),
        "reason": "ok" if ok else "holder_edge_disambiguation_weak",
        "evidence_source": "separator_width_evidence",
        "holder_edge_disambiguation_gaps": int(count),
        "min_holder_edge_disambiguation_gaps": int(min_required),
        "separator_width_evidence": width_detail,
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


def partial_safe_extra_frames_gate_detail(
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
    separator_evidence = separator_gate_detail_summary(hard_detail)
    expected = separator_evidence.expected_gaps
    hard = separator_evidence.hard_separator_gaps
    equal = separator_evidence.equal_model_gaps
    grid = separator_evidence.grid_model_gaps
    width_cv_value = detection.detail.get("width_cv", None)
    width_cv = 1.0 if width_cv_value is None else float(width_cv_value)
    width_cv_source = str(detection.detail.get("width_cv_source") or "unknown")
    outer_area = float(detection.detail.get("outer_area_ratio", 1.0) or 1.0)
    min_count = holder.min_count_35mm if fmt.default_count >= 6 else holder.min_count_small
    hard_ratio = 1.0 if expected <= 0 else hard / float(max(1, expected))
    holder_edge_detail = partial_safe_holder_edge_disambiguation_detail(detection, fmt, policy)
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
    content_containment_ok = bool(content_detail.get("content_containment_ok", False))
    content_harm_risk = bool(content_detail.get("content_harm_risk", True))
    if not content_containment_ok or content_harm_risk:
        disqualifiers.append("content_harm_risk")
    if hard < holder.min_hard_gaps:
        disqualifiers.append("too_few_hard_gaps")
    if hard_ratio < holder.min_hard_ratio:
        disqualifiers.append("hard_gap_ratio_low")
    if (
        bool(holder_edge_detail.get("used", False))
        and int(holder_edge_detail.get("holder_edge_disambiguation_gaps", 0) or 0)
        < int(holder_edge_detail.get("min_holder_edge_disambiguation_gaps", 0) or 0)
    ):
        disqualifiers.append("holder_edge_disambiguation_weak")
    if equal > holder.max_equal_gaps:
        disqualifiers.append("equal_gap_used")
    photo_width_stability = photo_width_stability_detail(
        detection.detail,
        float(holder.max_photo_width_cv),
        used_role="photo_width_gate",
    )
    if bool(photo_width_stability["unstable"]):
        disqualifiers.append("photo_width_unstable")
    if joint_score < holder.min_joint_score:
        disqualifiers.append("joint_score_low")
    content_quality_ok = content_score >= holder.min_content_score
    if geometry_score < holder.min_geometry_score:
        disqualifiers.append("geometry_score_low")
    partial_candidate_gate_blockers = candidate_signal_blocker_signals(
        candidate_signals(detection),
    )
    if partial_candidate_gate_blockers:
        disqualifiers.append("candidate_gate_blocker_present")
    if bool(leading_content.get("used", False)) and not bool(leading_content.get("ok", True)):
        disqualifiers.append(SIGNAL_PARTIAL_LEADING_CONTENT_RISK)
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
        "width_cv_source": width_cv_source,
        "photo_width_stability": photo_width_stability,
        "outer_area_ratio": float(outer_area),
        "joint_score": float(joint_score),
        "content_score": float(content_score),
        "geometry_score": float(geometry_score),
        "content_quality": {
            "score": float(content_score),
            "min_quality_score": float(holder.min_content_score),
            "quality_ok": bool(content_quality_ok),
            "role": "quality_diagnostic_not_hard_gate",
        },
        "policy_id": policy.policy_id,
        "holder_policy": {
            "safe_extra_frames": holder.safe_extra_frames,
            "requires_holder_edge_disambiguation_gaps": holder.requires_broad_separator_width_gaps,
            "checks_leading_content": holder.checks_leading_content,
            "checks_frame_content": holder.checks_frame_content,
            "max_frame_aspect_error": holder.max_frame_aspect_error,
        },
        "holder_edge_disambiguation": holder_edge_detail,
        "leading_content": leading_content,
        "frame_content": frame_content,
    }


__all__ = [
    "partial_safe_extra_frames_gate_detail",
    "partial_safe_frame_content_detail",
    "partial_safe_leading_content_detail",
    "partial_safe_holder_edge_disambiguation_detail",
]
