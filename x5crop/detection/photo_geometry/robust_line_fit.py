"""SciPy robust fitting for one already-bound transition family."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy.optimize import least_squares

from ...domain import FiniteInterval
from .measurement_points import TransitionPoint
from .line_observations import RobustLineFitReceipt
from .model import PhotoBoundaryMeasurementSpec


@dataclass(frozen=True)
class TransitionLineFit:
    slope: float
    intercept: float
    residuals: np.ndarray
    selected_points: tuple[TransitionPoint, ...]
    receipt: RobustLineFitReceipt


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
