"""Direction measurement for one candidate-independent sequence edge."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ...domain import FiniteInterval, ObservationId
from .measurement_points import TransitionPoint
from .measurement_model import PhotoBoundaryTransition
from .model import (
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
    independent_spatial_support_count,
)
from .observation_types import ProfileRun
from .robust_line_fit import (
    TransitionLineFit,
    fit_transition_line,
    physical_slope_interval,
)
from .trace_support import (
    continuous_trace_support_fraction,
    source_spanning_continuous_trace_support,
)


def _retained_role_relation_is_unanimous(
    run: ProfileRun,
    points: tuple[TransitionPoint, ...],
) -> bool:
    return any(
        all(
            (
                point.transition.left_texture_mean
                < point.transition.right_texture_mean
            )
            if role == BoundaryRole.START
            else (
                point.transition.right_texture_mean
                < point.transition.left_texture_mean
            )
            for point in points
        )
        for role in run.qualified_anchor_roles
        if role in {BoundaryRole.START, BoundaryRole.END}
    )


@dataclass(frozen=True)
class SequenceRunLineMeasurement:
    """One locally refined sequence edge at a declared reference trace.

    The tracked run interval is only a coarse discovery corridor.  This
    record is the candidate-independent local refinement of that same raw
    transition family and is the only position uncertainty allowed to reach
    template fitting and selected-output safety.
    """

    reference_trace_px: float
    canonical_position_px: float
    fit_position_interval_px: FiniteInterval
    full_position_interval_px: FiniteInterval
    canonical_direction_degrees: float | None
    fit_direction_interval_degrees: FiniteInterval | None
    full_direction_interval_degrees: FiniteInterval | None
    transition_ids: tuple[ObservationId, ...]
    trace_coordinates_px: tuple[int, ...]
    support_fraction: float
    continuous_support_fraction: float
    fit_residual_px: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.reference_trace_px)
            or not math.isfinite(self.canonical_position_px)
            or not self.fit_position_interval_px.contains(
                self.canonical_position_px,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.minimum,
                epsilon=1.0e-9,
            )
            or not self.full_position_interval_px.contains(
                self.fit_position_interval_px.maximum,
                epsilon=1.0e-9,
            )
            or (
                (self.canonical_direction_degrees is None)
                != (self.fit_direction_interval_degrees is None)
            )
            or (
                (self.canonical_direction_degrees is None)
                != (self.full_direction_interval_degrees is None)
            )
            or (
                self.canonical_direction_degrees is not None
                and (
                    not math.isfinite(self.canonical_direction_degrees)
                    or not self.fit_direction_interval_degrees.contains(
                        self.canonical_direction_degrees,
                        epsilon=1.0e-9,
                    )
                    or not self.full_direction_interval_degrees.contains(
                        self.fit_direction_interval_degrees.minimum,
                        epsilon=1.0e-9,
                    )
                    or not self.full_direction_interval_degrees.contains(
                        self.fit_direction_interval_degrees.maximum,
                        epsilon=1.0e-9,
                    )
                )
            )
            or not self.transition_ids
            or len(set(self.transition_ids)) != len(self.transition_ids)
            or tuple(sorted(set(self.trace_coordinates_px)))
            != self.trace_coordinates_px
            or len(self.trace_coordinates_px) != len(self.transition_ids)
            or not 0.0 < self.support_fraction <= 1.0
            or not 0.0 <= self.continuous_support_fraction <= 1.0
            or not math.isfinite(self.fit_residual_px)
            or self.fit_residual_px < 0.0
        ):
            raise ValueError("sequence run line measurement is invalid")


def _sequence_run_fit(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
    *,
    queried_trace_coordinates_px: tuple[int, ...],
    boundary_axis_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[TransitionLineFit, FiniteInterval | None, bool] | None:
    values = tuple(
        transitions[str(identity)]
        for identity in run.transition_ids
        if str(identity) in transitions
    )
    traces = tuple(float(item.trace_coordinate_px) for item in values)
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
    maximum_slope = math.tan(
        math.radians(spec.maximum_measurable_line_angle_degrees)
    )
    physical = physical_slope_interval(retained, maximum_slope)
    if physical is not None:
        return fitted, physical, False
    if not run.qualified_anchor_roles or not run.pair_qualified:
        return None

    # A role-qualified physical track may bend slightly or contain one local
    # transition that does not belong to its dominant edge.  Reuse the same
    # named physical-distance allowance as role-bound boundary fitting, then
    # require the retained direct pixels to preserve independent spatial
    # support.  Placement geometry never participates in this recovery.
    inlier_threshold = (
        spec.inlier_minimum_threshold_mm * boundary_axis_scale_px_per_mm
    )
    predicted = np.asarray(
        [fitted.slope * point.trace + fitted.intercept for point in retained],
        dtype=np.float64,
    )
    interval_distance = np.asarray(
        [
            max(
                point.transition.physical_position_interval_px.minimum - value,
                0.0,
                value - point.transition.physical_position_interval_px.maximum,
            )
            for point, value in zip(retained, predicted, strict=True)
        ],
        dtype=np.float64,
    )
    inliers = tuple(
        point
        for point, keep in zip(
            retained,
            interval_distance <= inlier_threshold,
            strict=True,
        )
        if bool(keep)
    )
    inlier_traces = tuple(sorted({point.trace for point in inliers}))
    if (
        len(inlier_traces) < 2
        or independent_spatial_support_count(
            queried_trace_coordinates_px,
            inlier_traces,
        )
        < MINIMUM_INDEPENDENT_SUPPORT_REGIONS
        or not source_spanning_continuous_trace_support(
            queried_trace_coordinates_px,
            inlier_traces,
            spec=spec,
        )
    ):
        return None
    fitted = fit_transition_line(
        inliers,
        boundary_axis_scale_px_per_mm,
        spec,
    )
    retained = fitted.selected_points
    retained_traces = tuple(item.trace for item in retained)
    if (
        len(retained) < 2
        or max(retained_traces) <= min(retained_traces)
        # Once straight physical closure has failed, a local position may keep
        # its role only when every retained direct trace agrees on which side
        # is background.  A weak majority is insufficient to turn a textured
        # picture line into a template anchor.
        or not _retained_role_relation_is_unanimous(run, retained)
    ):
        return None
    return fitted, physical_slope_interval(retained, maximum_slope), True


def _direction_from_fit(
    fitted: TransitionLineFit,
    physical_slopes: FiniteInterval | None,
    *,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[float, FiniteInterval, FiniteInterval]:
    retained = fitted.selected_points
    retained_traces = tuple(item.trace for item in retained)
    slope = fitted.slope
    residuals = tuple(float(value) for value in fitted.residuals)
    residual_center = float(np.median(residuals))
    residual_mad = float(
        np.median(np.abs(np.asarray(residuals) - residual_center))
    )
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
    full_slope_allowance = multiplier * maximum_endpoint_error / trace_span
    measured_full = FiniteInterval(
        math.degrees(math.atan(-(slope + full_slope_allowance))),
        math.degrees(math.atan(-(slope - full_slope_allowance))),
    )
    full = FiniteInterval(
        min(fit.minimum, measured_full.minimum),
        max(fit.maximum, measured_full.maximum),
    )
    if physical_slopes is not None:
        physical_full = FiniteInterval(
            math.degrees(math.atan(-physical_slopes.maximum)),
            math.degrees(math.atan(-physical_slopes.minimum)),
        )
        full = FiniteInterval(
            min(full.minimum, physical_full.minimum),
            max(full.maximum, physical_full.maximum),
        )
    return canonical, fit, full


def sequence_run_line_measurement(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
    *,
    reference_trace_px: float,
    queried_trace_coordinates_px: tuple[int, ...],
    boundary_axis_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> SequenceRunLineMeasurement | None:
    """Refine one already-tracked edge without another pixel query."""

    if not math.isfinite(reference_trace_px):
        raise ValueError("sequence line reference trace must be finite")
    measured = _sequence_run_fit(
        run,
        transitions,
        queried_trace_coordinates_px=queried_trace_coordinates_px,
        boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        spec=spec,
    )
    if measured is None:
        return None
    fitted, physical_slopes, residual_recovered = measured
    retained = fitted.selected_points
    retained_traces = tuple(item.trace for item in retained)
    if len(retained) < 2 or max(retained_traces) <= min(retained_traces):
        return None
    residuals = tuple(float(value) for value in fitted.residuals)
    residual_center = float(np.median(residuals))
    residual_mad = float(
        np.median(np.abs(np.asarray(residuals) - residual_center))
    )
    numeric = spec.transition_coordinate_sampling_uncertainty_px
    fit_uncertainty = residual_mad / math.sqrt(len(retained)) + numeric
    full_uncertainty = max(
        fit_uncertainty,
        max(
            abs(residual)
            + point.transition.localization_interval_px.width / 2.0
            for residual, point in zip(residuals, retained, strict=True)
        )
        + spec.line_connection_allowance_px(
            boundary_axis_scale_px_per_mm
        ),
    )
    canonical_position = (
        fitted.slope * reference_trace_px + fitted.intercept
    )
    if residual_recovered:
        canonical_direction = None
        fit_direction = None
        full_direction = None
    else:
        canonical_direction, fit_direction, full_direction = _direction_from_fit(
            fitted,
            physical_slopes,
            spec=spec,
        )
    selected_traces = tuple(
        int(point.transition.trace_coordinate_px) for point in retained
    )
    return SequenceRunLineMeasurement(
        reference_trace_px=reference_trace_px,
        canonical_position_px=canonical_position,
        fit_position_interval_px=FiniteInterval(
            canonical_position - fit_uncertainty,
            canonical_position + fit_uncertainty,
        ),
        full_position_interval_px=FiniteInterval(
            canonical_position - full_uncertainty,
            canonical_position + full_uncertainty,
        ),
        canonical_direction_degrees=canonical_direction,
        fit_direction_interval_degrees=fit_direction,
        full_direction_interval_degrees=full_direction,
        transition_ids=tuple(
            point.transition.transition_id for point in retained
        ),
        trace_coordinates_px=selected_traces,
        support_fraction=(
            len(selected_traces) / len(queried_trace_coordinates_px)
        ),
        continuous_support_fraction=continuous_trace_support_fraction(
            queried_trace_coordinates_px,
            selected_traces,
            spec=spec,
        ),
        fit_residual_px=run.fit_residual_px,
    )


def sequence_run_direction_measurement(
    run: ProfileRun,
    transitions: dict[str, PhotoBoundaryTransition],
    *,
    queried_trace_coordinates_px: tuple[int, ...],
    boundary_axis_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[float, FiniteInterval, FiniteInterval] | None:
    """Return SciPy-robust canonical, fit, and physical direction intervals."""

    measured = _sequence_run_fit(
        run,
        transitions,
        queried_trace_coordinates_px=queried_trace_coordinates_px,
        boundary_axis_scale_px_per_mm=boundary_axis_scale_px_per_mm,
        spec=spec,
    )
    if measured is None:
        return None
    if measured[2]:
        return None
    return _direction_from_fit(measured[0], measured[1], spec=spec)
