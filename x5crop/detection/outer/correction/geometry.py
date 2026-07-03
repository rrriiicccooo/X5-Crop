from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ....constants import HARD_GAP_METHODS
from ....domain import Box, Detection
from ....formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ....geometry.boxes import original_box_to_work
from ....policies.registry import get_detection_policy
from ....policies.runtime_policy import DetectionPolicy
from ....runtime import AnalysisCache
from ....runtime_config import RuntimeConfig
from ....utils import box_from_dict, clamp_int
from ...evidence.outer_alignment import outer_content_alignment_detail


def corrected_outer_for_short_axis_aspect(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    cache: AnalysisCache,
    policy: Optional[DetectionPolicy] = None,
) -> Optional[Box]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    short_axis_retry = policy.outer.short_axis_aspect_retry
    if not short_axis_retry.enabled:
        return None
    if detection.strip_mode != "full" or detection.count != fmt.default_count:
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
    if max_aspect_error is None or float(max_aspect_error) < short_axis_retry.min_error:
        return None

    source_h, source_w = gray.shape
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return None
    pitch = float(outer.width) / float(max(1, detection.count))
    target_aspect = max(0.01, float(short_axis_retry.target_aspect))
    target_height = pitch / target_aspect
    if target_height <= float(outer.height):
        return None

    margin = clamp_int(
        pitch * short_axis_retry.margin_ratio,
        short_axis_retry.margin_min,
        short_axis_retry.margin_max,
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
    return corrected


def format_geometry_model_detail(gray: np.ndarray, detection: Detection, config: RuntimeConfig, fmt: FormatSpec, cache: AnalysisCache) -> dict[str, Any]:
    if detection.strip_mode != "full" or detection.count <= 0:
        return {"used": False, "reason": "not_full_strip"}
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


def corrected_outer_from_format_geometry(
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    geometry_detail: dict[str, Any],
    alignment: dict[str, Any],
    cache: AnalysisCache,
    policy: Optional[DetectionPolicy] = None,
) -> Optional[Box]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    retry_policy = policy.outer.format_geometry_retry
    if not retry_policy.enabled:
        return None
    if detection.strip_mode != "full" or detection.count != fmt.default_count:
        return None
    if not bool(geometry_detail.get("used", False)):
        return None
    if not bool(geometry_detail.get("complete_measured_hard_gaps", False)):
        return None

    unexplained = float(geometry_detail.get("unexplained_extra_ratio", 0.0) or 0.0)
    if unexplained <= retry_policy.ratio_tolerance:
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
    if shrink_ratio < retry_policy.min_shrink_ratio:
        return None
    if shrink_ratio > retry_policy.max_shrink_ratio:
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
                float(outer.height) * retry_policy.content_margin_ratio,
                retry_policy.content_margin_min,
                retry_policy.content_margin_max,
            )
            if corrected.left > content.left - margin or corrected.right < content.right + margin:
                return None

    if corrected.width < max(80, int(round(outer.width * 0.80))):
        return None
    return corrected


def retry_with_geometry_outer_correction(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
) -> tuple[Optional[Detection], bool]:
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    corrected_outer = corrected_outer_for_short_axis_aspect(
        gray,
        config,
        fmt,
        detection,
        content_detail,
        cache,
        policy=policy,
    )
    if corrected_outer is not None:
        return (
            _retry_with_corrected_geometry_outer(
                gray,
                config,
                fmt,
                detection,
                corrected_outer,
                cache,
                policy,
                candidate_name="short_axis_aspect_outer",
                candidate_strategy="short_axis_retry",
                source_reason="short_axis_aspect_conflict",
                original_outer_work_box=detection.detail.get("work_outer"),
                source_format_geometry=None,
                preserve_wide_retry=False,
            ),
            True,
        )

    geometry_detail = format_geometry_model_detail(gray, detection, config, fmt, cache)
    detection.detail["format_geometry_model"] = geometry_detail
    corrected_outer = corrected_outer_from_format_geometry(
        detection,
        config,
        fmt,
        geometry_detail,
        outer_alignment,
        cache,
        policy=policy,
    )
    if corrected_outer is None:
        return None, False

    retried = _retry_with_corrected_geometry_outer(
        gray,
        config,
        fmt,
        detection,
        corrected_outer,
        cache,
        policy,
        candidate_name="format_geometry_outer",
        candidate_strategy="format_geometry_retry",
        source_reason="format_geometry_unexplained_outer_extra",
        original_outer_work_box=geometry_detail.get("outer_work_box"),
        source_format_geometry=geometry_detail,
        preserve_wide_retry=True,
    )
    return retried, False


def _retry_with_corrected_geometry_outer(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    corrected_outer: Box,
    cache: AnalysisCache,
    policy: DetectionPolicy,
    *,
    candidate_name: str,
    candidate_strategy: str,
    source_reason: str,
    original_outer_work_box: Any,
    source_format_geometry: Optional[dict[str, Any]],
    preserve_wide_retry: bool,
) -> Detection:
    from ...candidate.build import build_detection_for_outer
    from ...candidate.candidate_assessment import apply_candidate_assessment_policy
    from ...evidence.content_evidence import content_evidence_detail

    gap_override = None
    wide_retry = detection.detail.get("wide_gap_retry")
    if preserve_wide_retry and isinstance(wide_retry, dict) and bool(wide_retry.get("used", False)):
        gap_override = float(wide_retry.get("retry_gap_max_width_ratio", policy.separator.wide_retry_max_width_ratio))

    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        candidate_name,
        candidate_strategy,
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=gap_override,
        policy=policy,
    )
    retried = apply_candidate_assessment_policy(gray, retried, config, fmt, "separator", cache, policy=policy)
    retry_alignment = outer_content_alignment_detail(gray, retried, cache, policy=policy)
    retry_content = content_evidence_detail(gray, retried, cache, policy.content)
    retry_geometry = format_geometry_model_detail(gray, retried, config, fmt, cache)
    retried.detail["outer_content_alignment"] = retry_alignment
    retried.detail["content_evidence"] = retry_content
    if source_format_geometry is not None:
        retried.detail["format_geometry_model"] = retry_geometry
    retried.detail["outer_correction"] = {
        "used": True,
        "source_reason": source_reason,
        "original_outer_work_box": original_outer_work_box,
        "corrected_outer_work_box": asdict(corrected_outer),
        "retry_alignment": retry_alignment,
        "retry_content_support": retry_content.get("support"),
    }
    if source_format_geometry is not None:
        retried.detail["outer_correction"]["source_format_geometry"] = source_format_geometry
        retried.detail["outer_correction"]["retry_format_geometry"] = retry_geometry
    if gap_override is not None:
        retried.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
            "retry_gap_max_width_ratio": float(gap_override),
            "preserved_through_outer_retry": True,
        }
    return retried
