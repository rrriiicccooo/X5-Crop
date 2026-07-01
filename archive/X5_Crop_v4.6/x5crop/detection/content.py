from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ..common import (
    CONTENT_ASPECTS_HORIZONTAL,
    AnalysisCache,
    Box,
    Config,
    Detection,
    FilmFormat,
    Gap,
    bbox_from_mask,
    box_from_dict,
    format_tuning,
    runs_from_mask,
    sampled_percentile,
    smooth_1d,
)
from ..constants import ANALYSIS_SOURCE_CONTENT_PRIMARY
from ..evidence import make_content_evidence_gray
from ..geometry import (
    box_cache_key,
    map_work_box,
    original_box_to_work,
    work_gray,
)
from .scoring import content_support_score


def detection_frame_cache_key(detection: Detection) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(box_cache_key(frame) for frame in detection.frames)


def content_detail_cache_key(detection: Detection, source_w: int, source_h: int) -> tuple[Any, ...]:
    return (
        str(detection.film_format),
        str(detection.layout),
        int(source_w),
        int(source_h),
        box_cache_key(detection.outer),
        detection_frame_cache_key(detection),
    )


def expected_content_aspect(format_name: str, layout: str) -> Optional[float]:
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(format_name)
    if aspect is None:
        return None
    if layout == "vertical":
        return 1.0 / aspect
    return aspect


def content_evidence_detail(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
) -> dict[str, Any]:
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


def content_evidence_detail_from_cache(
    gray: np.ndarray,
    detection: Detection,
    cache: AnalysisCache,
) -> dict[str, Any]:
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


def content_mask_outer_detail(
    evidence_float: np.ndarray,
    gray_work_shape: tuple[int, int],
    fmt: FilmFormat,
    cache: Optional[AnalysisCache] = None,
) -> dict[str, Any]:
    cache_key = fmt.name
    if cache is not None:
        cached = cache.content_mask_details.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)
    tuning = format_tuning(fmt.name)
    wh, ww = gray_work_shape
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
    detail: dict[str, Any] = {
        "mask_threshold": float(mask_threshold),
        "mask_percentiles": {"p55": float(p55), "p75": float(p75), "p92": float(p92)},
        "outer": None if outer is None else asdict(outer),
    }
    if outer is not None and outer.valid():
        expanded = outer.expand(
            max(2, int(round(ww * tuning.outer_mask_expand_ratio))),
            max(2, int(round(wh * tuning.outer_mask_expand_ratio))),
            ww,
            wh,
        )
        detail["outer"] = asdict(expanded)
    if cache is not None:
        cache.content_mask_details[cache_key] = copy.deepcopy(detail)
    return detail


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
    mask_detail = content_mask_outer_detail(evidence_float, gray_work.shape, fmt, cache)
    mask_threshold = float(mask_detail["mask_threshold"])
    outer_raw = mask_detail.get("outer")
    outer = box_from_dict(outer_raw) if isinstance(outer_raw, dict) else None
    if outer is None or outer.width < max(tuning.content_outer_min_width_px, int(ww * tuning.content_outer_min_width_ratio)) or outer.height < max(tuning.content_outer_min_height_px, int(wh * tuning.content_outer_min_height_ratio)):
        return None

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
        "analysis_source": ANALYSIS_SOURCE_CONTENT_PRIMARY,
        "candidate_count": count,
        "offset_fraction": float(offset_fraction),
        "layout": config.layout,
        "outer_candidate": "content_evidence",
        "work_outer": asdict(outer),
        "content_primary": {
            "used": True,
            "placement": placement,
            "mask_threshold": mask_threshold,
            "mask_percentiles": mask_detail.get("mask_percentiles", {}),
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
    return Detection(
        fmt.name,
        config.layout,
        strip_mode,
        count,
        outer_original,
        boxes,
        gaps,
        float(max(0.0, min(1.0, confidence))),
        sorted(set(reasons)),
        detail,
    )


__all__ = [
    "content_detection_for_count",
    "content_detail_cache_key",
    "content_evidence_detail",
    "content_evidence_detail_from_cache",
    "content_mask_outer_detail",
    "content_profile_runs",
    "content_support_score",
    "expected_content_aspect",
    "select_content_runs",
]
