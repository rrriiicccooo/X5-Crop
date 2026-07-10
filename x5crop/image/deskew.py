from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from ..geometry.layout import work_gray
from ..utils import bbox_from_mask
from .evidence import DeskewFallbackEvidenceParameters, make_deskew_fallback_gray
from .deskew_parameters import DeskewParameters

def fit_line(
    points: list[tuple[float, float]],
    *,
    min_points: int,
    tolerance_min: float,
    tolerance_multiplier: float,
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


def fit_edge_angle(gray: np.ndarray, layout: str, deskew: DeskewParameters) -> tuple[float, dict[str, Any]]:
    work = work_gray(gray, layout)
    h, w = work.shape
    mask = work < deskew.outer_dark_threshold
    outer = bbox_from_mask(mask, deskew.outer_min_fraction, deskew.outer_min_fraction)
    if outer is None or outer.width < deskew.min_outer_width:
        return 0.0, {"reason": "no_outer"}

    xs = np.linspace(
        outer.left,
        outer.right - 1,
        num=min(deskew.max_samples, max(deskew.min_samples, outer.width // deskew.sample_width_px)),
    ).astype(int)
    top_points: list[tuple[float, float]] = []
    bottom_points: list[tuple[float, float]] = []
    for x in xs:
        col = mask[:, x]
        ys = np.flatnonzero(col)
        if ys.size < max(deskew.min_col_content, h * deskew.min_col_content_ratio):
            continue
        top_points.append((float(x), float(ys[0])))
        bottom_points.append((float(x), float(ys[-1])))

    top_fit = fit_line(
        top_points,
        min_points=deskew.fit_min_points,
        tolerance_min=deskew.fit_tolerance_min,
        tolerance_multiplier=deskew.fit_tolerance_multiplier,
    )
    bottom_fit = fit_line(
        bottom_points,
        min_points=deskew.fit_min_points,
        tolerance_min=deskew.fit_tolerance_min,
        tolerance_multiplier=deskew.fit_tolerance_multiplier,
    )
    fits = [fit for fit in (top_fit, bottom_fit) if fit is not None]
    if not fits:
        return 0.0, {"reason": "not_enough_points", "top_samples": len(top_points), "bottom_samples": len(bottom_points)}

    slopes = [float(fit["slope"]) for fit in fits]
    if len(slopes) == 2 and abs(slopes[0] - slopes[1]) > deskew.slope_delta_max:
        return 0.0, {
            "reason": "top_bottom_disagree",
            "top": top_fit,
            "bottom": bottom_fit,
            "slope_delta": abs(slopes[0] - slopes[1]),
        }
    if any(float(fit["median_residual"]) > max(deskew.residual_min, h * deskew.residual_height_ratio) for fit in fits):
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


def deskew_quality(detail: dict[str, Any], deskew: DeskewParameters) -> float:
    if detail.get("reason"):
        return -1.0
    fits = [detail.get("top"), detail.get("bottom")]
    score = 0.0
    for fit in fits:
        if isinstance(fit, dict):
            score += float(fit["inliers"]) * deskew.quality_inlier_weight
            score -= float(fit["median_residual"])
    return score


def choose_deskew_angle(
    gray: np.ndarray,
    layout: str,
    deskew_fallback: str,
    deskew: DeskewParameters,
    fallback_params: DeskewFallbackEvidenceParameters,
) -> tuple[float, dict[str, Any]]:
    base_angle, base_detail = fit_edge_angle(gray, layout, deskew)
    base_detail["source"] = "base"
    if deskew_fallback == "off":
        return base_angle, base_detail
    if deskew_fallback == "auto" and deskew_quality(base_detail, deskew) >= deskew.auto_quality_ok:
        base_detail["fallback_candidate"] = {"skipped": "auto_base_quality_ok"}
        return base_angle, base_detail
    fallback_gray = make_deskew_fallback_gray(
        gray,
        fallback_params,
    )
    fallback_angle, fallback_detail = fit_edge_angle(fallback_gray, layout, deskew)
    fallback_detail["source"] = "fallback"
    if deskew_quality(fallback_detail, deskew) > deskew_quality(base_detail, deskew) + deskew.fallback_quality_gain:
        fallback_detail["base_candidate"] = base_detail
        return fallback_angle, fallback_detail
    base_detail["fallback_candidate"] = fallback_detail
    return base_angle, base_detail
