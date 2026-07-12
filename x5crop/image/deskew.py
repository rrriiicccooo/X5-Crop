from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

import numpy as np

from ..geometry.layout import VERTICAL, work_gray
from ..utils import bbox_from_mask
from .deskew_parameters import DeskewParameters
from .statistics import ImageMeasurementStatistics


@dataclass(frozen=True)
class LineFitMeasurement:
    slope: float
    inliers: int
    median_residual: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.slope)
            or self.inliers <= 0
            or not math.isfinite(self.median_residual)
            or self.median_residual < 0.0
        ):
            raise ValueError("line fit measurement requires finite positive support")


class DeskewMeasurementOutcome(str, Enum):
    MEASURED = "deskew_angle_measured"
    NO_SCAN_FOOTPRINT = "no_scan_footprint"
    INSUFFICIENT_EDGE_POINTS = "insufficient_edge_points"
    EDGE_FITS_DISAGREE = "edge_fits_disagree"
    HIGH_RESIDUAL = "high_residual"


@dataclass(frozen=True)
class DeskewAngleMeasurement:
    outcome: DeskewMeasurementOutcome
    angle_degrees: float
    top_fit: LineFitMeasurement | None
    bottom_fit: LineFitMeasurement | None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, DeskewMeasurementOutcome):
            raise TypeError("deskew measurement requires a typed outcome")
        if not math.isfinite(self.angle_degrees):
            raise ValueError("deskew angle measurement must be finite")
        fits = (self.top_fit, self.bottom_fit)
        if self.outcome == DeskewMeasurementOutcome.MEASURED:
            if all(fit is None for fit in fits):
                raise ValueError("successful deskew measurement requires an edge fit")
        else:
            if self.angle_degrees != 0.0:
                raise ValueError("failed deskew measurement must have zero angle")
            if self.outcome in {
                DeskewMeasurementOutcome.NO_SCAN_FOOTPRINT,
                DeskewMeasurementOutcome.INSUFFICIENT_EDGE_POINTS,
            } and any(fit is not None for fit in fits):
                raise ValueError("unsupported deskew measurement cannot carry edge fits")
            if (
                self.outcome == DeskewMeasurementOutcome.EDGE_FITS_DISAGREE
                and any(fit is None for fit in fits)
            ):
                raise ValueError("edge disagreement requires both edge fits")
            if (
                self.outcome == DeskewMeasurementOutcome.HIGH_RESIDUAL
                and all(fit is None for fit in fits)
            ):
                raise ValueError("high residual requires an edge fit")


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
        return DeskewAngleMeasurement(
            DeskewMeasurementOutcome.NO_SCAN_FOOTPRINT,
            0.0,
            None,
            None,
        )

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
        return DeskewAngleMeasurement(
            DeskewMeasurementOutcome.INSUFFICIENT_EDGE_POINTS,
            0.0,
            None,
            None,
        )

    slopes = tuple(fit.slope for fit in fits)
    if (
        len(slopes) == 2
        and abs(slopes[0] - slopes[1]) > parameters.slope_delta_max
    ):
        return DeskewAngleMeasurement(
            DeskewMeasurementOutcome.EDGE_FITS_DISAGREE,
            0.0,
            top_fit,
            bottom_fit,
        )
    residual_limit = max(
        parameters.residual_min,
        height * parameters.residual_height_ratio,
    )
    if any(fit.median_residual > residual_limit for fit in fits):
        return DeskewAngleMeasurement(
            DeskewMeasurementOutcome.HIGH_RESIDUAL,
            0.0,
            top_fit,
            bottom_fit,
        )

    slope = float(np.median(slopes))
    angle = math.degrees(math.atan(slope))
    if layout == VERTICAL:
        angle = -angle
    return DeskewAngleMeasurement(
        DeskewMeasurementOutcome.MEASURED,
        angle,
        top_fit,
        bottom_fit,
    )
