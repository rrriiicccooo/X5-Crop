"""Direction measurement for one candidate-independent sequence edge."""

from __future__ import annotations

import math

from ...domain import FiniteInterval
from .measurement_points import TransitionPoint
from .measurement_model import PhotoBoundaryTransition
from .model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
)
from .observation_types import ProfileRun
from .robust_line_fit import fit_transition_line, physical_slope_interval


def sequence_run_direction_measurement(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
    *,
    boundary_axis_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[float, FiniteInterval, FiniteInterval] | None:
    """Return SciPy-robust canonical, fit, and physical direction intervals."""

    values = tuple(
        transitions[str(identity)]
        for identity in run.transition_ids
        if str(identity) in transitions
    )
    traces = [float(item.trace_coordinate_px) for item in values]
    if len(values) < 2 or max(traces) <= min(traces):
        return None
    points = tuple(
        TransitionPoint(
            transition=item,
            trace=float(item.trace_coordinate_px),
            coordinate=float(item.coordinate_px),
        )
        for item in values
    )
    fitted = fit_transition_line(
        points,
        boundary_axis_scale_px_per_mm,
        spec,
    )
    retained = fitted.selected_points
    retained_traces = tuple(item.trace for item in retained)
    if len(retained) < 2 or max(retained_traces) <= min(retained_traces):
        return None
    slope = fitted.slope
    residuals = tuple(float(value) for value in fitted.residuals)
    residual_center = sorted(residuals)[len(residuals) // 2]
    residual_mad = sorted(
        abs(value - residual_center) for value in residuals
    )[len(residuals) // 2]
    numeric = spec.transition_coordinate_sampling_uncertainty_px
    fit_endpoint_error = residual_mad / math.sqrt(len(retained)) + numeric
    maximum_endpoint_error = max(
        abs(residual)
        + point.transition.localization_interval_px.width / 2.0
        for residual, point in zip(residuals, retained, strict=True)
    )
    trace_span = max(retained_traces) - min(retained_traces)
    multiplier = spec.angle_endpoint_uncertainty_multiplier
    fit_slope_allowance = multiplier * fit_endpoint_error / trace_span
    canonical = math.degrees(math.atan(-slope))
    fit = FiniteInterval(
        math.degrees(math.atan(-(slope + fit_slope_allowance))),
        math.degrees(math.atan(-(slope - fit_slope_allowance))),
    )
    physical_slopes = physical_slope_interval(
        retained,
        math.tan(math.radians(spec.maximum_measurable_line_angle_degrees)),
    )
    if physical_slopes is None:
        return None
    # Safety retains both the measured endpoint departure and every slope
    # permitted by the direct localization intervals.  Their hull never
    # creates direction authority; it only preserves measurement uncertainty.
    full_slope_allowance = multiplier * maximum_endpoint_error / trace_span
    measured_full = FiniteInterval(
        math.degrees(math.atan(-(slope + full_slope_allowance))),
        math.degrees(math.atan(-(slope - full_slope_allowance))),
    )
    physical_full = FiniteInterval(
        math.degrees(math.atan(-physical_slopes.maximum)),
        math.degrees(math.atan(-physical_slopes.minimum)),
    )
    full = FiniteInterval(
        min(
            fit.minimum,
            measured_full.minimum,
            physical_full.minimum,
        ),
        max(
            fit.maximum,
            measured_full.maximum,
            physical_full.maximum,
        ),
    )
    return canonical, fit, full
