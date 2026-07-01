from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ..config import Config
from ..constants import HARD_GAP_METHODS
from ..domain import Box, Detection
from ..formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ..geometry import box_cache_key, original_box_to_work, work_gray
from ..policies.base import DetectionPolicy
from ..policies.registry import get_detection_policy
from ..runtime import AnalysisCache
from ..utils import bbox_from_mask, box_from_dict, clamp_int
from .cache_keys import detection_gap_cache_key


def outer_alignment_cache_key(detection: Detection, source_w: int, source_h: int) -> tuple[Any, ...]:
    return (
        str(detection.film_format),
        str(detection.layout),
        str(detection.strip_mode),
        int(detection.count),
        int(source_w),
        int(source_h),
        box_cache_key(detection.outer),
        tuple(detection_gap_cache_key(detection)),
    )


def outer_content_alignment_detail(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> dict[str, Any]:
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    alignment = policy.outer.content_alignment
    work_h, work_w = gray_work.shape
    source_h, source_w = gray.shape
    detail_key: Optional[tuple[Any, ...]] = None
    if cache is not None and cache.layout == detection.layout:
        detail_key = outer_alignment_cache_key(detection, source_w, source_h)
        cached = cache.outer_alignment_details.get(detail_key)
        if cached is not None:
            return copy.deepcopy(cached)
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    candidates: list[tuple[str, Box]] = []
    for threshold in (225, 210, 190):
        box = bbox_from_mask(gray_work < threshold, min_row_fraction=0.015, min_col_fraction=0.015)
        if box is not None and box.valid():
            candidates.append((f"gray_lt_{threshold}", box))
    if not candidates:
        return {"used": False, "reason": "no_content_bbox"}

    source, content_box = candidates[0]
    pitch = float(outer.width) / float(max(1, detection.count))
    long_slack_left = max(0, content_box.left - outer.left)
    long_slack_right = max(0, outer.right - content_box.right)
    short_slack_top = max(0, content_box.top - outer.top)
    short_slack_bottom = max(0, outer.bottom - content_box.bottom)
    max_long_slack = max(long_slack_left, long_slack_right)
    max_short_slack = max(short_slack_top, short_slack_bottom)
    long_slack_ratio = float(max_long_slack) / max(1.0, pitch)
    short_slack_ratio = float(max_short_slack) / max(1.0, float(outer.height))
    content_width_ratio = float(content_box.width) / max(1.0, float(outer.width))
    content_height_ratio = float(content_box.height) / max(1.0, float(outer.height))
    white_edge_long_slack_min = clamp_int(
        pitch * alignment.white_edge_long_ratio,
        alignment.white_edge_long_min,
        alignment.white_edge_long_max,
    )
    long_slack_pixel_gate = clamp_int(
        pitch * alignment.long_gate_ratio,
        alignment.long_gate_min,
        alignment.long_gate_max,
    )
    short_slack_pixel_gate = clamp_int(
        float(outer.height) * alignment.short_gate_ratio,
        alignment.short_gate_min,
        alignment.short_gate_max,
    )

    edge_band = max(4, min(80, int(round(min(outer.width, outer.height) * alignment.border_band_ratio))))
    outer_crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if outer_crop.size:
        left_band = outer_crop[:, :min(edge_band, outer_crop.shape[1])]
        right_band = outer_crop[:, max(0, outer_crop.shape[1] - edge_band):]
        top_band = outer_crop[:min(edge_band, outer_crop.shape[0]), :]
        bottom_band = outer_crop[max(0, outer_crop.shape[0] - edge_band):, :]
        border_dark_fraction = {
            "left": float((left_band < 245).mean()) if left_band.size else 0.0,
            "right": float((right_band < 245).mean()) if right_band.size else 0.0,
            "top": float((top_band < 245).mean()) if top_band.size else 0.0,
            "bottom": float((bottom_band < 245).mean()) if bottom_band.size else 0.0,
        }
    else:
        border_dark_fraction = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}

    edge_hard_anchors = (
        detection.strip_mode == "full"
        and len(detection.gaps) >= 2
        and detection.gaps[0].method in HARD_GAP_METHODS
        and detection.gaps[-1].method in HARD_GAP_METHODS
    )
    white_edge_slack = (
        edge_hard_anchors
        and content_width_ratio >= alignment.content_width_min
        and max_short_slack <= max(24, int(round(float(outer.height) * alignment.edge_short_ratio)))
        and (
            (long_slack_left >= white_edge_long_slack_min and float(border_dark_fraction.get("left", 1.0)) <= alignment.edge_dark_max)
            or (long_slack_right >= white_edge_long_slack_min and float(border_dark_fraction.get("right", 1.0)) <= alignment.edge_dark_max)
        )
    )
    short_axis_semantic_ok = True
    if alignment.short_requires_hard_anchors:
        short_axis_semantic_ok = short_axis_semantic_ok and edge_hard_anchors
    if alignment.short_content_height_max < 1.0:
        short_axis_semantic_ok = short_axis_semantic_ok and content_height_ratio <= alignment.short_content_height_max

    excess_long = long_slack_ratio > alignment.long_excess_ratio or (max_long_slack >= long_slack_pixel_gate and long_slack_ratio > alignment.long_gate_excess_ratio) or white_edge_slack
    excess_short = short_axis_semantic_ok and short_slack_ratio > alignment.short_excess_ratio and max_short_slack >= short_slack_pixel_gate
    ok = not (excess_long or excess_short)
    reason = "ok"
    if excess_long:
        reason = "outer_long_axis_excess"
    elif excess_short:
        reason = "outer_short_axis_excess"

    detail = {
        "used": True,
        "ok": ok,
        "reason": reason,
        "content_bbox_source": source,
        "outer_work_box": asdict(outer),
        "content_work_box": asdict(content_box),
        "long_slack_left": int(long_slack_left),
        "long_slack_right": int(long_slack_right),
        "short_slack_top": int(short_slack_top),
        "short_slack_bottom": int(short_slack_bottom),
        "max_long_slack": int(max_long_slack),
        "max_short_slack": int(max_short_slack),
        "long_slack_ratio": long_slack_ratio,
        "short_slack_ratio": short_slack_ratio,
        "content_width_ratio": content_width_ratio,
        "content_height_ratio": content_height_ratio,
        "white_edge_long_slack_min": int(white_edge_long_slack_min),
        "long_slack_pixel_gate": int(long_slack_pixel_gate),
        "short_slack_pixel_gate": int(short_slack_pixel_gate),
        "border_dark_fraction": border_dark_fraction,
        "edge_hard_anchors": edge_hard_anchors,
        "white_edge_slack": white_edge_slack,
        "short_axis_semantic_ok": bool(short_axis_semantic_ok),
        "short_content_height_max": float(alignment.short_content_height_max),
    }
    if detail_key is not None:
        cache.outer_alignment_details[detail_key] = copy.deepcopy(detail)
    return detail


def corrected_outer_from_alignment(alignment: dict[str, Any], count: int, policy: DetectionPolicy) -> Optional[Box]:
    alignment_policy = policy.outer.content_alignment
    if not bool(alignment.get("used", False)) or bool(alignment.get("ok", True)):
        return None
    try:
        outer = box_from_dict(alignment["outer_work_box"])
        content = box_from_dict(alignment["content_work_box"])
    except Exception:
        return None
    if not outer.valid() or not content.valid():
        return None

    pitch = float(outer.width) / float(max(1, count))
    alignment_margin_x = clamp_int(pitch * alignment_policy.margin_x_ratio, alignment_policy.margin_x_min, alignment_policy.margin_x_max)
    alignment_margin_y = clamp_int(float(outer.height) * alignment_policy.margin_y_ratio, alignment_policy.margin_y_min, alignment_policy.margin_y_max)
    long_margin_cap = clamp_int(pitch * alignment_policy.long_margin_cap_ratio, alignment_policy.long_margin_cap_min, alignment_policy.long_margin_cap_max)
    short_margin_cap = clamp_int(float(outer.height) * alignment_policy.short_margin_cap_ratio, alignment_policy.short_margin_cap_min, alignment_policy.short_margin_cap_max)
    long_margin = max(alignment_margin_x, min(long_margin_cap, int(round(pitch * alignment_policy.long_margin_ratio))))
    short_margin = max(alignment_margin_y, min(short_margin_cap, int(round(float(outer.height) * alignment_policy.short_margin_ratio))))
    left, top, right, bottom = outer.left, outer.top, outer.right, outer.bottom

    if int(alignment.get("long_slack_left", 0)) > 0:
        left = max(outer.left, content.left - long_margin)
    if int(alignment.get("long_slack_right", 0)) > 0:
        right = min(outer.right, content.right + long_margin)
    if int(alignment.get("short_slack_top", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        top = max(outer.top, content.top - short_margin)
    if int(alignment.get("short_slack_bottom", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        bottom = min(outer.bottom, content.bottom + short_margin)

    corrected = Box(left, top, right, bottom)
    if not corrected.valid():
        return None
    if corrected.width < max(80, int(round(outer.width * 0.80))) or corrected.height < max(40, int(round(outer.height * 0.80))):
        return None
    if corrected == outer:
        return None
    return corrected


def format_geometry_model_detail(gray: np.ndarray, detection: Detection, config: Config, fmt: FormatSpec, cache: AnalysisCache) -> dict[str, Any]:
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
    config: Config,
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


def retry_with_format_geometry_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FormatSpec,
    detection: Detection,
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    from .calibration import calibrate_candidate_decision
    from .content import content_evidence_detail
    from .candidate_build import build_detection_for_outer

    geometry_detail = format_geometry_model_detail(gray, detection, config, fmt, cache)
    detection.detail["format_geometry_model"] = geometry_detail
    policy = get_detection_policy(fmt.name, detection.strip_mode)
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
        return None

    gap_override = None
    wide_retry = detection.detail.get("wide_gap_retry")
    if isinstance(wide_retry, dict) and bool(wide_retry.get("used", False)):
        gap_override = float(wide_retry.get("retry_gap_max_width_ratio", policy.separator.wide_retry_max_width_ratio))

    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "format_geometry_outer",
        "format_geometry_retry",
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=gap_override,
        policy=policy,
    )
    retried = calibrate_candidate_decision(gray, retried, config, fmt, "separator", cache, policy=policy)
    retry_alignment = outer_content_alignment_detail(gray, retried, cache, policy=policy)
    retry_content = content_evidence_detail(gray, retried, cache, policy.content)
    retry_geometry = format_geometry_model_detail(gray, retried, config, fmt, cache)
    retried.detail["outer_content_alignment"] = retry_alignment
    retried.detail["content_evidence"] = retry_content
    retried.detail["format_geometry_model"] = retry_geometry
    retried.detail["outer_correction"] = {
        "used": True,
        "source_reason": "format_geometry_unexplained_outer_extra",
        "original_outer_work_box": geometry_detail.get("outer_work_box"),
        "corrected_outer_work_box": asdict(corrected_outer),
        "source_format_geometry": geometry_detail,
        "retry_format_geometry": retry_geometry,
        "retry_alignment": retry_alignment,
        "retry_content_support": retry_content.get("support"),
    }
    if gap_override is not None:
        retried.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
            "retry_gap_max_width_ratio": float(gap_override),
            "preserved_through_outer_retry": True,
        }
    return retried


def retry_with_content_aligned_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FormatSpec,
    detection: Detection,
    alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    from .calibration import calibrate_candidate_decision
    from .content import content_evidence_detail
    from .candidate_build import build_detection_for_outer

    if detection.strip_mode != "full":
        return None
    policy = get_detection_policy(fmt.name, detection.strip_mode)
    corrected_outer = corrected_outer_from_alignment(alignment, detection.count, policy)
    if corrected_outer is None:
        return None

    gap_override = None
    wide_retry = detection.detail.get("wide_gap_retry")
    if isinstance(wide_retry, dict) and bool(wide_retry.get("used", False)):
        gap_override = float(wide_retry.get("retry_gap_max_width_ratio", policy.separator.wide_retry_max_width_ratio))

    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "content_aligned_outer",
        "content_aligned_retry",
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=gap_override,
        policy=policy,
    )
    retried = calibrate_candidate_decision(gray, retried, config, fmt, "separator", cache, policy=policy)
    if gap_override is not None:
        retried.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(policy.separator.gap_search.max_width_ratio),
            "retry_gap_max_width_ratio": float(gap_override),
            "preserved_through_outer_retry": True,
        }
    retry_alignment = outer_content_alignment_detail(gray, retried, cache, policy=policy)
    retry_content = content_evidence_detail(gray, retried, cache, policy.content)
    retried.detail["outer_content_alignment"] = retry_alignment
    retried.detail["content_evidence"] = retry_content
    retried.detail["outer_correction"] = {
        "used": True,
        "source_reason": alignment.get("reason"),
        "source_edge_hard_anchors": bool(alignment.get("edge_hard_anchors", False)),
        "source_white_edge_slack": bool(alignment.get("white_edge_slack", False)),
        "original_outer_work_box": alignment.get("outer_work_box"),
        "content_work_box": alignment.get("content_work_box"),
        "corrected_outer_work_box": asdict(corrected_outer),
        "retry_alignment": retry_alignment,
        "retry_content_support": retry_content.get("support"),
    }
    return retried


def corrected_outer_for_short_axis_aspect(
    gray: np.ndarray,
    config: Config,
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
    candidate = detection.detail.get("candidate_decision", {})
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


def retry_with_short_axis_aspect_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    from .calibration import calibrate_candidate_decision
    from .content import content_evidence_detail
    from .candidate_build import build_detection_for_outer

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
    if corrected_outer is None:
        return None
    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "short_axis_aspect_outer",
        "short_axis_retry",
        cache=cache,
        allow_outer_refine=False,
        policy=policy,
    )
    retried = calibrate_candidate_decision(gray, retried, config, fmt, "separator", cache, policy=policy)
    retry_content = content_evidence_detail(gray, retried, cache, policy.content)
    retry_alignment = outer_content_alignment_detail(gray, retried, cache, policy=policy)
    retried.detail["content_evidence"] = retry_content
    retried.detail["outer_content_alignment"] = retry_alignment
    retried.detail["outer_correction"] = {
        "used": True,
        "source_reason": "short_axis_aspect_conflict",
        "original_outer_work_box": detection.detail.get("work_outer"),
        "corrected_outer_work_box": asdict(corrected_outer),
        "retry_alignment": retry_alignment,
        "retry_content_support": retry_content.get("support"),
    }
    return retried


def retry_with_outer_correction_proposals(
    gray: np.ndarray,
    config: Config,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
) -> tuple[Detection, dict[str, Any], dict[str, Any], bool]:
    retried = retry_with_short_axis_aspect_outer(gray, config, fmt, detection, content_detail, cache)
    if retried is not None:
        return (
            retried,
            dict(retried.detail.get("content_evidence", {})),
            dict(retried.detail.get("outer_content_alignment", {})),
            True,
        )

    geometry_detail = format_geometry_model_detail(gray, detection, config, fmt, cache)
    detection.detail["format_geometry_model"] = geometry_detail
    retried = retry_with_format_geometry_outer(gray, config, fmt, detection, outer_alignment, cache)
    if retried is not None:
        return (
            retried,
            dict(retried.detail.get("content_evidence", {})),
            dict(retried.detail.get("outer_content_alignment", {})),
            False,
        )

    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        retried = retry_with_content_aligned_outer(gray, config, fmt, detection, outer_alignment, cache)
        if retried is not None:
            return (
                retried,
                dict(retried.detail.get("content_evidence", {})),
                dict(retried.detail.get("outer_content_alignment", {})),
                False,
            )
        detection.detail["outer_correction"] = {
            "used": False,
            "reason": "no_valid_content_aligned_outer_retry",
        }

    return detection, content_detail, outer_alignment, False


__all__ = [
    "corrected_outer_for_short_axis_aspect",
    "format_geometry_model_detail",
    "outer_content_alignment_detail",
    "retry_with_outer_correction_proposals",
]
