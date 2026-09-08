"""SciPy robust fitting for one already-bound transition family."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy.optimize import least_squares

from ...domain import FiniteInterval
from ...geometry.convex import convex_hull
from .measurement_points import TransitionPoint
from .line_observations import PhysicalLineRegion, RobustLineFitReceipt
from .model import PhotoBoundaryMeasurementSpec


@dataclass(frozen=True)
class TransitionLineFit:
    slope: float
    intercept: float
    residuals: np.ndarray
    selected_points: tuple[TransitionPoint, ...]
    receipt: RobustLineFitReceipt


def _clip_line_region(
    vertices: tuple[tuple[float, float], ...],
    position_coefficient: float,
    slope_coefficient: float,
    limit: float,
) -> tuple[tuple[float, float], ...]:
    """Intersect a bounded line-parameter region with one closed half-plane."""

    if not vertices:
        return ()
    result: list[tuple[float, float]] = []

    def append(point: tuple[float, float]) -> None:
        if not result or point != result[-1]:
            result.append(point)

    def distance(point: tuple[float, float]) -> float:
        value = (
            position_coefficient * point[0]
            + slope_coefficient * point[1]
            - limit
        )
        # The existing coordinate contract admits 1e-9 px arithmetic error.
        # Keep a closed-set vertex when cancellation lands on its boundary.
        return 0.0 if abs(value) <= 1.0e-9 else value

    previous = vertices[-1]
    previous_value = distance(previous)
    for current in vertices:
        current_value = distance(current)
        if (previous_value <= 0.0) != (current_value <= 0.0):
            fraction = previous_value / (previous_value - current_value)
            append((
                previous[0] + fraction * (current[0] - previous[0]),
                previous[1] + fraction * (current[1] - previous[1]),
            ))
        if current_value <= 0.0:
            append(current)
        previous = current
        previous_value = current_value
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return tuple(result)


def physical_line_region(
    trace_intervals: tuple[tuple[float, FiniteInterval], ...],
    maximum_slope: float,
    reference_trace_px: float,
) -> PhysicalLineRegion | None:
    """Retain all raw-physical straight-line states without another fit or LP.

    The first trace and the existing slope cap provide a bounded superset.
    Each of the 2N closed half-planes adds at most one vertex: O(N**2)
    work and O(N) storage, including valid point and segment degeneracies.
    Connection allowance does not make an infeasible physical family close.
    """

    if (
        not trace_intervals
        or not math.isfinite(maximum_slope)
        or maximum_slope <= 0.0
        or not math.isfinite(reference_trace_px)
        or any(not math.isfinite(trace) for trace, _ in trace_intervals)
    ):
        raise ValueError("physical line inputs are invalid")
    first_trace, interval = trace_intervals[0]
    allowance = maximum_slope * abs(first_trace - reference_trace_px)
    minimum = interval.minimum - allowance
    maximum = interval.maximum + allowance
    vertices = (
        (minimum, -maximum_slope),
        (maximum, -maximum_slope),
        (maximum, maximum_slope),
        (minimum, maximum_slope),
    )
    for trace, interval in trace_intervals:
        distance = trace - reference_trace_px
        vertices = _clip_line_region(vertices, 1.0, distance, interval.maximum)
        vertices = _clip_line_region(vertices, -1.0, -distance, -interval.minimum)
        if not vertices:
            return None
    return PhysicalLineRegion(reference_trace_px, vertices)


def physical_line_region_at_positions(
    region: PhysicalLineRegion,
    offset: FiniteInterval,
    positions: FiniteInterval,
) -> PhysicalLineRegion | None:
    """Project a bounded position offset, then restrict its reachable reference.

    The offset is a protective Minkowski envelope, not an independent width
    measurement. Clipping retains position/slope correlation and legal point
    or segment degeneracies without an additional LP.
    """
    if offset.width == 0.0:
        vertices = tuple((p + offset.minimum, m) for p, m in region.vertices)
    elif len({m for _, m in region.vertices}) == 1:
        slope = region.vertices[0][1]
        vertices = ((min(p for p, _ in region.vertices) + offset.minimum, slope),
                    (max(p for p, _ in region.vertices) + offset.maximum, slope))
    else:
        vertices = convex_hull(tuple(
            (p + value, m) for p, m in region.vertices
            for value in (offset.minimum, offset.maximum)
        ))
    vertices = _clip_line_region(vertices, 1.0, 0.0, positions.maximum)
    vertices = _clip_line_region(vertices, -1.0, 0.0, -positions.minimum)
    return PhysicalLineRegion(region.reference_trace_px, vertices) if vertices else None


def physical_slope_interval(
    points: tuple[TransitionPoint, ...],
    maximum_slope: float,
) -> FiniteInterval | None:
    """Return every straight-line slope allowed by measured intervals."""

    if not points or not math.isfinite(maximum_slope) or maximum_slope <= 0.0:
        raise ValueError("physical slope inputs are invalid")
    minimum = -maximum_slope
    maximum = maximum_slope
    ordered = tuple(sorted(points, key=lambda item: item.trace))
    for index, left in enumerate(ordered):
        left_interval = left.transition.physical_position_interval_px
        for right in ordered[index + 1 :]:
            delta = right.trace - left.trace
            if delta <= 0.0:
                continue
            right_interval = right.transition.physical_position_interval_px
            minimum = max(
                minimum,
                (right_interval.minimum - left_interval.maximum) / delta,
            )
            maximum = min(
                maximum,
                (right_interval.maximum - left_interval.minimum) / delta,
            )
            if minimum > maximum:
                return None
    return FiniteInterval(minimum, maximum)


@lru_cache(maxsize=1024)
def fit_transition_line(
    points: tuple[TransitionPoint, ...],
    boundary_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> TransitionLineFit:
    """Fit one exact candidate-independent family with bounded Huber loss."""

    traces = np.asarray([point.trace for point in points], dtype=np.float64)
    coordinates = np.asarray(
        [point.coordinate for point in points], dtype=np.float64
    )
    trace_reference = float(np.median(traces))
    centered_traces = traces - trace_reference
    design = np.column_stack((centered_traces, np.ones_like(traces)))
    initial, *_unused = np.linalg.lstsq(design, coordinates, rcond=None)
    maximum_slope = math.tan(
        math.radians(spec.maximum_measurable_line_angle_degrees)
    )
    initial[0] = min(maximum_slope, max(-maximum_slope, initial[0]))
    loss_scale = spec.robust_loss_minimum_scale_mm * boundary_scale_px_per_mm
    result = least_squares(
        lambda coefficients: design @ coefficients - coordinates,
        initial,
        jac=lambda _coefficients: design,
        bounds=(
            np.asarray((-maximum_slope, -np.inf), dtype=np.float64),
            np.asarray((maximum_slope, np.inf), dtype=np.float64),
        ),
        method="trf",
        ftol=spec.robust_fit_tolerance,
        xtol=spec.robust_fit_tolerance,
        gtol=spec.robust_fit_tolerance,
        loss="huber",
        f_scale=loss_scale,
        max_nfev=spec.robust_fit_maximum_evaluations,
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise ValueError("robust line fit did not converge")
    slope = float(result.x[0])
    intercept = float(result.x[1] - slope * trace_reference)
    residuals = coordinates - (slope * traces + intercept)
    residuals.flags.writeable = False

    selected: list[TransitionPoint] = []
    for trace in sorted(set(point.trace for point in points)):
        indices = np.flatnonzero(traces == trace)
        best = min(
            indices,
            key=lambda index: (
                abs(float(residuals[index])),
                -(
                    points[int(index)].transition.gradient_z
                    + max(
                        points[int(index)].transition.tone_z,
                        points[int(index)].transition.texture_z,
                    )
                ),
                str(points[int(index)].transition.transition_id),
            ),
        )
        selected.append(points[int(best)])
    if len(selected) != len(points):
        return fit_transition_line(
            tuple(selected), boundary_scale_px_per_mm, spec
        )
    return TransitionLineFit(
        slope=slope,
        intercept=intercept,
        residuals=residuals,
        selected_points=tuple(selected),
        receipt=RobustLineFitReceipt(
            method="scipy_least_squares_huber",
            converged=True,
            status=int(result.status),
            evaluation_count=int(result.nfev),
            cost=float(result.cost),
            optimality=float(result.optimality),
        ),
    )
