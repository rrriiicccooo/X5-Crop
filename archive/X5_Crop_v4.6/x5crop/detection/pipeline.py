from __future__ import annotations

from ..constants import (
    ANALYSIS_SOURCE_135_DUAL,
    ANALYSIS_SOURCE_CONTENT,
    ANALYSIS_SOURCE_CONTENT_PRIMARY,
    ANALYSIS_SOURCE_HARD_FALLBACK,
    ANALYSIS_SOURCE_SEPARATOR,
    ANALYSIS_SOURCE_UNSUPPORTED,
    REASON_AUTO_GATE_NOT_SATISFIED,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_OUTER_CONTENT_BBOX_MISMATCH,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ..common import *
from ..evidence import *
from ..geometry import *
from ..policies import DetectionPolicy, get_detection_policy
from .candidates import (
    candidate_counts_for_format,
    raw_detection_rank,
    wide_separator_retry_allowed_for_strip,
)
from .content import (
    content_detection_for_count,
    content_evidence_detail,
    content_evidence_detail_from_cache,
)
from .gates import separator_hard_evidence_ok
from .outer import (
    outer_candidate_strategy,
    outer_proposal_candidates,
    outer_proposal_strategy_plan,
    outer_proposal_strategy_plan_for_policy,
    separator_dark_band_outer_candidates,
    separator_geometry_outer_candidates,
)
from .scoring import (
    content_support_score,
    detail_float,
    geometry_support_score,
    half_stable_grid_support_applies,
    half_wide_geometry_support_applies,
    hard_full_calibration_floor_applies,
    separator_support_score,
)
from .separator import dark_band_gaps_for_outer
from .selection import (
    is_partial_safe_auto_candidate,
    select_detection_candidate,
)


def detection_frame_cache_key(detection: Detection) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(box_cache_key(frame) for frame in detection.frames)


def detection_gap_cache_key(detection: Detection) -> tuple[tuple[int, str, float, Optional[float], Optional[float]], ...]:
    return tuple(
        (
            int(gap.index),
            str(gap.method),
            round(float(gap.center), 4),
            None if gap.start is None else round(float(gap.start), 4),
            None if gap.end is None else round(float(gap.end), 4),
        )
        for gap in detection.gaps
    )


def content_detail_cache_key(detection: Detection, source_w: int, source_h: int) -> tuple[Any, ...]:
    return (
        str(detection.film_format),
        str(detection.layout),
        int(source_w),
        int(source_h),
        box_cache_key(detection.outer),
        detection_frame_cache_key(detection),
    )


def outer_alignment_cache_key(detection: Detection, source_w: int, source_h: int) -> tuple[Any, ...]:
    return (
        str(detection.film_format),
        str(detection.layout),
        str(detection.strip_mode),
        int(detection.count),
        int(source_w),
        int(source_h),
        box_cache_key(detection.outer),
        detection_gap_cache_key(detection),
    )


def outer_content_alignment_detail(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    tuning = format_tuning(detection.film_format)
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
    white_edge_long_slack_min = clamp_int(pitch * tuning.outer_align_white_edge_long_ratio, tuning.outer_align_white_edge_long_min, tuning.outer_align_white_edge_long_max)
    long_slack_pixel_gate = clamp_int(pitch * tuning.outer_align_long_gate_ratio, tuning.outer_align_long_gate_min, tuning.outer_align_long_gate_max)
    short_slack_pixel_gate = clamp_int(float(outer.height) * tuning.outer_align_short_gate_ratio, tuning.outer_align_short_gate_min, tuning.outer_align_short_gate_max)

    edge_band = max(4, min(80, int(round(min(outer.width, outer.height) * tuning.outer_align_border_band_ratio))))
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
        and content_width_ratio >= tuning.outer_align_content_width_min
        and max_short_slack <= max(24, int(round(float(outer.height) * tuning.outer_align_edge_short_ratio)))
        and (
            (long_slack_left >= white_edge_long_slack_min and float(border_dark_fraction.get("left", 1.0)) <= tuning.outer_align_edge_dark_max)
            or (long_slack_right >= white_edge_long_slack_min and float(border_dark_fraction.get("right", 1.0)) <= tuning.outer_align_edge_dark_max)
        )
    )
    short_axis_semantic_ok = True
    if tuning.outer_align_short_requires_hard_anchors:
        short_axis_semantic_ok = short_axis_semantic_ok and edge_hard_anchors
    if tuning.outer_align_short_content_height_max < 1.0:
        short_axis_semantic_ok = short_axis_semantic_ok and content_height_ratio <= tuning.outer_align_short_content_height_max

    excess_long = long_slack_ratio > tuning.outer_align_long_excess_ratio or (max_long_slack >= long_slack_pixel_gate and long_slack_ratio > tuning.outer_align_long_gate_excess_ratio) or white_edge_slack
    excess_short = short_axis_semantic_ok and short_slack_ratio > tuning.outer_align_short_excess_ratio and max_short_slack >= short_slack_pixel_gate
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
        "outer_align_short_content_height_max": float(tuning.outer_align_short_content_height_max),
    }
    if detail_key is not None:
        cache.outer_alignment_details[detail_key] = copy.deepcopy(detail)
    return detail


def corrected_outer_from_alignment(alignment: dict[str, Any], config: Config, count: int) -> Optional[Box]:
    tuning = format_tuning(config.film_format)
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
    alignment_margin_x = clamp_int(pitch * tuning.outer_align_margin_x_ratio, tuning.outer_align_margin_x_min, tuning.outer_align_margin_x_max)
    alignment_margin_y = clamp_int(float(outer.height) * tuning.outer_align_margin_y_ratio, tuning.outer_align_margin_y_min, tuning.outer_align_margin_y_max)
    long_margin_cap = clamp_int(pitch * tuning.outer_align_long_margin_cap_ratio, tuning.outer_align_long_margin_cap_min, tuning.outer_align_long_margin_cap_max)
    short_margin_cap = clamp_int(float(outer.height) * tuning.outer_align_short_margin_cap_ratio, tuning.outer_align_short_margin_cap_min, tuning.outer_align_short_margin_cap_max)
    long_margin = max(alignment_margin_x, min(long_margin_cap, int(round(pitch * tuning.outer_align_long_margin_ratio))))
    short_margin = max(alignment_margin_y, min(short_margin_cap, int(round(float(outer.height) * tuning.outer_align_short_margin_ratio))))
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


def format_geometry_model_detail(gray: np.ndarray, detection: Detection, config: Config, fmt: FilmFormat, cache: AnalysisCache) -> dict[str, Any]:
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
    fmt: FilmFormat,
    geometry_detail: dict[str, Any],
    alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Box]:
    tuning = format_tuning(fmt.name)
    if not tuning.format_geometry_outer_retry_enabled:
        return None
    if detection.strip_mode != "full" or detection.count != fmt.default_count:
        return None
    if not bool(geometry_detail.get("used", False)):
        return None
    if not bool(geometry_detail.get("complete_measured_hard_gaps", False)):
        return None

    unexplained = float(geometry_detail.get("unexplained_extra_ratio", 0.0) or 0.0)
    if unexplained <= tuning.format_geometry_outer_retry_ratio_tolerance:
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
    if shrink_ratio < tuning.format_geometry_outer_retry_min_shrink_ratio:
        return None
    if shrink_ratio > tuning.format_geometry_outer_retry_max_shrink_ratio:
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
                float(outer.height) * tuning.format_geometry_outer_retry_content_margin_ratio,
                tuning.format_geometry_outer_retry_content_margin_min,
                tuning.format_geometry_outer_retry_content_margin_max,
            )
            if corrected.left > content.left - margin or corrected.right < content.right + margin:
                return None

    if corrected.width < max(80, int(round(outer.width * 0.80))):
        return None
    return corrected


def retry_with_format_geometry_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    detection: Detection,
    outer_alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    geometry_detail = format_geometry_model_detail(gray, detection, config, fmt, cache)
    detection.detail["format_geometry_model"] = geometry_detail
    corrected_outer = corrected_outer_from_format_geometry(detection, config, fmt, geometry_detail, outer_alignment, cache)
    if corrected_outer is None:
        return None

    gap_override = None
    wide_retry = detection.detail.get("wide_gap_retry")
    if isinstance(wide_retry, dict) and bool(wide_retry.get("used", False)):
        gap_override = float(wide_retry.get("retry_gap_max_width_ratio", format_tuning(fmt.name).wide_gap_retry_max_width_ratio))

    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "format_geometry_outer",
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=gap_override,
    )
    retried = calibrate_candidate_decision(gray, retried, config, fmt, "separator", cache)
    retry_alignment = outer_content_alignment_detail(gray, retried, cache)
    retry_content = content_evidence_detail(gray, retried, cache)
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
            "base_gap_max_width_ratio": float(format_tuning(fmt.name).gap_max_width_ratio),
            "retry_gap_max_width_ratio": float(gap_override),
            "preserved_through_outer_retry": True,
        }
    return retried


def retry_with_content_aligned_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    detection: Detection,
    alignment: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    if detection.strip_mode != "full":
        return None
    corrected_outer = corrected_outer_from_alignment(alignment, config, detection.count)
    if corrected_outer is None:
        return None

    gap_override = None
    wide_retry = detection.detail.get("wide_gap_retry")
    if isinstance(wide_retry, dict) and bool(wide_retry.get("used", False)):
        gap_override = float(wide_retry.get("retry_gap_max_width_ratio", format_tuning(fmt.name).wide_gap_retry_max_width_ratio))

    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "content_aligned_outer",
        cache=cache,
        allow_outer_refine=False,
        gap_max_width_ratio_override=gap_override,
    )
    retried = calibrate_candidate_decision(gray, retried, config, fmt, "separator", cache)
    if gap_override is not None:
        retried.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(format_tuning(fmt.name).gap_max_width_ratio),
            "retry_gap_max_width_ratio": float(gap_override),
            "preserved_through_outer_retry": True,
        }
    retry_alignment = outer_content_alignment_detail(gray, retried, cache)
    retry_content = content_evidence_detail(gray, retried, cache)
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
    fmt: FilmFormat,
    detection: Detection,
    content_detail: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Box]:
    tuning = format_tuning(fmt.name)
    if not tuning.short_axis_aspect_retry_enabled:
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
    if max_aspect_error is None or float(max_aspect_error) < tuning.short_axis_aspect_retry_min_error:
        return None

    source_h, source_w = gray.shape
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return None
    pitch = float(outer.width) / float(max(1, detection.count))
    target_aspect = max(0.01, float(tuning.short_axis_aspect_retry_target_aspect))
    target_height = pitch / target_aspect
    if target_height <= float(outer.height):
        return None

    margin = clamp_int(
        pitch * tuning.short_axis_aspect_retry_margin_ratio,
        tuning.short_axis_aspect_retry_margin_min,
        tuning.short_axis_aspect_retry_margin_max,
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
    fmt: FilmFormat,
    detection: Detection,
    content_detail: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    corrected_outer = corrected_outer_for_short_axis_aspect(gray, config, fmt, detection, content_detail, cache)
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
        cache=cache,
        allow_outer_refine=False,
    )
    retried = calibrate_candidate_decision(gray, retried, config, fmt, "separator", cache)
    retry_content = content_evidence_detail(gray, retried, cache)
    retry_alignment = outer_content_alignment_detail(gray, retried, cache)
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
    fmt: FilmFormat,
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


def score_detection(gray_work: np.ndarray, outer: Box, gaps: list[Gap], boxes: list[Box], count: int, fmt: FilmFormat, strip_mode: str) -> tuple[float, list[str], dict[str, Any]]:
    tuning = format_tuning(fmt.name)
    expected_gaps = max(0, count - 1)
    actual_detected = sum(1 for gap in gaps if gap.method in {"detected", "edge-pair"})
    wide_detected = sum(1 for gap in gaps if gap.method == "wide-separator")
    enhanced_detected = sum(1 for gap in gaps if gap.method == "enhanced-detected")
    grid_gaps = sum(1 for gap in gaps if gap.method == "grid")
    hard_detected = actual_detected + wide_detected + enhanced_detected
    detected = hard_detected + grid_gaps
    equal = sum(1 for gap in gaps if gap.method == "equal")
    reliable = sum(1 for gap in gaps if gap.method in HARD_GAP_METHODS.union({"grid"}) and gap.score >= tuning.robust_reliable_min_score)
    widths = np.array([box.width for box in boxes if box.valid()], dtype=np.float64)
    width_cv = float(widths.std() / max(1.0, widths.mean())) if widths.size else 1.0
    outer_area = float(outer.width * outer.height) / max(1.0, float(gray_work.shape[0] * gray_work.shape[1]))
    p01, p50, p99 = sampled_percentile(gray_work, [1, 50, 99])
    contrast = float(p99 - p01)

    gap_conf = 1.0 if expected_gaps == 0 else detected / float(expected_gaps)
    width_conf = max(0.0, min(1.0, 1.0 - width_cv / tuning.score_width_cv_norm))
    outer_conf = 1.0 if tuning.score_outer_min_area <= outer_area <= tuning.score_outer_max_area else tuning.score_outer_uncertain_confidence
    contrast_conf = 1.0 if contrast >= tuning.score_contrast_min else max(tuning.score_contrast_floor, contrast / tuning.score_contrast_min)
    enough_135_separator_evidence = (
        fmt.name != "135"
        or expected_gaps <= 1
        or (hard_detected >= tuning.score_gate_135_min_hard_gaps and equal <= max(tuning.score_gate_135_max_equal_min, expected_gaps // 2))
        or (actual_detected >= 1 and enhanced_detected >= 2 and equal <= max(tuning.score_gate_135_max_equal_min, expected_gaps // 2))
    )

    confidence = (
        tuning.score_gap_weight * gap_conf
        + tuning.score_width_weight * width_conf
        + tuning.score_outer_weight * outer_conf
        + tuning.score_contrast_weight * contrast_conf
    )

    full_geometry_ok = (
        strip_mode == "full"
        and count == fmt.default_count
        and len(boxes) == count
        and (
            width_cv <= tuning.score_full_width_cv
            or (fmt.name == "135" and tuning.score_gate_135_allow_full_detected_geometry and detected == expected_gaps)
        )
        and tuning.score_full_outer_min_area <= outer_area <= tuning.score_outer_max_area
        and outer_area <= tuning.score_outer_too_large
        and enough_135_separator_evidence
        and (fmt.name == "135" or (fmt.name == "half" and tuning.score_gate_half_allow_geometry) or (reliable >= expected_gaps and equal == 0))
    )
    if full_geometry_ok:
        geometry_floor = tuning.score_geometry_floor_high if fmt.name in {"135", "half"} and width_cv <= tuning.score_geometry_floor_tight_cv else tuning.score_geometry_floor_low
        confidence = max(confidence, geometry_floor)
    reasons: list[str] = []
    if expected_gaps and detected < max(1, expected_gaps // 2) and not full_geometry_ok:
        reasons.append("weak_separators")
    if equal >= max(2, expected_gaps // 2 + 1) and not full_geometry_ok:
        reasons.append("mostly_equal_split")
    if fmt.name == "135" and expected_gaps >= 3 and hard_detected < 2 and not (actual_detected >= 1 and enhanced_detected >= 2):
        reasons.append("too_few_detected_separators")
    if width_cv > tuning.score_unstable_width_cv:
        reasons.append("unstable_frame_width")
    if not (tuning.score_outer_min_area <= outer_area <= tuning.score_outer_max_area):
        reasons.append("outer_box_uncertain")
    if outer_area > tuning.score_outer_too_large:
        reasons.append("outer_box_too_large")
    if fmt.family == "120" and detected < expected_gaps:
        reasons.append("120_separator_uncertain")
    if contrast < tuning.score_contrast_min:
        reasons.append("low_contrast")
    if len(boxes) != count:
        reasons.append("frame_count_mismatch")
    if confidence < tuning.score_low_confidence_floor and not reasons:
        reasons.append("low_confidence")

    if strip_mode == "partial" and count < fmt.default_count:
        if count <= 1:
            confidence = min(confidence, tuning.score_partial_one_cap)
            reasons.append("partial_too_ambiguous")
        elif count <= 2 and fmt.default_count >= 6:
            confidence = min(confidence, tuning.score_partial_two_35mm_cap)
            reasons.append("partial_too_ambiguous")
        else:
            confidence = min(confidence, tuning.score_partial_general_cap)
        reasons.append("partial_strip_count_candidate")

    if fmt.name == "135" and expected_gaps >= 3:
        if hard_detected < 1:
            confidence = min(confidence, tuning.score_gate_135_low_hard_cap)
        elif hard_detected < 2 and enhanced_detected < 2:
            confidence = min(confidence, tuning.score_gate_135_low_hard_cap)
        elif equal >= max(2, expected_gaps // 2 + 1):
            confidence = min(confidence, tuning.score_gate_135_mostly_equal_cap)
    if outer_area > tuning.score_outer_too_large:
        confidence = min(confidence, tuning.score_outer_too_large_cap)

    detail = {
        "detected_gaps": detected,
        "actual_detected_gaps": actual_detected,
        "wide_detected_gaps": wide_detected,
        "enhanced_detected_gaps": enhanced_detected,
        "grid_gaps": grid_gaps,
        "reliable_gaps": reliable,
        "equal_gaps": equal,
        "width_cv": width_cv,
        "outer_area_ratio": outer_area,
        "image_quality": {
            "p01": float(p01),
            "p50": float(p50),
            "p99": float(p99),
            "range_1_99": contrast,
        },
        "contrast_1_99": contrast,
        "full_geometry_ok": full_geometry_ok,
    }
    return float(max(0.0, min(1.0, confidence))), sorted(set(reasons)), detail


def build_detection_for_outer(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    outer: Box,
    offset_fraction: float = 0.0,
    outer_candidate_name: str = "unknown",
    allow_separator_analysis: bool = True,
    cache: Optional[AnalysisCache] = None,
    allow_outer_refine: bool = True,
    gap_max_width_ratio_override: Optional[float] = None,
) -> Detection:
    h, w = gray.shape
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0:
        outer = Box(0, 0, ww, wh)
        crop = gray_work
    profile = cached_separator_profile(cache, gray_work, outer, fmt.name)
    if strip_mode == "partial" and count < fmt.default_count:
        pitch = outer.width / float(max(1, fmt.default_count))
        total_width = pitch * count
        origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
    else:
        pitch = outer.width / float(max(1, count))
        origin = 0.0
    gaps = [
        find_gap(profile, origin + pitch * i, pitch, i, fmt.name, gap_max_width_ratio_override)
        for i in range(1, count)
    ]
    if outer_candidate_name.startswith("separator_dark_band_"):
        dark_band_gaps = dark_band_gaps_for_outer(gray_work, outer, count, fmt)
        if len(dark_band_gaps) >= max(1, count - 1):
            gaps = dark_band_gaps
    if (
        strip_mode == "full"
        and fmt.name == "half"
        and count == fmt.default_count
        and gap_max_width_ratio_override is None
    ):
        gaps = [
            Gap(i, origin + pitch * i, float(profile[min(len(profile) - 1, max(0, int(round(origin + pitch * i))))]), "equal")
            for i in range(1, count)
        ]
    edge_refine_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    if strip_mode == "full" and count > 1:
        gaps, edge_refine_detail = refine_gaps_by_edge_pairs(crop, gaps, count, fmt.name, cache, outer)
    gaps, grid_detail = apply_robust_grid(gaps, origin, pitch, strip_mode, fmt.name, profile, gray_work, outer)
    if allow_outer_refine and strip_mode == "full" and bool(grid_detail.get("grid_used", False)):
        tuning = format_tuning(fmt.name)
        model_origin = float(grid_detail.get("grid_origin", 0.0))
        model_pitch = float(grid_detail.get("grid_pitch", pitch))
        proposed_left = int(round(outer.left + model_origin))
        proposed_right = int(round(outer.left + model_origin + model_pitch * count))
        max_shift = clamp_int(pitch * tuning.grid_outer_refine_shift_ratio, tuning.grid_outer_refine_shift_min, tuning.grid_outer_refine_shift_max)
        width_change = abs((proposed_right - proposed_left) - outer.width) / max(1.0, float(outer.width))
        if (
            proposed_right > proposed_left
            and abs(proposed_left - outer.left) <= max_shift
            and abs(proposed_right - outer.right) <= max_shift
            and width_change <= tuning.grid_outer_refine_max_width_change
            and 0 <= proposed_left < proposed_right <= ww
        ):
            outer = Box(proposed_left, outer.top, proposed_right, outer.bottom)
            crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
            profile = cached_separator_profile(cache, gray_work, outer, fmt.name)
            pitch = outer.width / float(max(1, count))
            origin = 0.0
            gaps = [
                find_gap(profile, pitch * i, pitch, i, fmt.name, gap_max_width_ratio_override)
                for i in range(1, count)
            ]
            if strip_mode == "full" and count > 1:
                gaps, edge_refine_detail = refine_gaps_by_edge_pairs(crop, gaps, count, fmt.name, cache, outer)
            gaps, grid_detail = apply_robust_grid(gaps, origin, pitch, strip_mode, fmt.name, profile, gray_work, outer)
            grid_detail["outer_refined"] = True
    separator_analysis_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    separator_analysis_allowed = allow_separator_analysis and strip_mode == "full" and fmt.name != "half"
    if separator_analysis_allowed:
        if should_run_enhanced_separator_analysis(config.analysis, gaps, count, fmt.name):
            gaps, separator_analysis_detail = merge_enhanced_separator_gaps(gray_work, outer, gaps, origin, pitch, strip_mode, fmt.name, cache)
        elif config.analysis == "auto":
            separator_analysis_detail = {"used": False, "reason": "auto_not_needed"}
    nearby_correction_detail: dict[str, Any] = {"used": False, "reason": "disabled"}
    confidence_cap_after_nearby: Optional[float] = None
    if strip_mode == "full" and format_tuning(fmt.name).nearby_active_correction:
        pre_correction_boxes = frame_boxes_from_gaps(
            outer, gaps, count, ww, wh, config.bleed_x, config.bleed_y, origin=origin, pitch=pitch
        )
        pre_correction_confidence, _pre_reasons, _pre_detail = score_detection(
            gray_work, outer, gaps, pre_correction_boxes, count, fmt, strip_mode
        )
        gaps, nearby_correction_detail = apply_nearby_separator_corrections(
            profile, gaps, origin, pitch, count, strip_mode, fmt.name
        )
        if bool(nearby_correction_detail.get("confidence_cap_required", False)):
            confidence_cap_after_nearby = float(pre_correction_confidence)
    boxes_work, frame_size_detail = fit_frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        ww,
        wh,
        config.bleed_x,
        config.bleed_y,
        fmt,
        strip_mode,
        origin=origin,
        pitch=pitch,
    )
    boxes = [map_work_box(box, config.layout, w, h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, w, h)
    confidence, reasons, detail = score_detection(gray_work, outer, gaps, boxes_work, count, fmt, strip_mode)
    detail.update(
        {
            "candidate_count": count,
            "offset_fraction": float(offset_fraction),
            "origin": float(origin),
            "pitch": float(pitch),
            "layout": config.layout,
            "outer_candidate": outer_candidate_name,
            "outer_candidate_strategy": outer_candidate_strategy(outer_candidate_name),
            "work_outer": asdict(outer),
            "grid": grid_detail,
            "grid_residual": grid_detail.get("grid_residual"),
            "grid_used": bool(grid_detail.get("grid_used", False)),
            "edge_refine": edge_refine_detail,
            "frame_size_fit": frame_size_detail,
            "separator_analysis": separator_analysis_detail,
            "nearby_separator_correction": nearby_correction_detail,
            "gap_max_width_ratio_override": gap_max_width_ratio_override,
            "partial_edge_hint": partial_edge_hint(profile, origin, pitch, count, fmt.name) if strip_mode == "partial" else {},
            "gap_centers": [gap.center for gap in gaps],
            "gap_scores": [gap.score for gap in gaps],
            "gap_methods": [gap.method for gap in gaps],
        }
    )
    if confidence_cap_after_nearby is not None:
        detail["nearby_separator_correction_confidence_cap"] = float(confidence_cap_after_nearby)
    return Detection(fmt.name, config.layout, strip_mode, count, outer_original, boxes, gaps, confidence, reasons, detail)


def select_66_full_dark_band_candidate(
    gray: np.ndarray,
    candidates: list[Detection],
    current_best: Detection,
    threshold: float,
    cache: Optional[AnalysisCache],
) -> Optional[Detection]:
    if (
        current_best.film_format != "120-66"
        or current_best.strip_mode != "full"
        or current_best.count != FORMATS["120-66"].default_count
    ):
        return None
    dark_candidates = [
        detection
        for detection in candidates
        if str(detection.detail.get("outer_candidate_strategy", "")) == "dark_band_outer"
    ]
    if not dark_candidates:
        return None

    current_content = content_evidence_detail(gray, current_best, cache)
    current_support = str(current_content.get("support", ""))
    current_reasons = set(current_best.review_reasons)
    current_needs_help = (
        current_best.confidence < threshold
        or current_support in {"aspect_conflict", "low_content"}
        or "content_aspect_conflict" in current_reasons
        or REASON_SEPARATOR_HARD_EVIDENCE_WEAK in current_reasons
    )
    if not current_needs_help:
        return None

    scored: list[tuple[tuple[int, int, float, float, float], Detection]] = []
    for detection in dark_candidates:
        content_detail = content_evidence_detail(gray, detection, cache)
        support = str(content_detail.get("support", ""))
        if support != "ok":
            continue
        hard_gaps = sum(1 for gap in detection.gaps if gap.method != "equal")
        equal_gaps = int(detection.detail.get("equal_gaps", 0) or 0)
        if hard_gaps < max(1, detection.count - 1) or equal_gaps > 0:
            continue
        width_cv = detail_float(detection.detail, "width_cv", 1.0)
        median_coverage = detail_float(content_detail, "median_coverage", 0.0)
        scored.append(
            (
                (
                    1 if detection.confidence >= threshold else 0,
                    hard_gaps,
                    median_coverage,
                    float(detection.confidence),
                    -width_cv,
                ),
                detection,
            )
        )
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]


def separator_geometry_can_compete(detection: Detection, gray: np.ndarray) -> bool:
    outer_candidate = str(detection.detail.get("outer_candidate", ""))
    frames = [original_box_to_work(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in detection.frames]
    aspects = [
        frame.width / max(1.0, float(frame.height))
        for frame in frames
        if frame.valid() and frame.height > 0
    ]
    if not aspects:
        return False
    median_aspect = float(np.median(np.array(aspects, dtype=np.float32)))
    if outer_candidate.startswith("floating_partial_"):
        return median_aspect <= 1.045
    return median_aspect >= 1.090


def detect_candidate_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    gap_max_width_ratio_override: Optional[float] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    tuning = format_tuning(fmt.name)
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        include_separator_first_mode="always",
        include_long_axis_edge_anchor_mode="always",
        policy=policy,
    )
    candidates: list[Detection] = []
    for candidate in outer_candidates:
        candidate_gap_override = gap_max_width_ratio_override
        if (
            candidate.name.startswith("separator_first_")
            and candidate_gap_override is None
            and tuning.separator_first_outer_gap_max_width_ratio > tuning.gap_max_width_ratio
        ):
            candidate_gap_override = tuning.separator_first_outer_gap_max_width_ratio
        detection = build_detection_for_outer(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            candidate.box,
            offset_fraction,
            candidate.name,
            cache=cache,
            gap_max_width_ratio_override=candidate_gap_override,
        )
        candidates.append(detection)
    regular_best = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold)) if candidates else None
    separator_geometry_mode = policy.outer.separator_geometry
    should_try_separator_geometry = (
        separator_geometry_mode == "always"
        or (
            separator_geometry_mode == "conditional"
            and (regular_best is None or separator_geometry_can_compete(regular_best, gray))
        )
    )
    if should_try_separator_geometry:
        separator_geometry_candidates = separator_geometry_outer_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            cache,
        )
        for candidate in separator_geometry_candidates:
            candidate_gap_override = gap_max_width_ratio_override
            if (
                candidate_gap_override is None
                and tuning.separator_first_outer_gap_max_width_ratio > tuning.gap_max_width_ratio
            ):
                candidate_gap_override = tuning.separator_first_outer_gap_max_width_ratio
            candidates.append(
                build_detection_for_outer(
                    gray,
                    config,
                    fmt,
                    count,
                    strip_mode,
                    candidate.box,
                    offset_fraction,
                    candidate.name,
                    cache=cache,
                    gap_max_width_ratio_override=candidate_gap_override,
                )
            )
        outer_candidates = unique_outer_candidates([*outer_candidates, *separator_geometry_candidates])
    should_try_dark_band = False
    current_best_for_dark = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold)) if candidates else None
    if policy.outer.dark_band != "off" and strip_mode == "partial" and current_best_for_dark is not None:
        has_wide_like_candidate = False
        for detection in candidates:
            candidate_wide_like = partial_safe_wide_like_gap_detail(detection, fmt)
            if (
                bool(candidate_wide_like.get("used", False))
                and int(candidate_wide_like.get("wide_like_gaps", 0) or 0)
                >= int(candidate_wide_like.get("min_wide_like_gaps", 0) or 0)
                and int(detection.detail.get("equal_gaps", 0) or 0) == 0
            ):
                has_wide_like_candidate = True
                break
        wide_like_detail = partial_safe_wide_like_gap_detail(current_best_for_dark, fmt)
        should_try_dark_band = (
            not has_wide_like_candidate
            and (
                int(current_best_for_dark.detail.get("equal_gaps", 0) or 0) > 0
                or (
                    bool(wide_like_detail.get("used", False))
                    and int(wide_like_detail.get("wide_like_gaps", 0) or 0)
                    < int(wide_like_detail.get("min_wide_like_gaps", 0) or 0)
                )
            )
        )
    elif policy.outer.dark_band != "off" and strip_mode == "full" and count == fmt.default_count:
        should_try_dark_band = True
    separator_dark_band_candidates = (
        separator_dark_band_outer_candidates(
            gray_work,
            outer_candidates,
            fmt,
            count,
            strip_mode,
            policy,
        )
        if should_try_dark_band
        else []
    )
    if separator_dark_band_candidates:
        for candidate in separator_dark_band_candidates:
            candidate_gap_override = gap_max_width_ratio_override
            if (
                candidate_gap_override is None
                and tuning.separator_first_outer_gap_max_width_ratio > tuning.gap_max_width_ratio
            ):
                candidate_gap_override = tuning.separator_first_outer_gap_max_width_ratio
            candidates.append(
                build_detection_for_outer(
                    gray,
                    config,
                    fmt,
                    count,
                    strip_mode,
                    candidate.box,
                    offset_fraction,
                    candidate.name,
                    cache=cache,
                    gap_max_width_ratio_override=candidate_gap_override,
                )
            )
        outer_candidates = unique_outer_candidates([*outer_candidates, *separator_dark_band_candidates])
    best_candidates = candidates
    if (
        policy.gates.partial_safe_extra_frames
        and policy.gates.partial_checks_leading_content
        and strip_mode == "partial"
        and len(candidates) > 1
    ):
        non_cutting_candidates: list[Detection] = []
        for detection in candidates:
            if str(detection.detail.get("outer_candidate_strategy", "")) != "content_outer":
                non_cutting_candidates.append(detection)
                continue
            leading_content = partial_safe_leading_content_detail(gray, detection, fmt, cache)
            frame_content = partial_safe_frame_content_detail(content_evidence_detail(gray, detection, cache), detection, fmt)
            if (
                (not bool(leading_content.get("used", False)) or bool(leading_content.get("ok", True)))
                and (not bool(frame_content.get("used", False)) or bool(frame_content.get("ok", True)))
            ):
                non_cutting_candidates.append(detection)
        if non_cutting_candidates:
            best_candidates = non_cutting_candidates
    best = max(best_candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold))
    full_dark_band_best = select_66_full_dark_band_candidate(gray, candidates, best, config.confidence_threshold, cache)
    if full_dark_band_best is not None:
        best = full_dark_band_best
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "strategy": outer_candidate_strategy(candidate.name), "box": asdict(candidate.box)}
            for candidate in outer_candidates
        ]
    return best


def detect_fallback_outer_proposal_candidate_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Optional[Detection]:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    tuning = format_tuning(fmt.name)
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        include_separator_first_mode="fallback",
        include_long_axis_edge_anchor_mode="fallback",
        include_separator_geometry_mode="fallback",
        fallback_only=True,
        policy=policy,
    )
    if not outer_candidates:
        return None

    candidates: list[Detection] = []
    for candidate in outer_candidates:
        candidate_gap_override = None
        if tuning.separator_first_outer_gap_max_width_ratio > tuning.gap_max_width_ratio:
            candidate_gap_override = tuning.separator_first_outer_gap_max_width_ratio
        candidates.append(
            build_detection_for_outer(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                candidate.box,
                offset_fraction,
                candidate.name,
                cache=cache,
                gap_max_width_ratio_override=candidate_gap_override,
            )
        )
    best = max(candidates, key=lambda d: raw_detection_rank(d, config.confidence_threshold))
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "strategy": outer_candidate_strategy(candidate.name), "box": asdict(candidate.box)}
            for candidate in outer_candidates
        ]
    return best


def translate_box(box: Box, dx: int, dy: int) -> Box:
    return Box(box.left + dx, box.top + dy, box.right + dx, box.bottom + dy)


def split_dual_135_lanes(gray_work: np.ndarray) -> list[Box]:
    h, w = gray_work.shape
    content = bbox_from_mask(gray_work < 246, min_row_fraction=0.010, min_col_fraction=0.010)
    if content is None or not content.valid():
        content = Box(0, 0, w, h)
    split_y = int(round((content.top + content.bottom) / 2.0))
    guard = max(2, min(80, int(round(content.height * 0.006))))
    lanes = [
        Box(content.left, content.top, content.right, max(content.top + 1, split_y - guard)).clamp(w, h),
        Box(content.left, min(content.bottom - 1, split_y + guard), content.right, content.bottom).clamp(w, h),
    ]
    if any(not lane.valid() or lane.height < max(20, h * 0.10) for lane in lanes):
        split_y = h // 2
        lanes = [Box(0, 0, w, split_y), Box(0, split_y, w, h)]
    return lanes


def detect_dual_135_lane(
    gray: np.ndarray,
    config: Config,
    lane: Box,
    lane_index: int,
    cache: AnalysisCache,
) -> Optional[Detection]:
    lane_crop = cache.gray_work[lane.top:lane.bottom, lane.left:lane.right]
    if lane_crop.size == 0:
        return None
    fmt_135 = FORMATS["135"]
    lane_config = replace(config, film_format="135", count=fmt_135.default_count, count_override=fmt_135.default_count)
    candidates: list[Detection] = []
    for outer_candidate in detect_outer_candidates(lane_crop):
        lane_outer = translate_box(outer_candidate.box, lane.left, lane.top)
        raw = build_detection_for_outer(
            gray,
            lane_config,
            fmt_135,
            fmt_135.default_count,
            "full",
            lane_outer,
            0.0,
            f"135_dual_lane_{lane_index}_{outer_candidate.name}",
            cache=cache,
        )
        calibrated = calibrate_candidate_decision(gray, raw, lane_config, fmt_135, "separator", cache)
        calibrated.detail["dual_lane_index"] = lane_index
        calibrated.detail["dual_lane_work_box"] = asdict(lane)
        candidates.append(calibrated)
    if not candidates:
        return None
    best = max(candidates, key=lambda d: calibrated_candidate_rank(d, config.confidence_threshold))
    content_detail = content_evidence_detail(gray, best, cache)
    outer_alignment = outer_content_alignment_detail(gray, best, cache)
    best.detail["content_evidence"] = content_detail
    best.detail["outer_content_alignment"] = outer_alignment
    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            best.confidence = min(best.confidence, 0.82)
            best.review_reasons.append(REASON_CONTENT_ASPECT_CONFLICT)
        elif support in {"low_content", "weak"} and best.confidence >= config.confidence_threshold:
            best.confidence = min(best.confidence, 0.84)
            best.review_reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        best.confidence = min(best.confidence, 0.84)
        best.review_reasons.append(REASON_OUTER_CONTENT_BBOX_MISMATCH)
    best.review_reasons = sorted(set(best.review_reasons))
    return best


def unsupported_dual_135_partial_detection(gray: np.ndarray, config: Config) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = Box(0, 0, ww, wh)
    source_h, source_w = gray.shape
    return Detection(
        "135-dual",
        config.layout,
        config.strip_mode,
        12,
        map_work_box(outer, config.layout, source_w, source_h),
        [],
        [],
        0.0,
        ["135_dual_partial_not_supported", "needs_manual_review"],
        {
            "analysis_source": ANALYSIS_SOURCE_UNSUPPORTED,
            "candidate_count": 0,
            "layout": config.layout,
            "work_outer": asdict(outer),
            "candidate_competition": {
                "candidate_count": 0,
                "formats": ["135-dual"],
                "selected_candidate": {
                    "format": "135-dual",
                    "count": 12,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "review_reasons": ["135_dual_partial_not_supported", "needs_manual_review"],
                },
                "selection_override": "unsupported_135_dual_partial",
                "top_candidates": [],
            },
        },
    )


def choose_detection_135_dual(gray: np.ndarray, config: Config, cache: AnalysisCache) -> Detection:
    if config.strip_mode != "full":
        return unsupported_dual_135_partial_detection(gray, config)

    gray_work = cache.gray_work
    source_h, source_w = gray.shape
    lanes = split_dual_135_lanes(gray_work)
    lane_detections = [
        detect_dual_135_lane(gray, config, lane, index, cache)
        for index, lane in enumerate(lanes, start=1)
    ]
    if any(detection is None for detection in lane_detections):
        detection = hard_fallback_detection(gray, config, FORMATS["135-dual"])
        detection.review_reasons.append("135_dual_lane_detection_failed")
        detection.review_reasons = sorted(set(detection.review_reasons))
        return detection

    confirmed_lanes = [detection for detection in lane_detections if detection is not None]
    lane_work_outers = [
        box_from_dict(detection.detail["work_outer"])
        for detection in confirmed_lanes
        if isinstance(detection.detail.get("work_outer"), dict)
    ]
    if len(lane_work_outers) != 2:
        detection = hard_fallback_detection(gray, config, FORMATS["135-dual"])
        detection.review_reasons.append("135_dual_outer_detection_failed")
        detection.review_reasons = sorted(set(detection.review_reasons))
        return detection

    combined_work_outer = Box(
        min(box.left for box in lane_work_outers),
        min(box.top for box in lane_work_outers),
        max(box.right for box in lane_work_outers),
        max(box.bottom for box in lane_work_outers),
    )
    frames = [box for detection in confirmed_lanes for box in detection.frames]
    gaps: list[Gap] = []
    for lane_number, detection in enumerate(confirmed_lanes, start=1):
        lane_work_outer = box_from_dict(detection.detail["work_outer"])
        for gap in detection.gaps:
            gaps.append(
                Gap(
                    index=(lane_number - 1) * 6 + int(gap.index),
                    center=float(gap.center),
                    score=float(gap.score),
                    method=gap.method,
                    start=gap.start,
                    end=gap.end,
                    lane_box=asdict(lane_work_outer),
                )
            )

    lane_confidences = [float(detection.confidence) for detection in confirmed_lanes]
    confidence = min(lane_confidences)
    review_reasons = sorted(set(reason for detection in confirmed_lanes for reason in detection.review_reasons))
    if any(conf < config.confidence_threshold for conf in lane_confidences):
        confidence = min(confidence, 0.84)
        review_reasons.append("135_dual_lane_below_threshold")
    if len(frames) != 12:
        confidence = min(confidence, 0.82)
        review_reasons.append("frame_count_mismatch")

    lane_summaries = [
        {
            "lane": index,
            "lane_format": "135",
            "lane_count": 6,
            "total_format": "135-dual",
            "total_count": 12,
            "confidence": float(detection.confidence),
            "review_reasons": list(detection.review_reasons),
            "work_outer": detection.detail.get("work_outer"),
            "content_evidence": detection.detail.get("content_evidence", {}),
            "outer_content_alignment": detection.detail.get("outer_content_alignment", {}),
            "candidate_decision": detection.detail.get("candidate_decision", {}),
        }
        for index, detection in enumerate(confirmed_lanes, start=1)
    ]
    detail = {
        "analysis_source": ANALYSIS_SOURCE_135_DUAL,
        "layout": config.layout,
        "candidate_count": 12,
        "work_outer": asdict(combined_work_outer),
        "dual_lane_work_boxes": [asdict(lane) for lane in lanes],
        "dual_lane_detections": lane_summaries,
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
        "candidate_competition": {
            "candidate_count": 2,
            "formats": ["135-dual"],
            "selected_candidate": {
                "format": "135-dual",
                "count": 12,
                "strip_mode": "full",
                "confidence": float(confidence),
                "review_reasons": sorted(set(review_reasons)),
            },
            "selection_override": None,
            "top_candidates": lane_summaries,
        },
    }
    outer_original = map_work_box(combined_work_outer, config.layout, source_w, source_h)
    return Detection(
        "135-dual",
        config.layout,
        "full",
        12,
        outer_original,
        frames,
        gaps,
        float(max(0.0, min(1.0, confidence))),
        sorted(set(review_reasons)),
        detail,
    )


def partial_candidates(fmt: FilmFormat) -> tuple[int, ...]:
    default = fmt.default_count
    candidates: set[int] = {default, max(1, default - 1), max(1, default - 2), 1}
    if default >= 3:
        candidates.add(2)
    if default >= 6:
        candidates.add(max(1, default // 2))
    return tuple(sorted((c for c in candidates if c in fmt.allowed_counts), reverse=True))


def partial_offsets(fmt: FilmFormat, count: int) -> tuple[float, ...]:
    if count >= fmt.default_count:
        return (0.0,)
    return format_tuning(fmt.name).partial_offsets


def partial_edge_hint(profile: np.ndarray, origin: float, pitch: float, count: int, format_name: str = "135") -> dict[str, Any]:
    if profile.size == 0 or count <= 0:
        return {}
    tuning = format_tuning(format_name)
    span_start = int(max(0, min(len(profile) - 1, round(origin))))
    span_end = int(max(0, min(len(profile), round(origin + pitch * count))))
    edge_window = clamp_int(pitch * tuning.partial_edge_hint_window_ratio, tuning.partial_edge_hint_window_min, tuning.partial_edge_hint_window_max)
    left_window = profile[span_start:min(len(profile), span_start + edge_window)]
    right_window = profile[max(0, span_end - edge_window):span_end]
    return {
        "left_edge_score": float(left_window.max()) if left_window.size else 0.0,
        "right_edge_score": float(right_window.max()) if right_window.size else 0.0,
        "span_start": span_start,
        "span_end": span_end,
    }


def partial_safe_wide_like_gap_detail(detection: Detection, fmt: FilmFormat) -> dict[str, Any]:
    tuning = format_tuning(fmt.name)
    min_required = int(tuning.partial_safe_extra_frames_min_wide_like_gaps)
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

    min_width = max(1.0, short_axis * float(tuning.partial_safe_extra_frames_wide_like_min_width_ratio))
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
    fmt: FilmFormat,
    cache: Optional[AnalysisCache],
) -> dict[str, Any]:
    tuning = format_tuning(fmt.name)
    if not tuning.partial_safe_extra_frames_leading_content_check or detection.strip_mode != "partial":
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
        pitch * float(tuning.partial_safe_extra_frames_leading_content_band_ratio),
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
        mean <= float(tuning.partial_safe_extra_frames_leading_content_max_mean)
        and coverage <= float(tuning.partial_safe_extra_frames_leading_content_max_coverage)
    )
    return {
        "used": True,
        "ok": bool(ok),
        "reason": "ok" if ok else "leading_edge_content_too_strong",
        "mean": mean,
        "coverage": coverage,
        "band_px": int(band_right - left),
        "max_mean": float(tuning.partial_safe_extra_frames_leading_content_max_mean),
        "max_coverage": float(tuning.partial_safe_extra_frames_leading_content_max_coverage),
    }


def partial_safe_frame_content_detail(
    content_detail: dict[str, Any],
    detection: Detection,
    fmt: FilmFormat,
) -> dict[str, Any]:
    tuning = format_tuning(fmt.name)
    if not tuning.partial_safe_extra_frames_frame_content_check or detection.strip_mode != "partial":
        return {"used": False, "reason": "disabled"}
    frame_scores = content_detail.get("frame_scores", [])
    if not isinstance(frame_scores, list) or not frame_scores:
        return {"used": True, "ok": False, "reason": "missing_frame_scores", "frame_count": 0}

    min_mean = float(tuning.partial_safe_extra_frames_min_frame_mean)
    min_coverage = float(tuning.partial_safe_extra_frames_min_frame_coverage)
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
        aspect_error: Optional[float]
        try:
            aspect_error = None if aspect_error_value is None else float(aspect_error_value)
        except (TypeError, ValueError):
            aspect_error = None
        if mean < min_mean and coverage < min_coverage:
            weak_frames.append(index)
        if aspect_error is not None and aspect_error > tuning.content_evidence_aspect_ok_max:
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
        "frame_scores": normalized_scores,
    }


def partial_extra_holder_frames_gate_detail(
    gray: np.ndarray,
    detection: Detection,
    hard_detail: dict[str, Any],
    content_detail: dict[str, Any],
    fmt: FilmFormat,
    source: str,
    joint_score: float,
    content_score: float,
    geometry_score: float,
    cache: Optional[AnalysisCache] = None,
) -> dict[str, Any]:
    tuning = format_tuning(fmt.name)
    expected = max(0, int(hard_detail.get("expected_gaps", 0) or 0))
    hard = int(hard_detail.get("hard_gaps", 0) or 0)
    equal = int(hard_detail.get("equal_gaps", 0) or 0)
    grid = int(hard_detail.get("grid_gaps", 0) or 0)
    width_cv_value = detection.detail.get("width_cv", None)
    width_cv = 1.0 if width_cv_value is None else float(width_cv_value)
    outer_area = float(detection.detail.get("outer_area_ratio", 1.0) or 1.0)
    min_count = (
        tuning.partial_safe_extra_frames_min_count_35mm
        if fmt.default_count >= 6
        else tuning.partial_safe_extra_frames_min_count_small
    )
    hard_ratio = 1.0 if expected <= 0 else hard / float(max(1, expected))
    wide_like_detail = partial_safe_wide_like_gap_detail(detection, fmt)
    leading_content = partial_safe_leading_content_detail(gray, detection, fmt, cache)
    frame_content = partial_safe_frame_content_detail(content_detail, detection, fmt)
    disqualifiers: list[str] = []
    if not tuning.partial_safe_extra_frames_enabled:
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
    if hard < tuning.partial_safe_extra_frames_min_hard_gaps:
        disqualifiers.append("too_few_hard_gaps")
    if hard_ratio < tuning.partial_safe_extra_frames_min_hard_ratio:
        disqualifiers.append("hard_gap_ratio_low")
    if (
        bool(wide_like_detail.get("used", False))
        and int(wide_like_detail.get("wide_like_gaps", 0) or 0)
        < int(wide_like_detail.get("min_wide_like_gaps", 0) or 0)
    ):
        disqualifiers.append("too_few_wide_like_gaps")
    if equal > tuning.partial_safe_extra_frames_max_equal_gaps:
        disqualifiers.append("equal_gap_used")
    if width_cv > tuning.partial_safe_extra_frames_max_width_cv:
        disqualifiers.append("width_cv_unstable")
    if joint_score < tuning.partial_safe_extra_frames_min_joint_score:
        disqualifiers.append("joint_score_low")
    if content_score < tuning.partial_safe_extra_frames_min_content_score:
        disqualifiers.append("content_score_low")
    if geometry_score < tuning.partial_safe_extra_frames_min_geometry_score:
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
        "format_policy": tuning.name,
        "wide_like_separator": wide_like_detail,
        "leading_content": leading_content,
        "frame_content": frame_content,
    }


def calibrate_candidate_decision(
    gray: np.ndarray,
    detection: Detection,
    config: Config,
    fmt: FilmFormat,
    source: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    candidate = replace(
        detection,
        review_reasons=list(detection.review_reasons),
        detail=dict(detection.detail),
    )
    content_detail = content_evidence_detail(gray, candidate, cache)
    hard_ok, hard_detail = separator_hard_evidence_ok(candidate, config.confidence_threshold, policy)
    policy = policy or get_detection_policy(fmt.name, candidate.strip_mode)
    tuning = policy.tuning
    floor_applies = hard_full_calibration_floor_applies(candidate, hard_detail, fmt, source)
    if floor_applies:
        gate_candidate = replace(
            candidate,
            confidence=max(float(candidate.confidence), tuning.calibrate_hard_full_confidence_floor),
        )
        hard_ok, hard_detail = separator_hard_evidence_ok(gate_candidate, config.confidence_threshold, policy)
        hard_detail = dict(hard_detail)
        hard_detail["calibrate_hard_full_confidence_floor_applied"] = True
        hard_detail["calibrate_hard_full_confidence_floor"] = float(tuning.calibrate_hard_full_confidence_floor)
    content_score = content_support_score(content_detail, fmt.name)
    geometry_score = geometry_support_score(candidate, content_detail)
    separator_score = separator_support_score(candidate, hard_detail) if source == "separator" else 0.0
    source_bias = tuning.calibrate_separator_source_bias if source == "separator" else 0.0
    joint_score = tuning.calibrate_geometry_weight * geometry_score + tuning.calibrate_content_weight * content_score + tuning.calibrate_separator_weight * separator_score + source_bias
    joint_score = max(0.0, min(1.0, joint_score))
    support = str(content_detail.get("support", ""))
    reasons = list(candidate.review_reasons)
    if floor_applies:
        reasons = [reason for reason in reasons if reason != "low_confidence"]
    half_wide_support = (not hard_ok) and half_wide_geometry_support_applies(
        candidate,
        hard_detail,
        fmt,
        source,
        support,
        joint_score,
        config.confidence_threshold,
    )
    half_stable_grid_support = (
        False
        if half_wide_support
        else half_stable_grid_support_applies(
            candidate,
            hard_detail,
            fmt,
            source,
            support,
            joint_score,
        )
    )
    if half_wide_support or half_stable_grid_support:
        hard_ok = True
        hard_detail = dict(hard_detail)
        hard_detail["ok"] = True
        if half_wide_support:
            hard_detail["reason"] = "half_wide_geometry_support"
            hard_detail["half_wide_geometry_support"] = True
        else:
            hard_detail["reason"] = "half_stable_grid_support"
            hard_detail["half_stable_grid_support"] = True
        reasons = [reason for reason in reasons if reason != "outer_box_too_large"]

    outer_candidate_name = str(candidate.detail.get("outer_candidate", ""))
    if source == "separator" and outer_candidate_name.startswith("long_axis_edge_anchor_"):
        hard_count = int(hard_detail.get("hard_gaps", 0) or 0)
        if hard_count <= 0:
            hard_ok = False
            hard_detail = dict(hard_detail)
            hard_detail["ok"] = False
            hard_detail["reason"] = "long_axis_edge_anchor_needs_hard_separator"
            hard_detail["long_axis_edge_anchor_needs_hard_separator"] = True
            reasons.append("long_axis_edge_anchor_separator_weak")

    if source == "separator" and not hard_ok:
        reasons.append(REASON_SEPARATOR_HARD_EVIDENCE_WEAK)
    if support == "aspect_conflict":
        reasons.append(REASON_CONTENT_ASPECT_CONFLICT)
    elif support == "low_content":
        reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    elif support == "weak":
        reasons.append(REASON_CONTENT_EVIDENCE_WEAK)
    if source == "content":
        reasons.append("content_only_not_enough_for_auto")

    confidence = max(float(candidate.confidence), joint_score)
    if floor_applies:
        confidence = max(confidence, tuning.calibrate_hard_full_confidence_floor)
    partial_safe_extra_frames = partial_extra_holder_frames_gate_detail(
        gray,
        candidate,
        hard_detail,
        content_detail,
        fmt,
        source,
        joint_score,
        content_score,
        geometry_score,
        cache,
    )
    partial_safe_extra_frames_ok = bool(partial_safe_extra_frames.get("ok", False))
    partial_safe_disqualifiers = set(partial_safe_extra_frames.get("disqualifiers", []))
    partial_safe_blocks_auto = (
        policy.gates.partial_safe_extra_frames
        and policy.gates.partial_checks_leading_content
        and policy.gates.partial_checks_frame_content
        and candidate.strip_mode == "partial"
        and source == "separator"
        and bool(partial_safe_extra_frames.get("used", False))
        and bool(
            partial_safe_disqualifiers.intersection(
                {"too_few_wide_like_gaps", "partial_outer_leading_content", "partial_frame_content_unstable"}
            )
        )
    )
    if partial_safe_blocks_auto:
        hard_ok = False
        hard_detail = dict(hard_detail)
        hard_detail["ok"] = False
        hard_detail["reason"] = "partial_safe_extra_frames_blocked"
        hard_detail["partial_safe_extra_frames_blocked"] = sorted(partial_safe_disqualifiers)
        reasons.extend(sorted(partial_safe_disqualifiers))
    if partial_safe_extra_frames_ok:
        hard_detail = dict(hard_detail)
        hard_detail["ok"] = True
        hard_detail["reason"] = "partial_safe_extra_frames_support"
        hard_detail["partial_safe_extra_frames_support"] = True
        reasons = [
            reason
            for reason in reasons
            if reason
            not in {
                "partial_strip_count_candidate",
                "partial_too_ambiguous",
                REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
                "weak_separators",
                "outer_box_too_large",
                "outer_box_uncertain",
            }
        ]
    hard_reasons = HARD_REVIEW_REASONS.intersection(reasons)
    auto_gate = False
    if source == "separator":
        auto_gate = (hard_ok or partial_safe_extra_frames_ok) and support == "ok" and not hard_reasons
    elif source == "content":
        auto_gate = False

    if not auto_gate:
        cap = tuning.calibrate_partial_no_auto_cap if candidate.strip_mode == "partial" else tuning.calibrate_full_no_auto_cap
        confidence = min(confidence, cap)
        reasons.append(REASON_AUTO_GATE_NOT_SATISFIED)
    else:
        confidence = max(confidence, config.confidence_threshold + min(0.10, joint_score * 0.08))
    wide_count = int(hard_detail.get("wide_detected_gaps", 0) or 0)
    if source == "separator" and wide_count > 0:
        confidence = min(confidence, tuning.wide_gap_confidence_cap)
    nearby_cap = candidate.detail.get("nearby_separator_correction_confidence_cap")
    if nearby_cap is not None:
        try:
            confidence = min(confidence, float(nearby_cap))
        except (TypeError, ValueError):
            pass

    candidate.confidence = float(max(0.0, min(1.0, confidence)))
    candidate.review_reasons = sorted(set(reasons))
    candidate.detail["analysis_source"] = (
        ANALYSIS_SOURCE_SEPARATOR if source == "separator" else ANALYSIS_SOURCE_CONTENT
    )
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["candidate_decision"] = {
        "source": source,
        "joint_score": float(joint_score),
        "auto_gate": bool(auto_gate),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_support": support,
        "separator_hard_evidence": hard_detail,
        "partial_extra_holder_frames": partial_safe_extra_frames,
        "partial_safe_extra_frames": partial_safe_extra_frames,
    }
    return candidate


def hard_fallback_detection(gray: np.ndarray, config: Config, fmt: FilmFormat) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    count = max(1, int(config.count))
    outer = Box(0, 0, ww, wh)
    if count > 1:
        pitch = ww / float(count)
        gaps = [Gap(i, pitch * i, 0.0, "equal") for i in range(1, count)]
    else:
        pitch = float(ww)
        gaps = []
    boxes_work = frame_boxes_from_gaps(outer, gaps, count, ww, wh, config.bleed_x, config.bleed_y, origin=0.0, pitch=pitch)
    source_h, source_w = gray.shape
    boxes = [map_work_box(box, config.layout, source_w, source_h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, source_w, source_h)
    return Detection(
        fmt.name,
        config.layout,
        config.strip_mode,
        count,
        outer_original,
        boxes,
        gaps,
        0.0,
        ["hard_fallback_no_candidates", "needs_manual_review"],
        {
            "analysis_source": ANALYSIS_SOURCE_HARD_FALLBACK,
            "fallback_kind": "review_only_equal_split",
            "changes_pass_review": False,
            "layout": config.layout,
            "film_format": fmt.name,
            "strip_mode": config.strip_mode,
            "count": int(count),
            "work_outer": asdict(outer),
            "pitch": float(pitch),
        },
    )


def calibrated_candidates_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    offset: float,
    cache: AnalysisCache,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[list[Detection], bool]:
    tuning = format_tuning(fmt.name)
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    candidates: list[Detection] = []
    stop_after_this_count = False
    wide_retry_allowed = bool(policy.separator.wide_retry)
    wide_retry_has_room = tuning.wide_gap_retry_max_width_ratio > tuning.gap_max_width_ratio
    half_full_equal_first = (
        fmt.name == "half"
        and strip_mode == "full"
        and count == fmt.default_count
        and wide_retry_allowed
        and wide_retry_has_room
    )
    separator = detect_candidate_for_count(gray, config, fmt, count, strip_mode, offset, cache, policy=policy)
    separator_candidate = calibrate_candidate_decision(gray, separator, config, fmt, "separator", cache, policy=policy)
    candidates.append(separator_candidate)
    separator_gate_candidate = separator_candidate
    separator_auto_gate = bool(
        separator_candidate.detail.get("candidate_decision", {}).get("auto_gate", False)
    )
    if (
        not separator_auto_gate
        and wide_retry_allowed
        and wide_retry_has_room
    ):
        wide_separator = detect_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            gap_max_width_ratio_override=tuning.wide_gap_retry_max_width_ratio,
            policy=policy,
        )
        wide_candidate = calibrate_candidate_decision(gray, wide_separator, config, fmt, "separator", cache, policy=policy)
        wide_candidate.detail["wide_gap_retry"] = {
            "used": True,
            "base_gap_max_width_ratio": float(tuning.gap_max_width_ratio),
            "retry_gap_max_width_ratio": float(tuning.wide_gap_retry_max_width_ratio),
        }
        if half_full_equal_first:
            wide_candidate.detail["wide_gap_retry"]["half_full_equal_first"] = True
        candidates.append(wide_candidate)
        if bool(wide_candidate.detail.get("candidate_decision", {}).get("auto_gate", False)):
            separator_auto_gate = True
            separator_gate_candidate = wide_candidate
    if (
        not separator_auto_gate
        and (
            separator_first_outer_mode_for_strip(tuning, strip_mode) == "fallback"
            or long_axis_edge_anchor_outer_mode_for_strip(tuning, strip_mode) == "fallback"
            or separator_geometry_outer_mode_for_strip(tuning, strip_mode) == "fallback"
        )
    ):
        fallback_proposal = detect_fallback_outer_proposal_candidate_for_count(
            gray,
            config,
            fmt,
            count,
            strip_mode,
            offset,
            cache,
            policy=policy,
        )
        if fallback_proposal is not None:
            fallback_candidate = calibrate_candidate_decision(gray, fallback_proposal, config, fmt, "separator", cache, policy=policy)
            fallback_candidate.detail["outer_proposal_fallback_retry"] = {
                "used": True,
                "separator_first_mode": separator_first_outer_mode_for_strip(tuning, strip_mode),
                "long_axis_edge_anchor_mode": long_axis_edge_anchor_outer_mode_for_strip(tuning, strip_mode),
                "separator_geometry_mode": separator_geometry_outer_mode_for_strip(tuning, strip_mode),
            }
            candidates.append(fallback_candidate)
            fallback_auto_gate = bool(
                fallback_candidate.detail.get("candidate_decision", {}).get("auto_gate", False)
            )
            if fallback_auto_gate:
                separator_auto_gate = True
                separator_gate_candidate = fallback_candidate
    partial_safe_auto = is_partial_safe_auto_candidate(separator_gate_candidate, config.confidence_threshold)
    if partial_safe_auto:
        stop_after_this_count = True
    if strip_mode == "full" and separator_auto_gate and separator_gate_candidate.confidence >= config.confidence_threshold:
        separator_gate_candidate.detail["content_candidate_skipped"] = "separator_auto_gate_passed"
        return candidates, stop_after_this_count
    if strip_mode == "partial" and partial_safe_auto:
        separator_gate_candidate.detail["content_candidate_skipped"] = "partial_safe_separator_auto_gate_passed"
        return candidates, stop_after_this_count
    content = content_detection_for_count(gray, config, fmt, count, strip_mode, offset, cache)
    if content is not None:
        candidates.append(calibrate_candidate_decision(gray, content, config, fmt, "content", cache, policy=policy))
    return candidates, stop_after_this_count


def choose_detection(gray: np.ndarray, config: Config, fmt: FilmFormat, cache: Optional[AnalysisCache] = None) -> Detection:
    candidates: list[Detection] = []
    cache = cache if cache is not None and cache.layout == config.layout else make_analysis_cache(gray, config.layout)
    policy = get_detection_policy(fmt.name, config.strip_mode)
    if fmt.name == "135-dual":
        detection = choose_detection_135_dual(gray, config, cache)
        detection.detail["policy"] = policy.report_detail()
        return detection
    count_specs = candidate_counts_for_format(config, fmt, policy)
    for count, strip_mode, offsets in count_specs:
        if count not in fmt.allowed_counts:
            continue
        stop_after_this_count = False
        for offset in offsets:
            count_candidates, should_stop = calibrated_candidates_for_count(
                gray,
                config,
                fmt,
                count,
                strip_mode,
                offset,
                cache,
                policy,
            )
            candidates.extend(count_candidates)
            stop_after_this_count = stop_after_this_count or should_stop
        if strip_mode == "partial" and stop_after_this_count and config.count_override is None:
            break

    if not candidates:
        detection = hard_fallback_detection(gray, config, fmt)
        detection.detail["policy"] = policy.report_detail()
        return detection

    detection = select_detection_candidate(candidates, fmt, config.confidence_threshold, policy)
    detection.detail["policy"] = policy.report_detail()
    return detection





def detect_image(*args, **kwargs) -> Detection:
    """Run the current full detection pipeline.

    This is the stable package-level detection entry point used by V4 callers.
    """

    return choose_detection(*args, **kwargs)
