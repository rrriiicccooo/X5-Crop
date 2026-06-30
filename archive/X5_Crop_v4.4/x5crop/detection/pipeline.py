from __future__ import annotations

import itertools

from ..common import *
from ..evidence import *
from ..geometry import *

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


def separator_first_cache_key(
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )


def long_axis_edge_anchor_cache_key(
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
) -> tuple[Any, ...]:
    return (
        str(fmt.name),
        int(count),
        str(strip_mode),
        tuple((candidate.name, box_cache_key(candidate.box)) for candidate in base_candidates),
    )


def expected_content_aspect(format_name: str, layout: str) -> Optional[float]:
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(format_name)
    if aspect is None:
        return None
    if layout == "vertical":
        return 1.0 / aspect
    return aspect


def content_evidence_detail(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    if cache is not None and cache.layout == detection.layout:
        return content_evidence_detail_from_cache(gray, detection, cache)
    tuning = format_tuning(detection.film_format)

    outer = detection.outer.clamp(gray.shape[1], gray.shape[0])
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    source_crop = gray[outer.top:outer.bottom, outer.left:outer.right]
    if source_crop.size == 0:
        return {"used": False, "reason": "empty_outer"}

    evidence = make_content_evidence_gray(source_crop).astype(np.float32) / 255.0
    outer_p70 = float(sampled_percentile(evidence, [tuning.content_evidence_percentile])[0])
    threshold = max(
        tuning.content_evidence_threshold_min,
        min(tuning.content_evidence_threshold_max, outer_p70 * tuning.content_evidence_threshold_multiplier),
    )
    frame_scores: list[dict[str, Any]] = []
    means: list[float] = []
    coverages: list[float] = []
    aspect_errors: list[float] = []
    expected_aspect = expected_content_aspect(detection.film_format, detection.layout)

    for index, frame in enumerate(detection.frames, start=1):
        absolute_box = frame.clamp(gray.shape[1], gray.shape[0])
        box = Box(
            max(0, absolute_box.left - outer.left),
            max(0, absolute_box.top - outer.top),
            min(outer.width, absolute_box.right - outer.left),
            min(outer.height, absolute_box.bottom - outer.top),
        )
        if not box.valid():
            continue
        crop = evidence[box.top:box.bottom, box.left:box.right]
        if crop.size == 0:
            continue
        mean = float(crop.mean())
        coverage = float((crop >= threshold).mean())
        means.append(mean)
        coverages.append(coverage)
        actual_aspect = float(absolute_box.width) / max(1.0, float(absolute_box.height))
        aspect_error: Optional[float] = None
        if expected_aspect is not None and expected_aspect > 0:
            aspect_error = abs(actual_aspect - expected_aspect) / expected_aspect
            aspect_errors.append(float(aspect_error))
        frame_scores.append(
            {
                "index": index,
                "mean": mean,
                "coverage": coverage,
                "actual_aspect": actual_aspect,
                "expected_aspect": expected_aspect,
                "aspect_error": aspect_error,
            }
        )

    if not frame_scores:
        return {"used": False, "reason": "no_valid_frames"}

    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    min_mean = float(min(means)) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else None
    aspect_ok = max_aspect_error is None or max_aspect_error <= tuning.content_evidence_aspect_ok_max
    content_present = median_mean >= tuning.content_evidence_present_mean_min or median_coverage >= tuning.content_evidence_present_coverage_min
    support = "ok" if content_present and aspect_ok else "weak"
    if not aspect_ok:
        support = "aspect_conflict"
    elif not content_present:
        support = "low_content"

    return {
        "used": True,
        "support": support,
        "composite": "gradient+neighbor_texture+local_contrast+tonal_presence",
        "threshold": threshold,
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": expected_aspect,
        "max_aspect_error": max_aspect_error,
        "frame_scores": frame_scores,
    }


def content_evidence_detail_from_cache(gray: np.ndarray, detection: Detection, cache: AnalysisCache) -> dict[str, Any]:
    tuning = format_tuning(detection.film_format)
    source_h, source_w = gray.shape
    detail_key = content_detail_cache_key(detection, source_w, source_h)
    cached = cache.content_evidence_details.get(detail_key)
    if cached is not None:
        return copy.deepcopy(cached)
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    evidence = cache.content_evidence_float_work[outer.top:outer.bottom, outer.left:outer.right]
    if evidence.size == 0:
        return {"used": False, "reason": "empty_outer"}

    outer_p70 = float(sampled_percentile(evidence, [tuning.content_evidence_percentile])[0])
    threshold = max(
        tuning.content_evidence_threshold_min,
        min(tuning.content_evidence_threshold_max, outer_p70 * tuning.content_evidence_threshold_multiplier),
    )
    frame_scores: list[dict[str, Any]] = []
    means: list[float] = []
    coverages: list[float] = []
    aspect_errors: list[float] = []
    expected_aspect = CONTENT_ASPECTS_HORIZONTAL.get(detection.film_format)

    for index, frame in enumerate(detection.frames, start=1):
        absolute_box = original_box_to_work(frame, detection.layout, source_w, source_h).clamp(work_w, work_h)
        box = Box(
            max(0, absolute_box.left - outer.left),
            max(0, absolute_box.top - outer.top),
            min(outer.width, absolute_box.right - outer.left),
            min(outer.height, absolute_box.bottom - outer.top),
        )
        if not box.valid():
            continue
        crop = evidence[box.top:box.bottom, box.left:box.right]
        if crop.size == 0:
            continue
        mean = float(crop.mean())
        coverage = float((crop >= threshold).mean())
        means.append(mean)
        coverages.append(coverage)
        actual_aspect = float(absolute_box.width) / max(1.0, float(absolute_box.height))
        aspect_error: Optional[float] = None
        if expected_aspect is not None and expected_aspect > 0:
            aspect_error = abs(actual_aspect - expected_aspect) / expected_aspect
            aspect_errors.append(float(aspect_error))
        frame_scores.append(
            {
                "index": index,
                "mean": mean,
                "coverage": coverage,
                "actual_aspect": actual_aspect,
                "expected_aspect": expected_aspect,
                "aspect_error": aspect_error,
            }
        )

    if not frame_scores:
        return {"used": False, "reason": "no_valid_frames"}

    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    min_mean = float(min(means)) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else None
    aspect_ok = max_aspect_error is None or max_aspect_error <= tuning.content_evidence_aspect_ok_max
    content_present = median_mean >= tuning.content_evidence_present_mean_min or median_coverage >= tuning.content_evidence_present_coverage_min
    support = "ok" if content_present and aspect_ok else "weak"
    if not aspect_ok:
        support = "aspect_conflict"
    elif not content_present:
        support = "low_content"

    detail = {
        "used": True,
        "support": support,
        "composite": "cached_gradient+neighbor_texture+local_contrast+tonal_presence",
        "threshold": threshold,
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": expected_aspect,
        "max_aspect_error": max_aspect_error,
        "frame_scores": frame_scores,
    }
    cache.content_evidence_details[detail_key] = copy.deepcopy(detail)
    return detail


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
    retried = calibrate_v2_candidate(gray, retried, config, fmt, "separator", cache)
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
    retried = calibrate_v2_candidate(gray, retried, config, fmt, "separator", cache)
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
    candidate = detection.detail.get("v2_candidate", {})
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
    retried = calibrate_v2_candidate(gray, retried, config, fmt, "separator", cache)
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


def content_profile_runs(
    evidence: np.ndarray,
    outer: Box,
    count: int,
    format_name: str = "135",
    cache: Optional[AnalysisCache] = None,
) -> tuple[list[tuple[int, int]], dict[str, Any]]:
    cache_key: Optional[tuple[str, int, int, int, int, int]] = None
    if cache is not None and evidence is cache.content_evidence_work:
        cache_key = (str(format_name), int(count), *box_cache_key(outer))
        cached = cache.content_profile_runs.get(cache_key)
        if cached is not None:
            runs, detail = cached
            return list(runs), copy.deepcopy(detail)
    crop = evidence[outer.top:outer.bottom, outer.left:outer.right].astype(np.float32) / 255.0
    if crop.size == 0:
        return [], {"reason": "empty_content_outer"}
    tuning = format_tuning(format_name)
    profile = crop.mean(axis=0)
    smooth_window = max(5, int(round(max(1, outer.width) * tuning.content_profile_smooth_ratio)))
    smoothed = smooth_1d(profile.astype(np.float32), smooth_window)
    p35, p65, p90 = sampled_percentile(smoothed, [35, 65, 90])
    threshold = max(
        tuning.content_profile_threshold_min,
        min(
            tuning.content_profile_threshold_max,
            float(p35 + (p90 - p35) * tuning.content_profile_p35_weight),
            float(p65) * tuning.content_profile_p65_multiplier,
        ),
    )
    runs = runs_from_mask(smoothed >= threshold)
    min_width = max(6, int(round(outer.width / max(1, count) * tuning.content_profile_min_run_ratio)))
    filtered: list[tuple[int, int]] = []
    for start, end in runs:
        if end - start >= min_width:
            filtered.append((outer.left + start, outer.left + end))
    detail = {
        "profile_threshold": threshold,
        "profile_smooth_window": smooth_window,
        "profile_percentiles": {"p35": float(p35), "p65": float(p65), "p90": float(p90)},
        "raw_run_count": len(runs),
        "usable_run_count": len(filtered),
        "min_run_width": min_width,
    }
    if cache_key is not None:
        cache.content_profile_runs[cache_key] = (list(filtered), copy.deepcopy(detail))
    return filtered, detail


def select_content_runs(runs: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
    if len(runs) <= count:
        return runs
    ordered = sorted(runs, key=lambda run: run[1] - run[0], reverse=True)[:count]
    return sorted(ordered)


def content_detection_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
) -> Optional[Detection]:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    tuning = format_tuning(fmt.name)
    wh, ww = gray_work.shape
    if cache is not None and cache.layout == config.layout:
        evidence = cache.content_evidence_work
        evidence_float = cache.content_evidence_float_work
    else:
        evidence = make_content_evidence_gray(gray_work)
        evidence_float = evidence.astype(np.float32) / 255.0
    p55, p75, p92 = sampled_percentile(evidence_float, tuning.content_mask_percentiles)
    mask_threshold = max(
        tuning.content_mask_min,
        min(
            tuning.content_mask_max,
            float(p55 + (p92 - p55) * tuning.content_mask_p55_weight),
            float(p75) * tuning.content_mask_p75_multiplier,
        ),
    )
    mask = evidence_float >= mask_threshold
    outer = bbox_from_mask(mask, min_row_fraction=tuning.content_bbox_min_fraction, min_col_fraction=tuning.content_bbox_min_fraction)
    if outer is None or outer.width < max(tuning.content_outer_min_width_px, int(ww * tuning.content_outer_min_width_ratio)) or outer.height < max(tuning.content_outer_min_height_px, int(wh * tuning.content_outer_min_height_ratio)):
        return None
    outer = outer.expand(max(2, int(round(ww * tuning.outer_mask_expand_ratio))), max(2, int(round(wh * tuning.outer_mask_expand_ratio))), ww, wh)

    expected_aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if expected_aspect is None or expected_aspect <= 0:
        return None
    runs, run_detail = content_profile_runs(evidence, outer, count, fmt.name, cache)
    selected_runs = select_content_runs(runs, count)

    frame_h = max(1.0, float(outer.height))
    expected_w = max(tuning.content_expected_width_min_px, frame_h * expected_aspect)
    raw_boxes: list[Box] = []
    placement = "content_runs" if len(selected_runs) >= count else "content_grid_fallback"
    if placement == "content_runs":
        for start, end in selected_runs[:count]:
            center = (float(start) + float(end)) * 0.5
            left = int(round(center - expected_w * 0.5))
            right = int(round(center + expected_w * 0.5))
            raw_boxes.append(Box(left, outer.top, right, outer.bottom).clamp(ww, wh))
    else:
        if strip_mode == "partial" and count < fmt.default_count:
            pitch = max(expected_w, outer.width / float(max(1, fmt.default_count)))
            total_width = pitch * count
            origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
            start_x = outer.left + origin
        else:
            pitch = max(expected_w, outer.width / float(max(1, count)))
            total_width = pitch * count
            start_x = outer.left + max(0.0, (outer.width - total_width) * 0.5)
        for i in range(count):
            center = start_x + pitch * (i + 0.5)
            raw_boxes.append(Box(int(round(center - expected_w * 0.5)), outer.top, int(round(center + expected_w * 0.5)), outer.bottom).clamp(ww, wh))

    raw_boxes = [box for box in raw_boxes if box.valid()]
    if len(raw_boxes) != count:
        return None

    boxes_work = [box.expand(config.bleed_x, config.bleed_y, ww, wh) for box in raw_boxes]
    boxes = [map_work_box(box, config.layout, gray.shape[1], gray.shape[0]) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, gray.shape[1], gray.shape[0])
    gaps: list[Gap] = []
    for index in range(1, count):
        left_box = raw_boxes[index - 1]
        right_box = raw_boxes[index]
        center = (float(left_box.right) + float(right_box.left)) * 0.5 - float(outer.left)
        gaps.append(Gap(index, center, 0.0, "content", float(left_box.right - outer.left), float(right_box.left - outer.left)))

    means: list[float] = []
    coverages: list[float] = []
    for box in raw_boxes:
        crop = evidence_float[box.top:box.bottom, box.left:box.right]
        if crop.size:
            means.append(float(crop.mean()))
            coverages.append(float((crop >= mask_threshold).mean()))
    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    run_conf = min(1.0, len(selected_runs) / float(max(1, count)))
    coverage_conf = min(1.0, median_coverage / tuning.content_conf_coverage_norm)
    mean_conf = min(1.0, median_mean / tuning.content_conf_mean_norm)
    aspect_errors = [abs((box.width / max(1.0, float(box.height))) - expected_aspect) / expected_aspect for box in raw_boxes]
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else 1.0
    aspect_conf = max(0.0, min(1.0, 1.0 - max_aspect_error / tuning.content_conf_aspect_norm))
    confidence = (
        tuning.content_candidate_coverage_weight * coverage_conf
        + tuning.content_candidate_mean_weight * mean_conf
        + tuning.content_candidate_run_weight * run_conf
        + tuning.content_candidate_aspect_weight * aspect_conf
    )
    reasons: list[str] = []
    if placement != "content_runs":
        confidence = min(confidence, tuning.content_grid_fallback_cap)
        reasons.append("content_grid_fallback")
    if len(runs) != count:
        confidence = min(confidence, tuning.content_run_mismatch_cap)
        reasons.append("content_run_count_mismatch")
    if run_conf < 1.0:
        confidence = min(confidence, tuning.content_runs_incomplete_cap)
        reasons.append("content_runs_incomplete")
    if median_coverage < tuning.content_weak_coverage:
        confidence = min(confidence, tuning.content_weak_coverage_cap)
        reasons.append("content_coverage_weak")
    if max_aspect_error > tuning.content_aspect_uncertain:
        confidence = min(confidence, tuning.content_aspect_uncertain_cap)
        reasons.append("content_aspect_uncertain")
    if strip_mode == "partial":
        reasons.append("partial_strip_count_candidate")
    if confidence < config.confidence_threshold and not reasons:
        reasons.append("content_confidence_low")

    detail = {
        "analysis_source": "content_primary",
        "candidate_count": count,
        "offset_fraction": float(offset_fraction),
        "layout": config.layout,
        "outer_candidate": "content_evidence",
        "work_outer": asdict(outer),
        "content_primary": {
            "used": True,
            "placement": placement,
            "mask_threshold": mask_threshold,
            "expected_frame_aspect": expected_aspect,
            "expected_frame_width": expected_w,
            "median_mean": median_mean,
            "median_coverage": median_coverage,
            "run_conf": run_conf,
            "coverage_conf": coverage_conf,
            "mean_conf": mean_conf,
            "max_aspect_error": max_aspect_error,
            "raw_boxes": [asdict(box) for box in raw_boxes],
            **run_detail,
        },
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
    }
    return Detection(fmt.name, config.layout, strip_mode, count, outer_original, boxes, gaps, float(max(0.0, min(1.0, confidence))), sorted(set(reasons)), detail)


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
        or (hard_detected >= tuning.score_135_min_hard_gaps and equal <= max(tuning.score_135_max_equal_min, expected_gaps // 2))
        or (actual_detected >= 1 and enhanced_detected >= 2 and equal <= max(tuning.score_135_max_equal_min, expected_gaps // 2))
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
            or (fmt.name == "135" and tuning.score_allow_135_full_detected_geometry and detected == expected_gaps)
        )
        and tuning.score_full_outer_min_area <= outer_area <= tuning.score_outer_max_area
        and outer_area <= tuning.score_outer_too_large
        and enough_135_separator_evidence
        and (fmt.name == "135" or (fmt.name == "half" and tuning.score_allow_half_geometry) or (reliable >= expected_gaps and equal == 0))
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
            confidence = min(confidence, tuning.score_135_low_hard_cap)
        elif hard_detected < 2 and enhanced_detected < 2:
            confidence = min(confidence, tuning.score_135_low_hard_cap)
        elif equal >= max(2, expected_gaps // 2 + 1):
            confidence = min(confidence, tuning.score_135_mostly_equal_cap)
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


def detection_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        -float(detection.detail.get("width_cv", 1.0)),
    )


def detect_candidate_for_count(
    gray: np.ndarray,
    config: Config,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    gap_max_width_ratio_override: Optional[float] = None,
) -> Detection:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    tuning = format_tuning(fmt.name)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        include_separator_first_mode="always",
        include_long_axis_edge_anchor_mode="always",
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
    best = max(candidates, key=lambda d: detection_rank(d, config.confidence_threshold))
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "box": asdict(candidate.box)}
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
) -> Optional[Detection]:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    tuning = format_tuning(fmt.name)
    outer_candidates = outer_proposal_candidates(
        gray_work,
        fmt,
        count,
        strip_mode,
        cache,
        include_separator_first_mode="fallback",
        include_long_axis_edge_anchor_mode="fallback",
        fallback_only=True,
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
    best = max(candidates, key=lambda d: detection_rank(d, config.confidence_threshold))
    areas = [candidate.box.width * candidate.box.height for candidate in outer_candidates if candidate.box.valid()]
    if areas:
        best.detail["outer_candidate_count"] = len(outer_candidates)
        best.detail["outer_area_spread_ratio"] = (max(areas) - min(areas)) / max(1.0, float(max(areas)))
        best.detail["outer_candidates"] = [
            {"name": candidate.name, "box": asdict(candidate.box)}
            for candidate in outer_candidates
        ]
    return best


def outer_proposal_candidates(
    gray_work: np.ndarray,
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    include_separator_first_mode: str = "off",
    include_long_axis_edge_anchor_mode: str = "off",
    fallback_only: bool = False,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    base_candidates = detect_outer_candidates(gray_work, fmt.name)
    floating_candidates = floating_full_outer_candidates(gray_work, base_candidates, fmt, count, strip_mode)
    pre_separator_candidates = unique_outer_candidates([*base_candidates, *floating_candidates])
    long_axis_candidates: list[OuterCandidate] = []
    if long_axis_edge_anchor_outer_mode_for_strip(tuning, strip_mode) == include_long_axis_edge_anchor_mode:
        long_axis_candidates = long_axis_edge_anchor_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
        )
        pre_separator_candidates = unique_outer_candidates([*pre_separator_candidates, *long_axis_candidates])
    separator_first_candidates: list[OuterCandidate] = []
    if separator_first_outer_mode_for_strip(tuning, strip_mode) == include_separator_first_mode:
        separator_first_candidates = separator_first_outer_candidates(
            gray_work,
            pre_separator_candidates,
            fmt,
            count,
            strip_mode,
            cache,
        )
    if fallback_only:
        return unique_outer_candidates([*long_axis_candidates, *separator_first_candidates])
    return unique_outer_candidates([*base_candidates, *floating_candidates, *long_axis_candidates, *separator_first_candidates])


def floating_full_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    enabled = tuning.floating_full_outer_enabled if strip_mode == "full" else tuning.floating_partial_outer_enabled
    if not enabled:
        return []
    if strip_mode == "full" and count != fmt.default_count:
        return []
    if strip_mode not in {"full", "partial"} or count <= 0:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []

    h, w = gray_work.shape
    content = bbox_from_mask(
        gray_work < int(tuning.floating_full_outer_content_threshold),
        min_row_fraction=0.010,
        min_col_fraction=0.010,
    )
    candidates: list[OuterCandidate] = []
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:1]

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0:
            continue
        margin = clamp_int(
            float(outer.height) * tuning.floating_full_outer_content_margin_ratio,
            tuning.floating_full_outer_content_margin_min,
            tuning.floating_full_outer_content_margin_max,
        )
        y_top = outer.top
        y_bottom = outer.bottom
        if content is not None and content.valid():
            y_top = max(outer.top, content.top - margin)
            y_bottom = min(outer.bottom, content.bottom + margin)
            if y_bottom - y_top < max(40, int(round(outer.height * 0.65))):
                y_top = outer.top
                y_bottom = outer.bottom
        height = max(1, y_bottom - y_top)
        min_width = max(80, int(round(float(outer.width) * tuning.floating_full_outer_min_width_ratio)))

        starts_from_content: list[int] = []
        if content is not None and content.valid():
            starts_from_content.extend(
                [
                    int(round(float(content.left - margin))),
                    int(round(float(content.right + margin))),
                    int(round(float((content.left + content.right) * 0.5))),
                ]
            )

        for extra in tuning.floating_full_outer_ratio_extras:
            target_ratio = float(count) * float(aspect) + float(extra)
            target_width = int(round(float(height) * target_ratio))
            if target_width < min_width or target_width >= outer.width:
                continue
            starts: list[int] = []
            available = max(0, outer.width - target_width)
            starts.extend(
                [
                    outer.left,
                    outer.left + int(round(available * 0.50)),
                    outer.left + available,
                ]
            )
            for anchor in starts_from_content:
                starts.append(anchor)
                starts.append(anchor - target_width)
                starts.append(anchor - int(round(target_width * 0.5)))
            for start in starts:
                left = max(outer.left, min(start, outer.right - target_width))
                right = left + target_width
                box = Box(left, y_top, right, y_bottom).clamp(w, h)
                if not box.valid() or box.width < min_width:
                    continue
                candidates.append(
                    OuterCandidate(
                        f"floating_{strip_mode}_{source.name}_r{target_ratio:.3f}",
                        box,
                    )
                )

    return unique_outer_candidates(candidates)[: int(tuning.floating_full_outer_max_candidates)]


def long_axis_edge_anchor_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    enabled = tuning.long_axis_edge_anchor_outer_enabled if strip_mode == "full" else tuning.long_axis_edge_anchor_partial_enabled
    if not enabled:
        return []
    if strip_mode == "full" and count != fmt.default_count:
        return []
    if strip_mode not in {"full", "partial"} or count <= 0:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []
    if cache is not None:
        candidate_key = long_axis_edge_anchor_cache_key(base_candidates, fmt, count, strip_mode)
        cached_candidates = cache.long_axis_edge_anchor_outer_candidates.get(candidate_key)
        if cached_candidates is not None:
            return list(cached_candidates)

    h, w = gray_work.shape
    content = bbox_from_mask(
        gray_work < int(tuning.long_axis_edge_anchor_content_threshold),
        min_row_fraction=0.010,
        min_col_fraction=0.010,
    )
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:1]
    candidates: list[OuterCandidate] = []

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        if strip_mode == "partial":
            if content is None or not content.valid():
                continue
            content_center = ((float(content.left + content.right) * 0.5) - float(outer.left)) / max(1.0, float(outer.width))
            edge_limit = float(tuning.long_axis_edge_anchor_partial_center_ratio)
            if edge_limit <= content_center <= (1.0 - edge_limit):
                continue
        margin = clamp_int(
            float(outer.height) * tuning.long_axis_edge_anchor_content_margin_ratio,
            tuning.long_axis_edge_anchor_content_margin_min,
            tuning.long_axis_edge_anchor_content_margin_max,
        )
        y_top = outer.top
        y_bottom = outer.bottom
        if content is not None and content.valid():
            y_top = max(outer.top, content.top - margin)
            y_bottom = min(outer.bottom, content.bottom + margin)
            if y_bottom - y_top < max(40, int(round(float(outer.height) * 0.65))):
                y_top = outer.top
                y_bottom = outer.bottom
        short_axis = max(1, y_bottom - y_top)
        min_width = max(80, int(round(float(outer.width) * tuning.long_axis_edge_anchor_min_width_ratio)))

        for extra in tuning.long_axis_edge_anchor_ratio_extras:
            target_ratio = float(count) * float(aspect) + float(extra)
            target_width = int(round(float(short_axis) * target_ratio))
            if target_width < min_width or target_width >= outer.width:
                continue
            anchors = (
                ("start", outer.left, outer.left + target_width),
                ("end", outer.right - target_width, outer.right),
            )
            for anchor_name, left, right in anchors:
                box = Box(int(left), y_top, int(right), y_bottom).clamp(w, h)
                if not box.valid() or box.width < min_width:
                    continue
                candidates.append(
                    OuterCandidate(
                        f"long_axis_edge_anchor_{strip_mode}_{anchor_name}_{source.name}_r{target_ratio:.3f}",
                        box,
                    )
                )

    result = unique_outer_candidates(candidates)[: int(tuning.long_axis_edge_anchor_max_candidates)]
    if cache is not None:
        cache.long_axis_edge_anchor_outer_candidates[candidate_key] = list(result)
    return result


def separator_first_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FilmFormat,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
) -> list[OuterCandidate]:
    tuning = format_tuning(fmt.name)
    if not tuning.separator_first_outer_enabled:
        return []
    if strip_mode == "full" and count != fmt.default_count:
        return []
    if strip_mode not in {"full", "partial"} or count <= 1:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []
    if cache is not None:
        candidate_key = separator_first_cache_key(base_candidates, fmt, count, strip_mode)
        cached_candidates = cache.separator_first_outer_candidates.get(candidate_key)
        if cached_candidates is not None:
            return list(cached_candidates)

    h, w = gray_work.shape
    expected_gaps = count - 1
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[: max(1, int(tuning.separator_first_outer_source_candidates))]
    candidates: list[OuterCandidate] = []

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        short_axis = float(outer.height)
        frame_long = short_axis * float(aspect)
        if frame_long <= 1.0:
            continue
        profile = cached_separator_profile(cache, gray_work, outer, fmt.name)
        if profile.size <= 0:
            continue

        peak_threshold = float(tuning.separator_first_outer_min_score)
        band_threshold = max(tuning.separator_first_outer_band_score, peak_threshold * 0.58)
        min_width = clamp_int(
            short_axis * tuning.separator_first_outer_min_width_ratio,
            tuning.gap_min_width_min,
            tuning.gap_max_width_max,
        )
        max_width = clamp_int(
            short_axis * tuning.separator_first_outer_max_width_ratio,
            max(min_width + 1, tuning.gap_max_width_min),
            tuning.gap_max_width_max,
        )
        guard = clamp_int(short_axis * 0.035, tuning.gap_guard_min, tuning.gap_guard_max)
        edge_margin = clamp_float(
            short_axis * tuning.separator_first_outer_edge_margin_ratio,
            60.0,
            max(60.0, short_axis * 0.80),
        )

        bands: list[dict[str, float]] = []
        for run_start, run_end in runs_from_mask(profile >= peak_threshold):
            band_start, band_end = int(run_start), int(run_end)
            while band_start > 0 and profile[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_width:
                band_start -= 1
            while band_end < len(profile) and profile[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_width:
                band_end += 1
            width = band_end - band_start
            if width < min_width or width > max_width:
                continue
            center = (band_start + band_end - 1) / 2.0
            if center < edge_margin or center > float(outer.width) - edge_margin:
                continue
            left_guard = profile[max(0, band_start - guard):band_start]
            right_guard = profile[band_end:min(len(profile), band_end + guard)]
            if left_guard.size == 0 or right_guard.size == 0:
                continue
            mean_score = float(profile[band_start:band_end].mean())
            side_score = max(float(left_guard.mean()), float(right_guard.mean()))
            prominence = mean_score - side_score
            if mean_score < tuning.gap_min_score or (prominence < 0.02 and mean_score < 0.88):
                continue
            bands.append(
                {
                    "start": float(band_start),
                    "end": float(band_end),
                    "center": float(center),
                    "width": float(width),
                    "score": float(mean_score + 0.8 * prominence),
                }
            )

        if len(bands) < expected_gaps:
            continue
        bands = sorted(
            bands,
            key=lambda band: (-float(band["score"]), float(band["center"])),
        )[: max(expected_gaps, int(tuning.separator_first_outer_band_candidates))]
        sequences: list[tuple[float, tuple[dict[str, float], ...], float]] = []
        for sequence in itertools.combinations(sorted(bands, key=lambda band: float(band["center"])), expected_gaps):
            frame_widths: list[float] = []
            previous: Optional[dict[str, float]] = None
            valid = True
            for band in sequence:
                if previous is not None:
                    inner_width = float(band["start"]) - float(previous["end"])
                    if inner_width <= 0:
                        valid = False
                        break
                    spacing = float(band["center"]) - float(previous["center"])
                    spacing_ratio = spacing / max(1.0, frame_long)
                    if (
                        spacing_ratio < tuning.separator_first_outer_spacing_min_ratio
                        or spacing_ratio > tuning.separator_first_outer_spacing_max_ratio
                    ):
                        valid = False
                        break
                    frame_widths.append(inner_width)
                previous = band
            if not valid or len(frame_widths) != max(0, expected_gaps - 1):
                continue
            if frame_widths:
                frame_errors = [abs(width - frame_long) / max(1.0, frame_long) for width in frame_widths]
                max_frame_error = max(frame_errors)
                mean_frame_error = float(sum(frame_errors) / len(frame_errors))
            else:
                max_frame_error = 0.0
                mean_frame_error = 0.0
            if max_frame_error > tuning.separator_first_outer_frame_error_max:
                continue

            first_band = sequence[0]
            last_band = sequence[-1]
            proposed_left = int(round(outer.left + float(first_band["start"]) - frame_long))
            proposed_right = int(round(outer.left + float(last_band["end"]) + frame_long))
            if proposed_right <= proposed_left:
                continue
            proposed = Box(proposed_left, outer.top, proposed_right, outer.bottom).clamp(w, h)
            if not proposed.valid():
                continue
            left_loss = max(0, -proposed_left)
            right_loss = max(0, proposed_right - w)
            if left_loss > edge_margin or right_loss > edge_margin:
                continue

            separator_total = sum(float(band["width"]) for band in sequence)
            expected_ratio = float(count) * float(aspect) + separator_total / max(1.0, short_axis)
            actual_ratio = proposed.width / max(1.0, float(proposed.height))
            ratio_error = abs(actual_ratio - expected_ratio)
            sequence_score = sum(float(band["score"]) for band in sequence) / max(1, len(sequence))
            sequence_rank = ratio_error + mean_frame_error - 0.02 * sequence_score
            sequences.append((sequence_rank, sequence, expected_ratio))

        for rank, (_sequence_rank, sequence, expected_ratio) in enumerate(
            sorted(sequences, key=lambda item: item[0])[: max(1, int(tuning.separator_first_outer_pair_candidates))],
            start=1,
        ):
            first_band = sequence[0]
            last_band = sequence[-1]
            proposed = Box(
                int(round(outer.left + float(first_band["start"]) - frame_long)),
                outer.top,
                int(round(outer.left + float(last_band["end"]) + frame_long)),
                outer.bottom,
            ).clamp(w, h)
            if not proposed.valid():
                continue
            candidates.append(
                OuterCandidate(
                    f"separator_first_{source.name}_{rank}_r{expected_ratio:.3f}",
                    proposed,
                )
            )

    result = unique_outer_candidates(candidates)[: int(tuning.separator_first_outer_max_candidates)]
    if cache is not None:
        cache.separator_first_outer_candidates[candidate_key] = list(result)
    return result


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
        calibrated = calibrate_v2_candidate(gray, raw, lane_config, fmt_135, "separator", cache)
        calibrated.detail["dual_lane_index"] = lane_index
        calibrated.detail["dual_lane_work_box"] = asdict(lane)
        candidates.append(calibrated)
    if not candidates:
        return None
    best = max(candidates, key=lambda d: v2_candidate_rank(d, config.confidence_threshold))
    content_detail = content_evidence_detail(gray, best, cache)
    outer_alignment = outer_content_alignment_detail(gray, best, cache)
    best.detail["content_evidence"] = content_detail
    best.detail["outer_content_alignment"] = outer_alignment
    if bool(content_detail.get("used", False)):
        support = str(content_detail.get("support", ""))
        if support == "aspect_conflict":
            best.confidence = min(best.confidence, 0.82)
            best.review_reasons.append("content_aspect_conflict")
        elif support in {"low_content", "weak"} and best.confidence >= config.confidence_threshold:
            best.confidence = min(best.confidence, 0.84)
            best.review_reasons.append("content_evidence_weak")
    if bool(outer_alignment.get("used", False)) and not bool(outer_alignment.get("ok", True)):
        best.confidence = min(best.confidence, 0.84)
        best.review_reasons.append("outer_content_bbox_mismatch")
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
            "analysis_source": "unsupported_mode",
            "candidate_count": 0,
            "layout": config.layout,
            "work_outer": asdict(outer),
            "v2_competition": {
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
            "v2_candidate": detection.detail.get("v2_candidate", {}),
        }
        for index, detection in enumerate(confirmed_lanes, start=1)
    ]
    detail = {
        "analysis_source": "135_dual_parallel_lanes",
        "layout": config.layout,
        "candidate_count": 12,
        "work_outer": asdict(combined_work_outer),
        "dual_lane_work_boxes": [asdict(lane) for lane in lanes],
        "dual_lane_detections": lane_summaries,
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
        "v2_competition": {
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


def partial_candidates(fmt: FilmFormat, seed: Optional[Detection]) -> tuple[int, ...]:
    default = fmt.default_count
    candidates: set[int] = {default, max(1, default - 1), max(1, default - 2), 1}
    if default >= 3:
        candidates.add(2)
    if default >= 6:
        candidates.add(max(1, default // 2))
    if seed is not None:
        detected = int(seed.detail.get("detected_gaps", 0))
        for count in (detected, detected + 1, detected + 2):
            if count >= 1:
                candidates.add(count)
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


def content_is_ambiguous(detection: Detection) -> bool:
    return bool(CONTENT_AMBIGUITY_REASONS.intersection(detection.review_reasons))


def separator_hard_evidence_ok(detection: Detection, threshold: float) -> tuple[bool, dict[str, Any]]:
    tuning = format_tuning(detection.film_format)
    expected = max(0, int(detection.count) - 1)
    actual = int(detection.detail.get("actual_detected_gaps", 0))
    wide = int(detection.detail.get("wide_detected_gaps", 0))
    enhanced = int(detection.detail.get("enhanced_detected_gaps", 0))
    grid = int(detection.detail.get("grid_gaps", 0))
    equal = int(detection.detail.get("equal_gaps", 0))
    hard = actual + wide + enhanced
    hard_indexes = [
        int(gap.index)
        for gap in detection.gaps
        if gap.method in HARD_GAP_METHODS
    ]
    edge_pair_scores = [
        float(gap.score)
        for gap in detection.gaps
        if gap.method == "edge-pair"
    ]
    detected_scores = [
        float(gap.score)
        for gap in detection.gaps
        if gap.method == "detected"
    ]
    wide_scores = [
        float(gap.score)
        for gap in detection.gaps
        if gap.method == "wide-separator"
    ]
    leading_grid_scores: list[float] = []
    for gap in detection.gaps:
        if gap.method != "grid":
            break
        leading_grid_scores.append(float(gap.score))
    separator_analysis = detection.detail.get("separator_analysis", {})
    enhanced_accepted = (
        int(separator_analysis.get("accepted_count", 0) or 0)
        if isinstance(separator_analysis, dict)
        else 0
    )
    hard_adjacent_late = False
    if hard_indexes:
        expected_sequence = list(
            range(max(hard_indexes) - len(hard_indexes) + 1, max(hard_indexes) + 1)
        )
        hard_adjacent_late = hard_indexes == expected_sequence and min(hard_indexes) >= 4
    leading_grid_failure = (
        tuning.leading_grid_failure_enabled
        and detection.strip_mode == "full"
        and expected >= tuning.leading_grid_failure_min_count
        and len(leading_grid_scores) >= tuning.leading_grid_failure_leading_count
        and all(score < tuning.leading_grid_failure_low_score for score in leading_grid_scores[:tuning.leading_grid_failure_leading_count])
        and sum(1 for score in leading_grid_scores[:tuning.leading_grid_failure_leading_count] if score < tuning.leading_grid_failure_very_low_score) >= tuning.leading_grid_failure_very_low_count
        and enhanced_accepted == 0
        and len(hard_indexes) <= tuning.leading_grid_failure_max_hard
        and hard_adjacent_late
    )

    if expected == 0:
        ok = detection.confidence >= threshold
        reason = "single_frame_no_separator_needed" if ok else "single_frame_low_confidence"
    elif detection.confidence < threshold:
        ok = False
        reason = "separator_below_threshold"
    elif leading_grid_failure:
        ok = False
        reason = "135_leading_grid_separator_failure"
    elif tuning.separator_gate_mode == "135":
        needed = min(expected, tuning.separator_135_needed_hard_max)
        ok = hard >= needed and equal <= max(tuning.separator_135_max_equal_min, expected // 2)
        reason = "135_hard_separator_support" if ok else "135_separator_support_weak"
    elif tuning.separator_gate_mode == "half":
        ok = bool(tuning.separator_half_allow_geometry_support) and detection.confidence >= threshold and equal <= expected
        reason = "half_geometry_support" if ok else "half_separator_support_weak"
    else:
        needed = max(1, expected if tuning.separator_120_require_all_hard else min(expected, 1))
        ok = hard >= needed
        reason = "120_hard_separator_support" if ok else "120_separator_support_weak"
        if ok and detection.strip_mode == "full" and detection.count == FORMATS[detection.film_format].default_count:
            if wide < tuning.separator_120_min_wide_gaps_for_auto:
                ok = False
                reason = "120_wide_separator_support_weak"
            edge_min = (
                tuning.separator_120_edge_pair_min_score_with_wide
                if wide > 0
                else tuning.separator_120_edge_pair_min_score_without_wide
            )
            if ok and edge_pair_scores and min(edge_pair_scores) < edge_min:
                ok = False
                reason = "120_edge_pair_support_weak"

    return ok, {
        "ok": ok,
        "reason": reason,
        "expected_gaps": expected,
        "hard_gaps": hard,
        "actual_detected_gaps": actual,
        "wide_detected_gaps": wide,
        "enhanced_detected_gaps": enhanced,
        "grid_gaps": grid,
        "equal_gaps": equal,
        "hard_gap_indexes": hard_indexes,
        "edge_pair_scores": edge_pair_scores,
        "detected_scores": detected_scores,
        "wide_separator_scores": wide_scores,
        "leading_grid_scores": leading_grid_scores,
        "enhanced_separator_accepted_count": enhanced_accepted,
        "leading_grid_separator_failure": bool(leading_grid_failure),
        "separator_confidence": float(detection.confidence),
        "format_policy": tuning.name,
    }


def content_only_partial_can_pass(detection: Detection, threshold: float, fmt: FilmFormat) -> bool:
    tuning = format_tuning(fmt.name)
    min_partial_count = tuning.partial_content_min_count_35mm if fmt.default_count >= 6 else tuning.partial_content_min_count_small
    return (
        tuning.content_only_partial_enabled
        and
        detection.strip_mode == "partial"
        and detection.count < fmt.default_count
        and detection.count >= min_partial_count
        and detection.confidence >= max(threshold, CONTENT_ONLY_PARTIAL_PASS_MIN_CONFIDENCE)
        and not content_is_ambiguous(detection)
    )


def partial_safe_extra_frames_pass_detail(
    detection: Detection,
    hard_detail: dict[str, Any],
    content_detail: dict[str, Any],
    fmt: FilmFormat,
    source: str,
    joint_score: float,
    content_score: float,
    geometry_score: float,
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
    }


def content_support_score(detail: dict[str, Any], format_name: str = "135") -> float:
    if not bool(detail.get("used", False)):
        return 0.0
    tuning = format_tuning(format_name)
    mean_score = min(1.0, float(detail.get("median_mean", 0.0)) / tuning.content_conf_mean_norm)
    coverage_score = min(1.0, float(detail.get("median_coverage", 0.0)) / tuning.content_conf_coverage_norm)
    aspect_error = detail.get("max_aspect_error")
    aspect_score = 0.75 if aspect_error is None else max(0.0, min(1.0, 1.0 - float(aspect_error) / tuning.content_support_aspect_norm))
    support = str(detail.get("support", ""))
    support_gate = {
        "ok": tuning.content_support_gate_ok,
        "weak": tuning.content_support_gate_weak,
        "low_content": tuning.content_support_gate_low_content,
        "aspect_conflict": tuning.content_support_gate_aspect_conflict,
    }.get(support, tuning.content_support_gate_unknown)
    return max(0.0, min(1.0, (tuning.content_support_coverage_weight * coverage_score + tuning.content_support_mean_weight * mean_score + tuning.content_support_aspect_weight * aspect_score) * support_gate))


def geometry_support_score(detection: Detection, content_detail: dict[str, Any]) -> float:
    tuning = format_tuning(detection.film_format)
    width_cv = float(detection.detail.get("width_cv", 0.0))
    if width_cv <= 0.0:
        widths = np.array([box.width for box in detection.frames if box.valid()], dtype=np.float64)
        width_cv = float(widths.std() / max(1.0, widths.mean())) if widths.size else 1.0
    width_score = max(0.0, min(1.0, 1.0 - width_cv / tuning.geometry_width_cv_norm))
    outer_area = float(detection.detail.get("outer_area_ratio", 0.70))
    outer_score = 1.0 if tuning.score_outer_min_area <= outer_area <= tuning.score_outer_too_large else tuning.geometry_support_outer_uncertain
    aspect_error = content_detail.get("max_aspect_error")
    aspect_score = tuning.geometry_support_no_aspect_score if aspect_error is None else max(0.0, min(1.0, 1.0 - float(aspect_error) / tuning.content_support_aspect_norm))
    count_score = 1.0 if len(detection.frames) == detection.count else 0.0
    return max(0.0, min(1.0, tuning.geometry_support_width_weight * width_score + tuning.geometry_support_outer_weight * outer_score + tuning.geometry_support_aspect_weight * aspect_score + tuning.geometry_support_count_weight * count_score))


def separator_support_score(detection: Detection, hard_detail: dict[str, Any]) -> float:
    tuning = format_tuning(detection.film_format)
    expected = max(0, int(hard_detail.get("expected_gaps", 0)))
    if expected == 0:
        return 1.0 if detection.confidence >= 0.85 else min(0.75, detection.confidence)
    hard = int(hard_detail.get("hard_gaps", 0))
    grid = int(hard_detail.get("grid_gaps", 0))
    equal = int(hard_detail.get("equal_gaps", 0))
    hard_ratio = min(1.0, hard / float(max(1, expected)))
    model_ratio = min(1.0, (hard + tuning.separator_model_grid_credit * grid + tuning.separator_model_equal_credit * equal) / float(max(1, expected)))
    return max(0.0, min(1.0, tuning.separator_support_hard_weight * hard_ratio + tuning.separator_support_model_weight * model_ratio))


def hard_full_calibration_floor_applies(candidate: Detection, hard_detail: dict[str, Any], fmt: FilmFormat, source: str) -> bool:
    tuning = format_tuning(fmt.name)
    expected = max(0, int(hard_detail.get("expected_gaps", 0) or 0))
    hard = int(hard_detail.get("hard_gaps", 0) or 0)
    equal = int(hard_detail.get("equal_gaps", 0) or 0)
    width_cv = float(candidate.detail.get("width_cv", 1.0) or 1.0)
    return (
        source == "separator"
        and tuning.calibrate_hard_full_confidence_floor > 0.0
        and candidate.strip_mode == "full"
        and candidate.count == fmt.default_count
        and len(candidate.frames) == candidate.count
        and expected > 0
        and hard >= expected
        and equal == 0
        and width_cv <= tuning.score_full_width_cv
    )


def half_wide_geometry_support_applies(
    candidate: Detection,
    hard_detail: dict[str, Any],
    fmt: FilmFormat,
    source: str,
    support: str,
    joint_score: float,
    threshold: float,
) -> bool:
    tuning = format_tuning(fmt.name)
    expected = max(0, int(hard_detail.get("expected_gaps", 0) or 0))
    hard = int(hard_detail.get("hard_gaps", 0) or 0)
    grid = int(hard_detail.get("grid_gaps", 0) or 0)
    equal = int(hard_detail.get("equal_gaps", 0) or 0)
    width_cv = float(candidate.detail.get("width_cv", 1.0) or 1.0)
    outer_area = float(candidate.detail.get("outer_area_ratio", 1.0) or 1.0)
    min_hard = int(math.ceil(expected * tuning.separator_half_wide_geometry_min_hard_ratio))
    return (
        fmt.name == "half"
        and source == "separator"
        and candidate.strip_mode == "full"
        and candidate.count == fmt.default_count
        and len(candidate.frames) == candidate.count
        and expected > 0
        and hard >= min_hard
        and hard + grid >= expected
        and equal == 0
        and width_cv <= tuning.score_full_width_cv
        and support == "ok"
        and joint_score >= tuning.separator_half_wide_geometry_min_joint_score
        and outer_area <= tuning.score_outer_max_area
    )


def half_stable_grid_support_applies(
    candidate: Detection,
    hard_detail: dict[str, Any],
    fmt: FilmFormat,
    source: str,
    support: str,
    joint_score: float,
) -> bool:
    tuning = format_tuning(fmt.name)
    expected = max(0, int(hard_detail.get("expected_gaps", 0) or 0))
    hard = int(hard_detail.get("hard_gaps", 0) or 0)
    grid = int(hard_detail.get("grid_gaps", 0) or 0)
    equal = int(hard_detail.get("equal_gaps", 0) or 0)
    width_cv = float(candidate.detail.get("width_cv", 1.0) or 1.0)
    outer_area = float(candidate.detail.get("outer_area_ratio", 1.0) or 1.0)
    min_hard = int(math.ceil(expected * tuning.separator_half_stable_grid_min_hard_ratio))
    return (
        fmt.name == "half"
        and source == "separator"
        and candidate.strip_mode == "full"
        and candidate.count == fmt.default_count
        and len(candidate.frames) == candidate.count
        and expected > 0
        and hard >= min_hard
        and hard + grid >= expected
        and equal == 0
        and width_cv <= tuning.score_full_width_cv
        and support == "ok"
        and joint_score >= tuning.separator_half_stable_grid_min_joint_score
        and outer_area <= tuning.score_outer_max_area
    )


def candidate_counts_for_format(config: Config, fmt: FilmFormat) -> list[tuple[int, str, tuple[float, ...]]]:
    def v2_offsets(count: int) -> tuple[float, ...]:
        return partial_offsets(fmt, count)

    if config.strip_mode == "full":
        return [(config.count, "full", (0.0,))]
    if config.strip_mode == "partial":
        if config.count_override is not None:
            return [(config.count, "partial", v2_offsets(config.count))]
        tuning = format_tuning(fmt.name)
        return [
            (count, "partial", v2_offsets(count))
            for count in partial_candidates(fmt, None)
            if count < fmt.default_count or tuning.partial_auto_include_default_count
        ] or [(1, "partial", partial_offsets(fmt, 1))]
    raise ValueError(f"Unsupported strip mode: {config.strip_mode}")


def calibrate_v2_candidate(
    gray: np.ndarray,
    detection: Detection,
    config: Config,
    fmt: FilmFormat,
    source: str,
    cache: Optional[AnalysisCache] = None,
) -> Detection:
    candidate = replace(
        detection,
        review_reasons=list(detection.review_reasons),
        detail=dict(detection.detail),
    )
    content_detail = content_evidence_detail(gray, candidate, cache)
    hard_ok, hard_detail = separator_hard_evidence_ok(candidate, config.confidence_threshold)
    tuning = format_tuning(fmt.name)
    floor_applies = hard_full_calibration_floor_applies(candidate, hard_detail, fmt, source)
    if floor_applies:
        gate_candidate = replace(
            candidate,
            confidence=max(float(candidate.confidence), tuning.calibrate_hard_full_confidence_floor),
        )
        hard_ok, hard_detail = separator_hard_evidence_ok(gate_candidate, config.confidence_threshold)
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
        reasons.append("separator_hard_evidence_weak")
    if support == "aspect_conflict":
        reasons.append("content_aspect_conflict")
    elif support == "low_content":
        reasons.append("content_evidence_weak")
    elif support == "weak":
        reasons.append("content_evidence_weak")
    if source == "content" and not content_only_partial_can_pass(candidate, config.confidence_threshold, fmt):
        reasons.append("content_only_not_enough_for_auto")

    confidence = max(float(candidate.confidence), joint_score)
    if floor_applies:
        confidence = max(confidence, tuning.calibrate_hard_full_confidence_floor)
    partial_safe_extra_frames = partial_safe_extra_frames_pass_detail(
        candidate,
        hard_detail,
        content_detail,
        fmt,
        source,
        joint_score,
        content_score,
        geometry_score,
    )
    partial_safe_extra_frames_ok = bool(partial_safe_extra_frames.get("ok", False))
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
                "separator_hard_evidence_weak",
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
        auto_gate = content_only_partial_can_pass(candidate, config.confidence_threshold, fmt)

    if not auto_gate:
        cap = tuning.calibrate_partial_no_auto_cap if candidate.strip_mode == "partial" else tuning.calibrate_full_no_auto_cap
        confidence = min(confidence, cap)
        reasons.append("v2_auto_gate_not_satisfied")
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
    candidate.detail["analysis_source"] = f"v2_{source}_candidate"
    candidate.detail["content_evidence"] = content_detail
    candidate.detail["v2_candidate"] = {
        "source": source,
        "joint_score": float(joint_score),
        "auto_gate": bool(auto_gate),
        "geometry_score": float(geometry_score),
        "separator_score": float(separator_score),
        "content_score": float(content_score),
        "content_support": support,
        "separator_hard_evidence": hard_detail,
        "partial_safe_extra_frames": partial_safe_extra_frames,
    }
    return candidate


def v2_candidate_rank(detection: Detection, threshold: float) -> tuple[int, float, int, float]:
    candidate = detection.detail.get("v2_candidate", {})
    joint = float(candidate.get("joint_score", 0.0)) if isinstance(candidate, dict) else 0.0
    partial_safe = bool(
        isinstance(candidate, dict)
        and isinstance(candidate.get("partial_safe_extra_frames"), dict)
        and candidate["partial_safe_extra_frames"].get("ok", False)
    )
    if partial_safe:
        return (
            1 if detection.confidence >= threshold else 0,
            float(detection.count),
            int(round(float(detection.confidence) * 1000.0)),
            joint,
        )
    return (
        1 if detection.confidence >= threshold else 0,
        float(detection.confidence),
        int(detection.count),
        joint,
    )


def half_review_separator_candidate(
    best: Detection,
    candidates: list[Detection],
) -> Optional[Detection]:
    best_v2 = best.detail.get("v2_candidate", {})
    best_source = best_v2.get("source") if isinstance(best_v2, dict) else None
    if (
        best.film_format != "half"
        or best.strip_mode != "full"
        or best.count != FORMATS["half"].default_count
        or best_source != "content"
        or "content_run_count_mismatch" not in best.review_reasons
    ):
        return None
    plausible: list[Detection] = []
    for candidate in candidates:
        if candidate is best or candidate.film_format != "half" or candidate.strip_mode != "full" or candidate.count != best.count:
            continue
        candidate_v2 = candidate.detail.get("v2_candidate", {})
        if not isinstance(candidate_v2, dict) or candidate_v2.get("source") != "separator":
            continue
        hard_detail = candidate_v2.get("separator_hard_evidence", {})
        if not isinstance(hard_detail, dict):
            continue
        expected = max(1, int(hard_detail.get("expected_gaps", best.count - 1) or best.count - 1))
        hard = int(hard_detail.get("hard_gaps", 0) or 0)
        equal = int(hard_detail.get("equal_gaps", 0) or 0)
        support = str(candidate_v2.get("content_support", ""))
        if hard >= max(1, math.ceil(expected * 0.50)) and equal == 0 and support == "ok":
            plausible.append(candidate)
    if not plausible:
        return None
    return max(
        plausible,
        key=lambda candidate: (
            int((candidate.detail.get("v2_candidate", {}).get("separator_hard_evidence", {}) or {}).get("hard_gaps", 0) or 0),
            float((candidate.detail.get("v2_candidate", {}) or {}).get("joint_score", 0.0) or 0.0),
            float(candidate.confidence),
        ),
    )


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
        ["hard_fallback_no_v2_candidates", "needs_manual_review"],
        {
            "analysis_source": "hard_fallback",
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


def choose_detection_v2(gray: np.ndarray, config: Config, fmt: FilmFormat, cache: Optional[AnalysisCache] = None) -> Detection:
    candidates: list[Detection] = []
    cache = cache if cache is not None and cache.layout == config.layout else make_analysis_cache(gray, config.layout)
    if fmt.name == "135-dual":
        return choose_detection_135_dual(gray, config, cache)
    format_candidates = [fmt]
    for fmt in format_candidates:
        count_specs = candidate_counts_for_format(config, fmt)
        for count, strip_mode, offsets in count_specs:
            if count not in fmt.allowed_counts:
                continue
            for offset in offsets:
                separator = detect_candidate_for_count(gray, config, fmt, count, strip_mode, offset, cache)
                separator_candidate = calibrate_v2_candidate(gray, separator, config, fmt, "separator", cache)
                candidates.append(separator_candidate)
                separator_gate_candidate = separator_candidate
                separator_auto_gate = bool(
                    separator_candidate.detail.get("v2_candidate", {}).get("auto_gate", False)
                )
                tuning = format_tuning(fmt.name)
                wide_retry_allowed = (
                    (strip_mode == "full" and tuning.wide_gap_retry_enabled)
                    or (strip_mode == "partial" and tuning.wide_gap_retry_partial_enabled)
                )
                if (
                    not separator_auto_gate
                    and wide_retry_allowed
                    and tuning.wide_gap_retry_max_width_ratio > tuning.gap_max_width_ratio
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
                    )
                    wide_candidate = calibrate_v2_candidate(gray, wide_separator, config, fmt, "separator", cache)
                    wide_candidate.detail["wide_gap_retry"] = {
                        "used": True,
                        "base_gap_max_width_ratio": float(tuning.gap_max_width_ratio),
                        "retry_gap_max_width_ratio": float(tuning.wide_gap_retry_max_width_ratio),
                    }
                    candidates.append(wide_candidate)
                    wide_auto_gate = bool(
                        wide_candidate.detail.get("v2_candidate", {}).get("auto_gate", False)
                    )
                    if wide_auto_gate:
                        separator_auto_gate = True
                        separator_gate_candidate = wide_candidate
                if (
                    not separator_auto_gate
                    and (
                        separator_first_outer_mode_for_strip(tuning, strip_mode) == "fallback"
                        or long_axis_edge_anchor_outer_mode_for_strip(tuning, strip_mode) == "fallback"
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
                    )
                    if fallback_proposal is not None:
                        fallback_candidate = calibrate_v2_candidate(gray, fallback_proposal, config, fmt, "separator", cache)
                        fallback_candidate.detail["outer_proposal_fallback_retry"] = {
                            "used": True,
                            "separator_first_mode": separator_first_outer_mode_for_strip(tuning, strip_mode),
                            "long_axis_edge_anchor_mode": long_axis_edge_anchor_outer_mode_for_strip(tuning, strip_mode),
                        }
                        candidates.append(fallback_candidate)
                        fallback_auto_gate = bool(
                            fallback_candidate.detail.get("v2_candidate", {}).get("auto_gate", False)
                        )
                        if fallback_auto_gate:
                            separator_auto_gate = True
                            separator_gate_candidate = fallback_candidate
                if strip_mode == "full" and separator_auto_gate and separator_gate_candidate.confidence >= config.confidence_threshold:
                    separator_gate_candidate.detail["content_candidate_skipped"] = "separator_auto_gate_passed"
                    continue
                content = content_detection_for_count(gray, config, fmt, count, strip_mode, offset, cache)
                if content is not None:
                    candidates.append(calibrate_v2_candidate(gray, content, config, fmt, "content", cache))

    if not candidates:
        return hard_fallback_detection(gray, config, fmt)

    candidates = sorted(candidates, key=lambda d: v2_candidate_rank(d, config.confidence_threshold), reverse=True)
    best = candidates[0]
    selected_by_full_guard = False
    selection_override: Optional[str] = None
    half_separator_review = half_review_separator_candidate(best, candidates)
    if half_separator_review is not None and half_separator_review.confidence < config.confidence_threshold:
        half_separator_review.review_reasons.append("half_content_candidate_mismatch_prefers_separator_review")
        half_separator_review.review_reasons = sorted(set(half_separator_review.review_reasons))
        half_separator_review.detail["half_content_candidate_mismatch"] = {
            "content_candidate_confidence": float(best.confidence),
            "content_candidate_review_reasons": list(best.review_reasons),
            "content_candidate_v2": best.detail.get("v2_candidate", {}),
        }
        best = half_separator_review
        selection_override = "half_content_candidate_mismatch_prefers_separator_review"
    if best.strip_mode == "partial":
        best_full = next(
            (
                candidate
                for candidate in candidates
                if candidate.film_format == best.film_format
                and candidate.strip_mode == "full"
                and candidate.count == FORMATS[candidate.film_format].default_count
                and candidate.confidence >= PARTIAL_FULL_COMPETE_MIN_CONFIDENCE
            ),
            None,
        )
        if best_full is not None:
            best_full.review_reasons.append("partial_competes_with_plausible_full_strip")
            best_full.review_reasons = sorted(set(best_full.review_reasons))
            best_full.detail["partial_best"] = {
                "count": int(best.count),
                "confidence": float(best.confidence),
                "review_reasons": list(best.review_reasons),
                "v2_candidate": best.detail.get("v2_candidate", {}),
            }
            best = best_full
            selected_by_full_guard = True
            selection_override = "partial_competes_with_plausible_full_strip"
    second = next((candidate for candidate in candidates if candidate is not best), None)
    selected_tuning = format_tuning(best.film_format)
    competition = [
        {
            "rank": index,
            "selected": candidate is best,
            "format": candidate.film_format,
            "count": int(candidate.count),
            "strip_mode": candidate.strip_mode,
            "confidence": float(candidate.confidence),
            "review_reasons": list(candidate.review_reasons),
            "v2_candidate": candidate.detail.get("v2_candidate", {}),
        }
        for index, candidate in enumerate(candidates[:selected_tuning.candidate_competition_top_n], start=1)
    ]
    best.detail["v2_competition"] = {
        "candidate_count": len(candidates),
        "formats": [fmt.name for fmt in format_candidates],
        "selected_candidate": {
            "format": best.film_format,
            "count": int(best.count),
            "strip_mode": best.strip_mode,
            "confidence": float(best.confidence),
            "review_reasons": list(best.review_reasons),
            "v2_candidate": best.detail.get("v2_candidate", {}),
        },
        "selection_override": selection_override,
        "top_candidates": competition,
    }
    if second is not None:
        margin = float(best.confidence) - float(second.confidence)
        best.detail["v2_competition"]["margin_to_second"] = margin
        second_close = margin < selected_tuning.candidate_competition_close_margin
        partial_full_conflict = (
            best.strip_mode != second.strip_mode
            and min(best.confidence, second.confidence) >= config.confidence_threshold
        )
        best_v2 = best.detail.get("v2_candidate", {})
        best_partial_safe = bool(
            isinstance(best_v2, dict)
            and isinstance(best_v2.get("partial_safe_extra_frames"), dict)
            and best_v2["partial_safe_extra_frames"].get("ok", False)
        )
        if (
            best.confidence >= config.confidence_threshold
            and not selected_by_full_guard
            and not best_partial_safe
            and (second_close or partial_full_conflict)
        ):
            best.confidence = min(best.confidence, selected_tuning.candidate_competition_confidence_cap)
            best.review_reasons.append("v2_candidate_competition_uncertain")
            best.review_reasons = sorted(set(best.review_reasons))
    return best





def detect_image(*args, **kwargs) -> Detection:
    """Run the current full detection pipeline.

    This is the stable package-level detection entry point used by V4 callers.
    """

    return choose_detection_v2(*args, **kwargs)
