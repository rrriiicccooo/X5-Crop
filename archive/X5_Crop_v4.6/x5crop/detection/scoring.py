from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..common import Detection, FilmFormat, format_tuning


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
    return max(
        0.0,
        min(
            1.0,
            (
                tuning.content_support_coverage_weight * coverage_score
                + tuning.content_support_mean_weight * mean_score
                + tuning.content_support_aspect_weight * aspect_score
            )
            * support_gate,
        ),
    )


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
    return max(
        0.0,
        min(
            1.0,
            tuning.geometry_support_width_weight * width_score
            + tuning.geometry_support_outer_weight * outer_score
            + tuning.geometry_support_aspect_weight * aspect_score
            + tuning.geometry_support_count_weight * count_score,
        ),
    )


def separator_support_score(detection: Detection, hard_detail: dict[str, Any]) -> float:
    tuning = format_tuning(detection.film_format)
    expected = max(0, int(hard_detail.get("expected_gaps", 0)))
    if expected == 0:
        return 1.0 if detection.confidence >= 0.85 else min(0.75, detection.confidence)
    hard = int(hard_detail.get("hard_gaps", 0))
    grid = int(hard_detail.get("grid_gaps", 0))
    equal = int(hard_detail.get("equal_gaps", 0))
    hard_ratio = min(1.0, hard / float(max(1, expected)))
    model_ratio = min(
        1.0,
        (hard + tuning.separator_model_grid_credit * grid + tuning.separator_model_equal_credit * equal)
        / float(max(1, expected)),
    )
    return max(
        0.0,
        min(
            1.0,
            tuning.separator_support_hard_weight * hard_ratio
            + tuning.separator_support_model_weight * model_ratio,
        ),
    )


def detail_float(detail: dict[str, Any], key: str, default: float) -> float:
    value = detail.get(key, None)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def hard_full_calibration_floor_applies(
    candidate: Detection,
    hard_detail: dict[str, Any],
    fmt: FilmFormat,
    source: str,
) -> bool:
    tuning = format_tuning(fmt.name)
    expected = max(0, int(hard_detail.get("expected_gaps", 0) or 0))
    hard = int(hard_detail.get("hard_gaps", 0) or 0)
    equal = int(hard_detail.get("equal_gaps", 0) or 0)
    width_cv = detail_float(candidate.detail, "width_cv", 1.0)
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
    width_cv = detail_float(candidate.detail, "width_cv", 1.0)
    outer_area = detail_float(candidate.detail, "outer_area_ratio", 1.0)
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
    width_cv = detail_float(candidate.detail, "width_cv", 1.0)
    outer_area = detail_float(candidate.detail, "outer_area_ratio", 1.0)
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


__all__ = [
    "content_support_score",
    "detail_float",
    "geometry_support_score",
    "half_stable_grid_support_applies",
    "half_wide_geometry_support_applies",
    "hard_full_calibration_floor_applies",
    "separator_support_score",
]
