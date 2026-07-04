from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from .....constants import HARD_GAP_METHODS
from .....domain import Box, Detection
from .....formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from .....geometry.boxes import original_box_to_work
from .....policies.registry import get_detection_policy
from .....policies.runtime.policy import DetectionPolicy
from .....cache import AnalysisCache
from .....runtime.config import RuntimeConfig
from .....utils import box_from_dict, clamp_int
from .policy import correction_axes_allowed, correction_family_available
from .types import OuterCorrectionProposal


def corrected_outer_for_short_axis_geometry(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    cache: AnalysisCache,
    explicit_count: bool,
    policy: Optional[DetectionPolicy] = None,
) -> Optional[Box]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    short_axis = policy.outer.correction.geometry_consistency.short_axis
    family = short_axis.family
    if not short_axis.enabled or not correction_family_available(family, detection, explicit_count):
        return None
    candidate = detection.detail.get("candidate_assessment", {})
    if not isinstance(candidate, dict) or candidate.get("source") != "separator":
        return None
    hard_detail = candidate.get("separator_hard_evidence", {})
    if not isinstance(hard_detail, dict) or not bool(hard_detail.get("ok", False)):
        return None
    if str(content_detail.get("support", "")) != "aspect_conflict":
        return None
    max_aspect_error = content_detail.get("max_aspect_error")
    if max_aspect_error is None or float(max_aspect_error) < short_axis.min_error:
        return None

    source_h, source_w = gray.shape
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return None
    pitch = float(outer.width) / float(max(1, detection.count))
    target_aspect = float(short_axis.target_aspect)
    if target_aspect <= 0.0:
        target_aspect = float(CONTENT_ASPECTS_HORIZONTAL.get(fmt.name) or 1.0)
    target_aspect = max(0.01, target_aspect)
    target_height = pitch / target_aspect
    if target_height <= float(outer.height):
        return None

    margin = clamp_int(
        pitch * short_axis.margin_ratio,
        short_axis.margin_min,
        short_axis.margin_max,
    )
    target_height = min(float(work_h), target_height + float(margin * 2))
    center = (float(outer.top) + float(outer.bottom)) * 0.5
    top = int(round(center - target_height * 0.5))
    bottom = int(round(center + target_height * 0.5))
    if top < 0:
        bottom -= top
        top = 0
    if bottom > work_h:
        top -= bottom - work_h
        bottom = work_h
    top = max(0, top)
    bottom = min(work_h, bottom)
    corrected = Box(outer.left, top, outer.right, bottom)
    if not corrected.valid() or corrected == outer:
        return None
    if corrected.height <= outer.height:
        return None
    expand_ratio = float(corrected.height - outer.height) / max(1.0, float(outer.height))
    if family.max_expand_ratio > 0.0 and expand_ratio > family.max_expand_ratio:
        return None
    if not correction_axes_allowed(family, outer, corrected):
        return None
    return corrected


def geometry_consistency_model_detail(gray: np.ndarray, detection: Detection, config: RuntimeConfig, fmt: FormatSpec, cache: AnalysisCache) -> dict[str, Any]:
    if detection.count <= 0:
        return {"used": False, "reason": "invalid_count"}
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return {"used": False, "reason": "unknown_format_aspect"}
    source_h, source_w = gray.shape
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid() or outer.height <= 0:
        return {"used": False, "reason": "invalid_outer"}

    hard_gaps = [gap for gap in detection.gaps if gap.method in HARD_GAP_METHODS]
    measured_widths: list[float] = []
    complete_measured = True
    for gap in detection.gaps:
        if gap.method not in HARD_GAP_METHODS or gap.start is None or gap.end is None:
            complete_measured = False
            continue
        measured_widths.append(max(0.0, float(gap.end) - float(gap.start)))

    base_ratio = float(detection.count) * float(aspect)
    measured_separator_total = float(sum(measured_widths))
    actual_ratio = float(outer.width) / max(1.0, float(outer.height))
    expected_ratio_from_measured = base_ratio + measured_separator_total / max(1.0, float(outer.height))
    return {
        "used": True,
        "format": fmt.name,
        "count": int(detection.count),
        "frame_aspect": float(aspect),
        "base_ratio": float(base_ratio),
        "actual_outer_ratio": float(actual_ratio),
        "measured_separator_total": float(measured_separator_total),
        "expected_ratio_from_measured_separators": float(expected_ratio_from_measured),
        "extra_ratio": float(actual_ratio - base_ratio),
        "unexplained_extra_ratio": float(actual_ratio - expected_ratio_from_measured),
        "hard_gap_count": int(len(hard_gaps)),
        "expected_gap_count": int(max(0, detection.count - 1)),
        "complete_measured_hard_gaps": bool(complete_measured and len(measured_widths) == max(0, detection.count - 1)),
        "outer_work_box": asdict(outer),
        "work_width": int(work_w),
        "work_height": int(work_h),
    }


def corrected_outer_from_long_axis_geometry(
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    geometry_detail: dict[str, Any],
    alignment: dict[str, Any],
    cache: AnalysisCache,
    explicit_count: bool,
    policy: Optional[DetectionPolicy] = None,
) -> Optional[Box]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    long_axis = policy.outer.correction.geometry_consistency.long_axis
    family = long_axis.family
    if not long_axis.enabled or not correction_family_available(family, detection, explicit_count):
        return None
    if not bool(geometry_detail.get("used", False)):
        return None
    if family.requires_complete_hard_gaps and not bool(geometry_detail.get("complete_measured_hard_gaps", False)):
        return None

    unexplained = float(geometry_detail.get("unexplained_extra_ratio", 0.0) or 0.0)
    if unexplained <= long_axis.ratio_tolerance:
        return None

    try:
        outer = box_from_dict(geometry_detail["outer_work_box"])
    except Exception:
        return None
    if not outer.valid():
        return None
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return None

    gap_widths: list[float] = []
    for gap in detection.gaps:
        if gap.method not in HARD_GAP_METHODS or gap.start is None or gap.end is None:
            return None
        gap_widths.append(max(0.0, float(gap.end) - float(gap.start)))

    frame_long = float(outer.height) * float(aspect)
    left_estimates: list[float] = []
    right_estimates: list[float] = []
    for gap in detection.gaps:
        index = int(gap.index)
        width = max(0.0, float(gap.end) - float(gap.start))
        previous_width = float(sum(gap_widths[: max(0, index - 1)]))
        next_width = float(sum(gap_widths[index:]))
        left_estimates.append(float(outer.left) + float(gap.start) - (float(index) * frame_long + previous_width))
        right_estimates.append(float(outer.left) + float(gap.end) + (float(detection.count - index) * frame_long + next_width))

    if not left_estimates or not right_estimates:
        return None

    proposed_left = int(round(float(np.median(np.array(left_estimates, dtype=np.float64)))))
    proposed_right = int(round(float(np.median(np.array(right_estimates, dtype=np.float64)))))
    work_w = int(geometry_detail.get("work_width", cache.gray_work.shape[1]))
    proposed_left = max(0, min(proposed_left, work_w - 1))
    proposed_right = max(proposed_left + 1, min(proposed_right, work_w))
    corrected = Box(proposed_left, outer.top, proposed_right, outer.bottom)
    if not corrected.valid() or corrected == outer:
        return None

    shrink = float(outer.width - corrected.width)
    if shrink <= 0:
        return None
    shrink_ratio = shrink / max(1.0, float(outer.width))
    if shrink_ratio < long_axis.min_shrink_ratio:
        return None
    if shrink_ratio > long_axis.max_shrink_ratio:
        return None
    if family.max_shrink_ratio > 0.0 and shrink_ratio > family.max_shrink_ratio:
        return None

    actual_ratio = float(geometry_detail.get("actual_outer_ratio", 0.0) or 0.0)
    expected_ratio = float(geometry_detail.get("expected_ratio_from_measured_separators", 0.0) or 0.0)
    corrected_ratio = float(corrected.width) / max(1.0, float(corrected.height))
    if abs(corrected_ratio - expected_ratio) >= abs(actual_ratio - expected_ratio):
        return None

    if bool(alignment.get("used", False)) and "content_work_box" in alignment:
        try:
            content = box_from_dict(alignment["content_work_box"])
        except Exception:
            content = None
        if content is not None and content.valid():
            margin = clamp_int(
                float(outer.height) * long_axis.content_margin_ratio,
                long_axis.content_margin_min,
                long_axis.content_margin_max,
            )
            if corrected.left > content.left - margin or corrected.right < content.right + margin:
                return None

    if corrected.width < max(80, int(round(outer.width * 0.80))):
        return None
    if not correction_axes_allowed(family, outer, corrected):
        return None
    return corrected


def geometry_consistency_correction_proposal(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
    explicit_count: bool,
) -> Optional[OuterCorrectionProposal]:
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    corrected_outer = corrected_outer_for_short_axis_geometry(
        gray,
        config,
        fmt,
        detection,
        content_detail,
        cache,
        explicit_count,
        policy=policy,
    )
    if corrected_outer is not None:
        return OuterCorrectionProposal(
            box=corrected_outer,
            name="geometry_consistency_short_axis_outer",
            strategy="geometry_consistency_correction",
            source_reason="short_axis_aspect_conflict",
            original_outer_work_box=detection.detail.get("work_outer"),
            suppress_outer_mismatch=True,
            detail={"correction_kind": "short_axis"},
        )

    geometry_detail = geometry_consistency_model_detail(gray, detection, config, fmt, cache)
    detection.detail["geometry_consistency_model"] = geometry_detail
    corrected_outer = corrected_outer_from_long_axis_geometry(
        detection,
        config,
        fmt,
        geometry_detail,
        outer_alignment,
        cache,
        explicit_count,
        policy=policy,
    )
    if corrected_outer is None:
        return None

    return OuterCorrectionProposal(
        box=corrected_outer,
        name="geometry_consistency_long_axis_outer",
        strategy="geometry_consistency_correction",
        source_reason="long_axis_geometry_unexplained_outer_extra",
        original_outer_work_box=geometry_detail.get("outer_work_box"),
        preserve_separator_width_profile=True,
        detail={
            "correction_kind": "long_axis",
            "source_geometry_consistency": geometry_detail,
        },
    )


__all__ = [
    "corrected_outer_for_short_axis_geometry",
    "corrected_outer_from_long_axis_geometry",
    "geometry_consistency_correction_proposal",
    "geometry_consistency_model_detail",
]
