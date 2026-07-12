from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..geometry.layout import work_gray
from ..utils import bbox_from_mask
from .deskew_parameters import DeskewParameters
from .statistics import ImageMeasurementStatistics


@dataclass(frozen=True)
class LineFitMeasurement:
    slope: float
    inliers: int
    median_residual: float


@dataclass(frozen=True)
class DeskewAngleMeasurement:
    angle_degrees: float
    reason: str | None
    top_fit: LineFitMeasurement | None
    bottom_fit: LineFitMeasurement | None


def _fit_line(
    points: list[tuple[float, float]],
    *,
    min_points: int,
    tolerance_min: float,
    tolerance_multiplier: float,
) -> LineFitMeasurement | None:
    if len(points) < min_points:
        return None
    x = np.array([point[0] for point in points], dtype=np.float64)
    y = np.array([point[1] for point in points], dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = np.abs(y - (slope * x + intercept))
    median_residual = float(np.median(residuals)) if residuals.size else 0.0
    tolerance = max(tolerance_min, median_residual * tolerance_multiplier)
    inliers = residuals <= tolerance
    inlier_count = int(inliers.sum())
    if min_points <= inlier_count < len(points):
        slope, intercept = np.polyfit(x[inliers], y[inliers], 1)
        residuals = np.abs(y[inliers] - (slope * x[inliers] + intercept))
        median_residual = (
            float(np.median(residuals)) if residuals.size else 0.0
        )
    return LineFitMeasurement(
        slope=float(slope),
        inliers=inlier_count,
        median_residual=median_residual,
    )


def measure_deskew_angle(
    gray: np.ndarray,
    layout: str,
    parameters: DeskewParameters,
    statistics: ImageMeasurementStatistics,
) -> DeskewAngleMeasurement:
    work = work_gray(gray, layout)
    height = work.shape[0]
    mask = work < float(statistics.intensity_high)
    footprint = bbox_from_mask(
        mask,
        parameters.footprint_min_fraction,
        parameters.footprint_min_fraction,
    )
    if footprint is None or footprint.width < parameters.min_footprint_width:
        return DeskewAngleMeasurement(0.0, "no_scan_footprint", None, None)

    xs = np.linspace(
        footprint.left,
        footprint.right - 1,
        num=min(
            parameters.max_samples,
            max(
                parameters.min_samples,
                footprint.width // parameters.sample_width_px,
            ),
        ),
    ).astype(int)
    top_points: list[tuple[float, float]] = []
    bottom_points: list[tuple[float, float]] = []
    for x in xs:
        column = mask[:, x]
        ys = np.flatnonzero(column)
        if ys.size < max(
            parameters.min_col_content,
            height * parameters.min_col_content_ratio,
        ):
            continue
        top_points.append((float(x), float(ys[0])))
        bottom_points.append((float(x), float(ys[-1])))

    top_fit = _fit_line(
        top_points,
        min_points=parameters.fit_min_points,
        tolerance_min=parameters.fit_tolerance_min,
        tolerance_multiplier=parameters.fit_tolerance_multiplier,
    )
    bottom_fit = _fit_line(
        bottom_points,
        min_points=parameters.fit_min_points,
        tolerance_min=parameters.fit_tolerance_min,
        tolerance_multiplier=parameters.fit_tolerance_multiplier,
    )
    fits = tuple(fit for fit in (top_fit, bottom_fit) if fit is not None)
    if not fits:
        return DeskewAngleMeasurement(0.0, "not_enough_points", None, None)

    slopes = tuple(fit.slope for fit in fits)
    if (
        len(slopes) == 2
        and abs(slopes[0] - slopes[1]) > parameters.slope_delta_max
    ):
        return DeskewAngleMeasurement(
            0.0,
            "top_bottom_disagree",
            top_fit,
            bottom_fit,
        )
    residual_limit = max(
        parameters.residual_min,
        height * parameters.residual_height_ratio,
    )
    if any(fit.median_residual > residual_limit for fit in fits):
        return DeskewAngleMeasurement(
            0.0,
            "high_residual",
            top_fit,
            bottom_fit,
        )

    slope = float(np.median(slopes))
    angle = math.degrees(math.atan(slope))
    if layout == "vertical":
        angle = -angle
    return DeskewAngleMeasurement(angle, None, top_fit, bottom_fit)


def deskew_measurement_quality(
    measurement: DeskewAngleMeasurement,
    parameters: DeskewParameters,
) -> float:
    if measurement.reason is not None:
        return -1.0
    return sum(
        fit.inliers * parameters.quality_inlier_weight
        - fit.median_residual
        for fit in (measurement.top_fit, measurement.bottom_fit)
        if fit is not None
    )
