"""Bounded, role-free outer-edge deskew observation.

This module only measures an optional strip angle.  It does not select a
template placement, authorize output, or turn a failed measurement into a
zero-degree observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

import numpy as np

from ..domain import EvidenceState
from ..geometry.layout import work_gray


_DARK_THRESHOLD = 245
_OUTER_SUPPORT_FRACTION = 0.01
_TRACE_SPACING_PX = 350
_MIN_TRACE_COUNT = 6
_MAX_TRACE_COUNT = 24
_MIN_EDGE_POINT_COUNT = 4
_MAD_INLIER_MULTIPLIER = 3.0
_MIN_INLIER_TOLERANCE_PX = 2.0
_MIN_RESIDUAL_LIMIT_PX = 3.0
_RESIDUAL_SHORT_EXTENT_RATIO = 0.003
_MAX_EDGE_SLOPE_DELTA = 0.006
_MAX_ABSOLUTE_ANGLE_DEGREES = 2.0

# The dark-support pass is source-sized work, but its threshold mask is
# chunked.  Apart from the canonical vertical ``work_gray`` copy, temporary
# image memory is bounded by one chunk (or one source row when wider) plus
# O(width + height) integer counters.  Edge sampling and fitting retain at
# most ``_MAX_TRACE_COUNT`` scalar points per side.
_SUPPORT_MASK_CHUNK_PIXELS = 1 << 20


class DeskewSkipReason(str, Enum):
    EMPTY_SOURCE = "empty_source"
    NO_DARK_SUPPORT = "no_dark_support"
    INSUFFICIENT_EDGE_POINTS = "insufficient_edge_points"
    EDGE_SLOPE_CONFLICT = "edge_slope_conflict"
    EDGE_RESIDUAL_TOO_HIGH = "edge_residual_too_high"
    ANGLE_OUT_OF_RANGE = "angle_out_of_range"
    ROTATION_NOT_NEEDED = "rotation_not_needed"


@dataclass(frozen=True)
class DeskewEdgeFit:
    """One outer-edge line fit in canonical work coordinates."""

    slope: float
    angle_degrees: float
    sample_count: int
    inlier_count: int
    median_residual_px: float

    def __post_init__(self) -> None:
        expected_angle = math.degrees(math.atan(self.slope))
        if (
            not math.isfinite(self.slope)
            or not math.isfinite(self.angle_degrees)
            or not math.isclose(
                self.angle_degrees,
                expected_angle,
                rel_tol=0.0,
                abs_tol=1.0e-9,
            )
            or type(self.sample_count) is not int
            or type(self.inlier_count) is not int
            or self.sample_count < _MIN_EDGE_POINT_COUNT
            or not (
                _MIN_EDGE_POINT_COUNT
                <= self.inlier_count
                <= self.sample_count
            )
            or not math.isfinite(self.median_residual_px)
            or self.median_residual_px < 0.0
        ):
            raise ValueError("deskew edge fit is invalid")


@dataclass(frozen=True)
class LightweightDeskewObservation:
    """One optional role-free deskew measurement.

    A supported observation always carries two compatible edge fits and the
    measured angle.  Every skipped observation carries a typed reason and no
    angle; available diagnostic fits may remain attached.
    """

    state: EvidenceState
    angle_degrees: float | None
    top_fit: DeskewEdgeFit | None
    bottom_fit: DeskewEdgeFit | None
    sample_trace_count: int
    skip_reason: DeskewSkipReason | None

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise TypeError("deskew observation requires a typed evidence state")
        if (
            type(self.sample_trace_count) is not int
            or not 0 <= self.sample_trace_count <= _MAX_TRACE_COUNT
            or (
                self.top_fit is not None
                and not isinstance(self.top_fit, DeskewEdgeFit)
            )
            or (
                self.bottom_fit is not None
                and not isinstance(self.bottom_fit, DeskewEdgeFit)
            )
            or any(
                fit.sample_count > self.sample_trace_count
                for fit in (self.top_fit, self.bottom_fit)
                if fit is not None
            )
        ):
            raise ValueError("deskew observation work accounting is invalid")

        supported = self.state == EvidenceState.SUPPORTED
        if self.state not in {EvidenceState.SUPPORTED, EvidenceState.UNAVAILABLE}:
            raise ValueError("deskew observation uses an unsupported evidence state")
        if supported:
            if (
                self.angle_degrees is None
                or not math.isfinite(self.angle_degrees)
                or abs(self.angle_degrees) > _MAX_ABSOLUTE_ANGLE_DEGREES
                or self.top_fit is None
                or self.bottom_fit is None
                or self.skip_reason is not None
                or self.sample_trace_count < _MIN_EDGE_POINT_COUNT
                or abs(self.top_fit.slope - self.bottom_fit.slope)
                > _MAX_EDGE_SLOPE_DELTA
            ):
                raise ValueError("supported deskew observation is incomplete")
            canonical_angle = math.degrees(
                math.atan(
                    float(np.median((self.top_fit.slope, self.bottom_fit.slope)))
                )
            )
            if not math.isclose(
                abs(self.angle_degrees),
                abs(canonical_angle),
                rel_tol=0.0,
                abs_tol=1.0e-9,
            ):
                raise ValueError("deskew observation angle disagrees with its fits")
            return

        if (
            self.angle_degrees is not None
            or not isinstance(self.skip_reason, DeskewSkipReason)
            or self.skip_reason == DeskewSkipReason.ROTATION_NOT_NEEDED
        ):
            raise ValueError("skipped deskew observation is inconsistent")


def _unavailable(
    reason: DeskewSkipReason,
    *,
    sample_trace_count: int = 0,
    top_fit: DeskewEdgeFit | None = None,
    bottom_fit: DeskewEdgeFit | None = None,
) -> LightweightDeskewObservation:
    return LightweightDeskewObservation(
        state=EvidenceState.UNAVAILABLE,
        angle_degrees=None,
        top_fit=top_fit,
        bottom_fit=bottom_fit,
        sample_trace_count=sample_trace_count,
        skip_reason=reason,
    )


def _outer_dark_support(
    work: np.ndarray,
) -> tuple[int, int, int, int] | None:
    height, width = work.shape
    row_dark_counts = np.empty(height, dtype=np.int64)
    column_dark_counts = np.zeros(width, dtype=np.int64)
    rows_per_chunk = max(
        1,
        min(height, _SUPPORT_MASK_CHUNK_PIXELS // max(1, width)),
    )
    for start in range(0, height, rows_per_chunk):
        stop = min(height, start + rows_per_chunk)
        dark = work[start:stop, :] < _DARK_THRESHOLD
        row_dark_counts[start:stop] = np.count_nonzero(dark, axis=1)
        column_dark_counts += np.count_nonzero(dark, axis=0)

    minimum_row_dark = max(1, math.ceil(width * _OUTER_SUPPORT_FRACTION))
    minimum_column_dark = max(
        1,
        math.ceil(height * _OUTER_SUPPORT_FRACTION),
    )
    supported_rows = np.flatnonzero(row_dark_counts >= minimum_row_dark)
    supported_columns = np.flatnonzero(
        column_dark_counts >= minimum_column_dark
    )
    if supported_rows.size == 0 or supported_columns.size == 0:
        return None
    support_top = int(supported_rows[0])
    support_bottom = int(supported_rows[-1]) + 1
    # If darkness occupies the complete short axis, neither external strip
    # edge is independently visible.  Treating the raster borders as two
    # perfect zero-degree edges would fabricate a deskew observation for an
    # all-black or otherwise blank image.
    if support_top == 0 and support_bottom == height:
        return None
    return (
        int(supported_columns[0]),
        support_top,
        int(supported_columns[-1]) + 1,
        support_bottom,
    )


def _line_parameters(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[float, float] | None:
    x_center = x - float(np.mean(x))
    denominator = float(np.dot(x_center, x_center))
    if denominator <= np.finfo(np.float64).eps:
        return None
    slope = float(np.dot(x_center, y - float(np.mean(y))) / denominator)
    intercept = float(np.mean(y) - slope * np.mean(x))
    if not math.isfinite(slope) or not math.isfinite(intercept):
        return None
    return slope, intercept


def _fit_edge(points: list[tuple[float, float]]) -> DeskewEdgeFit | None:
    sample_count = len(points)
    if sample_count < _MIN_EDGE_POINT_COUNT:
        return None
    x = np.fromiter((point[0] for point in points), dtype=np.float64)
    y = np.fromiter((point[1] for point in points), dtype=np.float64)
    initial = _line_parameters(x, y)
    if initial is None:
        return None
    initial_slope, initial_intercept = initial
    signed_residuals = y - (initial_slope * x + initial_intercept)
    residual_center = float(np.median(signed_residuals))
    residual_mad = float(
        np.median(np.abs(signed_residuals - residual_center))
    )
    tolerance = max(
        _MIN_INLIER_TOLERANCE_PX,
        _MAD_INLIER_MULTIPLIER * residual_mad,
    )
    inliers = np.abs(signed_residuals - residual_center) <= tolerance
    inlier_count = int(np.count_nonzero(inliers))
    if inlier_count < _MIN_EDGE_POINT_COUNT:
        return None
    refined = _line_parameters(x[inliers], y[inliers])
    if refined is None:
        return None
    slope, intercept = refined
    median_residual = float(
        np.median(np.abs(y[inliers] - (slope * x[inliers] + intercept)))
    )
    return DeskewEdgeFit(
        slope=slope,
        angle_degrees=math.degrees(math.atan(slope)),
        sample_count=sample_count,
        inlier_count=inlier_count,
        median_residual_px=median_residual,
    )


def observe_lightweight_deskew(
    source_gray: np.ndarray,
    layout: str,
) -> LightweightDeskewObservation:
    """Measure parallel external strip edges with bounded sparse traces."""

    if not isinstance(source_gray, np.ndarray):
        raise TypeError("deskew observation requires a numpy array")
    if source_gray.ndim != 2 or source_gray.dtype != np.uint8:
        raise ValueError("deskew observation requires two-dimensional uint8 gray")
    work = work_gray(source_gray, layout)
    short_extent, long_extent = work.shape
    if short_extent == 0 or long_extent == 0:
        return _unavailable(DeskewSkipReason.EMPTY_SOURCE)

    support = _outer_dark_support(work)
    if support is None:
        return _unavailable(DeskewSkipReason.NO_DARK_SUPPORT)
    support_left, support_top, support_right, support_bottom = support
    support_width = support_right - support_left
    requested_trace_count = min(
        _MAX_TRACE_COUNT,
        max(_MIN_TRACE_COUNT, support_width // _TRACE_SPACING_PX),
    )
    traces = np.unique(
        np.linspace(
            support_left,
            support_right - 1,
            num=requested_trace_count,
        ).astype(np.int64)
    )
    sample_trace_count = int(traces.size)
    support_midpoint = (support_top + support_bottom - 1) / 2.0
    top_points: list[tuple[float, float]] = []
    bottom_points: list[tuple[float, float]] = []
    for trace in traces:
        dark_rows = np.flatnonzero(work[:, int(trace)] < _DARK_THRESHOLD)
        if dark_rows.size == 0:
            continue
        top = int(dark_rows[0])
        bottom = int(dark_rows[-1])
        if top <= support_midpoint:
            top_points.append((float(trace), float(top)))
        if bottom >= support_midpoint:
            bottom_points.append((float(trace), float(bottom)))

    top_fit = _fit_edge(top_points)
    bottom_fit = _fit_edge(bottom_points)
    if top_fit is None or bottom_fit is None:
        return _unavailable(
            DeskewSkipReason.INSUFFICIENT_EDGE_POINTS,
            sample_trace_count=sample_trace_count,
            top_fit=top_fit,
            bottom_fit=bottom_fit,
        )
    if abs(top_fit.slope - bottom_fit.slope) > _MAX_EDGE_SLOPE_DELTA:
        return _unavailable(
            DeskewSkipReason.EDGE_SLOPE_CONFLICT,
            sample_trace_count=sample_trace_count,
            top_fit=top_fit,
            bottom_fit=bottom_fit,
        )
    residual_limit = max(
        _MIN_RESIDUAL_LIMIT_PX,
        short_extent * _RESIDUAL_SHORT_EXTENT_RATIO,
    )
    if (
        top_fit.median_residual_px > residual_limit
        or bottom_fit.median_residual_px > residual_limit
    ):
        return _unavailable(
            DeskewSkipReason.EDGE_RESIDUAL_TOO_HIGH,
            sample_trace_count=sample_trace_count,
            top_fit=top_fit,
            bottom_fit=bottom_fit,
        )

    slope = float(np.median((top_fit.slope, bottom_fit.slope)))
    canonical_angle = math.degrees(math.atan(slope))
    angle = canonical_angle if layout == "horizontal" else -canonical_angle
    if abs(angle) > _MAX_ABSOLUTE_ANGLE_DEGREES:
        return _unavailable(
            DeskewSkipReason.ANGLE_OUT_OF_RANGE,
            sample_trace_count=sample_trace_count,
            top_fit=top_fit,
            bottom_fit=bottom_fit,
        )
    return LightweightDeskewObservation(
        state=EvidenceState.SUPPORTED,
        angle_degrees=angle,
        top_fit=top_fit,
        bottom_fit=bottom_fit,
        sample_trace_count=sample_trace_count,
        skip_reason=None,
    )
