from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from ..domain import Box
from ..geometry.layout import work_gray
from ..policies.parameters import format_parameters
from ..utils import bbox_from_mask, spatial_shape
from .evidence import make_analysis_gray

def fit_line(
    points: list[tuple[float, float]],
    *,
    min_points: int = 4,
    tolerance_min: float = 2.0,
    tolerance_multiplier: float = 3.0,
) -> Optional[dict[str, Any]]:
    if len(points) < min_points:
        return None
    x = np.array([p[0] for p in points], dtype=np.float64)
    y = np.array([p[1] for p in points], dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = np.abs(y - (slope * x + intercept))
    median_residual = float(np.median(residuals)) if residuals.size else 0.0
    tolerance = max(tolerance_min, median_residual * tolerance_multiplier)
    inliers = residuals <= tolerance
    if int(inliers.sum()) >= min_points and int(inliers.sum()) < len(points):
        slope, intercept = np.polyfit(x[inliers], y[inliers], 1)
        residuals = np.abs(y[inliers] - (slope * x[inliers] + intercept))
        median_residual = float(np.median(residuals)) if residuals.size else 0.0
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "inliers": int(inliers.sum()),
        "samples": len(points),
        "median_residual": median_residual,
    }


def fit_edge_angle(gray: np.ndarray, layout: str, format_name: str) -> tuple[float, dict[str, Any]]:
    tuning = format_parameters(format_name)
    work = work_gray(gray, layout)
    h, w = work.shape
    mask = work < tuning.deskew_outer_dark_threshold
    outer = bbox_from_mask(mask, tuning.deskew_outer_min_fraction, tuning.deskew_outer_min_fraction)
    if outer is None or outer.width < tuning.deskew_min_outer_width:
        return 0.0, {"reason": "no_outer"}

    xs = np.linspace(
        outer.left,
        outer.right - 1,
        num=min(tuning.deskew_max_samples, max(tuning.deskew_min_samples, outer.width // tuning.deskew_sample_width_px)),
    ).astype(int)
    top_points: list[tuple[float, float]] = []
    bottom_points: list[tuple[float, float]] = []
    for x in xs:
        col = mask[:, x]
        ys = np.flatnonzero(col)
        if ys.size < max(tuning.deskew_min_col_content, h * tuning.deskew_min_col_content_ratio):
            continue
        top_points.append((float(x), float(ys[0])))
        bottom_points.append((float(x), float(ys[-1])))

    top_fit = fit_line(
        top_points,
        min_points=tuning.deskew_fit_min_points,
        tolerance_min=tuning.deskew_fit_tolerance_min,
        tolerance_multiplier=tuning.deskew_fit_tolerance_multiplier,
    )
    bottom_fit = fit_line(
        bottom_points,
        min_points=tuning.deskew_fit_min_points,
        tolerance_min=tuning.deskew_fit_tolerance_min,
        tolerance_multiplier=tuning.deskew_fit_tolerance_multiplier,
    )
    fits = [fit for fit in (top_fit, bottom_fit) if fit is not None]
    if not fits:
        return 0.0, {"reason": "not_enough_points", "top_samples": len(top_points), "bottom_samples": len(bottom_points)}

    slopes = [float(fit["slope"]) for fit in fits]
    if len(slopes) == 2 and abs(slopes[0] - slopes[1]) > tuning.deskew_slope_delta_max:
        return 0.0, {
            "reason": "top_bottom_disagree",
            "top": top_fit,
            "bottom": bottom_fit,
            "slope_delta": abs(slopes[0] - slopes[1]),
        }
    if any(float(fit["median_residual"]) > max(tuning.deskew_residual_min, h * tuning.deskew_residual_height_ratio) for fit in fits):
        return 0.0, {"reason": "high_residual", "top": top_fit, "bottom": bottom_fit}

    slope = float(np.median(slopes))
    angle = math.degrees(math.atan(slope))
    if layout == "vertical":
        angle = -angle
    return angle, {
        "slope": slope,
        "top": top_fit,
        "bottom": bottom_fit,
        "samples": len(top_points) + len(bottom_points),
    }


def deskew_quality(detail: dict[str, Any]) -> float:
    if detail.get("reason"):
        return -1.0
    fits = [detail.get("top"), detail.get("bottom")]
    score = 0.0
    for fit in fits:
        if isinstance(fit, dict):
            score += float(fit.get("inliers", 0)) * 2.0
            score -= float(fit.get("median_residual", 10.0))
    return score


def choose_deskew_angle(gray: np.ndarray, layout: str, analysis: str, format_name: str) -> tuple[float, dict[str, Any]]:
    tuning = format_parameters(format_name)
    base_angle, base_detail = fit_edge_angle(gray, layout, format_name)
    base_detail["source"] = "base"
    if analysis == "off":
        return base_angle, base_detail
    if analysis == "auto" and deskew_quality(base_detail) >= tuning.deskew_auto_quality_ok:
        base_detail["enhanced_candidate"] = {"skipped": "auto_base_quality_ok"}
        return base_angle, base_detail
    enhanced_gray = make_analysis_gray(gray)
    enhanced_angle, enhanced_detail = fit_edge_angle(enhanced_gray, layout, format_name)
    enhanced_detail["source"] = "enhanced"
    if deskew_quality(enhanced_detail) > deskew_quality(base_detail) + tuning.deskew_enhanced_quality_gain:
        enhanced_detail["base_candidate"] = base_detail
        return enhanced_angle, enhanced_detail
    base_detail["enhanced_candidate"] = enhanced_detail
    return base_angle, base_detail


def dtype_white(dtype: np.dtype) -> int | float:
    if np.issubdtype(dtype, np.integer):
        return int(np.iinfo(dtype).max)
    return 1.0


def rotate_array_expand(arr: np.ndarray, angle_degrees: float, axes: str) -> np.ndarray:
    if abs(angle_degrees) < 1e-9:
        return arr
    if axes == "SYX":
        rotated = rotate_array_expand(np.moveaxis(arr, 0, -1), angle_degrees, "YXS")
        return np.moveaxis(rotated, -1, 0)
    angle = math.radians(angle_degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    h, w = spatial_shape(arr)
    corners = np.array(
        [[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]],
        dtype=np.float64,
    )
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    centered = corners - np.array([cx, cy])
    rot = np.column_stack(
        [
            centered[:, 0] * cos_a - centered[:, 1] * sin_a,
            centered[:, 0] * sin_a + centered[:, 1] * cos_a,
        ]
    )
    min_xy = rot.min(axis=0)
    max_xy = rot.max(axis=0)
    out_w = int(math.ceil(max_xy[0] - min_xy[0] + 1))
    out_h = int(math.ceil(max_xy[1] - min_xy[1] + 1))
    out_shape = (out_h, out_w) + tuple(arr.shape[2:])
    out = np.full(out_shape, dtype_white(arr.dtype), dtype=arr.dtype)

    out_cx = (out_w - 1) / 2.0
    out_cy = (out_h - 1) / 2.0
    chunk = 256
    for y0 in range(0, out_h, chunk):
        y1 = min(out_h, y0 + chunk)
        yy, xx = np.mgrid[y0:y1, 0:out_w].astype(np.float64)
        x_rel = xx - out_cx
        y_rel = yy - out_cy
        src_x = x_rel * cos_a + y_rel * sin_a + cx
        src_y = -x_rel * sin_a + y_rel * cos_a + cy
        valid = (src_x >= 0) & (src_x <= w - 1) & (src_y >= 0) & (src_y <= h - 1)
        if not valid.any():
            continue
        x0f = np.floor(src_x).astype(np.int64)
        y0f = np.floor(src_y).astype(np.int64)
        x1f = np.clip(x0f + 1, 0, w - 1)
        y1f = np.clip(y0f + 1, 0, h - 1)
        x0f = np.clip(x0f, 0, w - 1)
        y0f = np.clip(y0f, 0, h - 1)
        wx = src_x - x0f
        wy = src_y - y0f
        if arr.ndim == 2:
            value = (
                arr[y0f, x0f] * (1 - wx) * (1 - wy)
                + arr[y0f, x1f] * wx * (1 - wy)
                + arr[y1f, x0f] * (1 - wx) * wy
                + arr[y1f, x1f] * wx * wy
            )
            out[y0:y1, :][valid] = np.clip(value[valid], 0, dtype_white(arr.dtype)).astype(arr.dtype)
        elif axes == "YXS":
            value = (
                arr[y0f, x0f].astype(np.float64) * ((1 - wx) * (1 - wy))[..., None]
                + arr[y0f, x1f].astype(np.float64) * (wx * (1 - wy))[..., None]
                + arr[y1f, x0f].astype(np.float64) * ((1 - wx) * wy)[..., None]
                + arr[y1f, x1f].astype(np.float64) * (wx * wy)[..., None]
            )
            out_chunk = out[y0:y1, :]
            out_chunk[valid] = np.clip(value[valid], 0, dtype_white(arr.dtype)).astype(arr.dtype)
        else:
            raise ValueError(f"Unsupported axes for deskew rotation: {axes}")
    return out


def crop_array(arr: np.ndarray, axes: str, box: Box) -> np.ndarray:
    if axes == "YX":
        return arr[box.top:box.bottom, box.left:box.right]
    if axes == "YXS":
        return arr[box.top:box.bottom, box.left:box.right, :]
    if axes == "SYX":
        return arr[:, box.top:box.bottom, box.left:box.right]
    raise ValueError(f"Unsupported axes: {axes}")


def validate_source_crop_pixels(source_arr: np.ndarray, axes: str, box: Box, cropped: np.ndarray) -> None:
    expected = np.ascontiguousarray(crop_array(source_arr, axes, box))
    if expected.dtype != cropped.dtype or tuple(expected.shape) != tuple(cropped.shape):
        raise RuntimeError(
            f"Source crop validation failed: expected {expected.shape}/{expected.dtype}, "
            f"got {cropped.shape}/{cropped.dtype}"
        )
    if not np.array_equal(expected, cropped):
        raise RuntimeError("Source crop validation failed: cropped pixels differ from source")
