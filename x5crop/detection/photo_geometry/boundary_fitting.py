"""Robust format-role boundary fitting from one tracked observation family."""

from __future__ import annotations

import math

import numpy as np

from ...domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval
from .measurement_points import TransitionPoint
from .model import (
    BoundaryAxis,
    BoundaryRole,
    MINIMUM_INDEPENDENT_SUPPORT_REGIONS,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    SPATIAL_SUPPORT_REGION_COUNT,
    PhotoBoundaryMeasurementSpec,
    independent_spatial_support_count,
)
from .measurement_model import PhotoBoundaryMeasurementSet
from .line_observations import PhotoBoundaryObservation, SourceCoordinateLine
from .robust_line_fit import fit_transition_line, physical_slope_interval
from .trace_support import (
    PIXEL_CENTER_HALF_EXTENT_PX,
    continuous_trace_support_fraction,
    source_spanning_continuous_trace_support,
)
from .physical_identity import physical_observation_id


def _source_line(
    boundary_axis: BoundaryAxis,
    source_axis_long: BoundaryAxis,
    slope: float,
    intercept: float,
    support: FiniteInterval,
) -> SourceCoordinateLine:
    norm = math.hypot(1.0, slope)
    if boundary_axis == BoundaryAxis.X:
        return SourceCoordinateLine(
            normal_x=1.0 / norm,
            normal_y=-slope / norm,
            offset_px=intercept / norm,
            support_projection_px=support,
            source_axis_long=source_axis_long,
        )
    return SourceCoordinateLine(
        normal_x=-slope / norm,
        normal_y=1.0 / norm,
        offset_px=intercept / norm,
        support_projection_px=support,
        source_axis_long=source_axis_long,
    )


def _canonical_rotation_degrees(
    source_axis_long: BoundaryAxis,
    slope: float,
) -> float:
    """Return the rotation-equivalent strip angle in source coordinates."""

    if source_axis_long not in {BoundaryAxis.X, BoundaryAxis.Y}:
        raise ValueError("source long axis is invalid")
    return math.degrees(math.atan(slope))


def fit_format_bound_boundary_observation(
    measurement_set: PhotoBoundaryMeasurementSet,
    *,
    transition_ids: tuple[ObservationId, ...],
    role: BoundaryRole,
    source_axis_long: BoundaryAxis,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    support_interval_px: FiniteInterval | None = None,
    minimum_independent_support_regions: int = (
        MINIMUM_INDEPENDENT_SUPPORT_REGIONS
    ),
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> PhotoBoundaryObservation | None:
    """Fit one robust line from transitions bound to one fixed-format role.

    This is deliberately not a line-family search.  The observation owner
    binds one tracked run first; this function then estimates the sole raw
    line supported by that run.  Adding an unrelated transition therefore
    cannot create another slope candidate or move this observation.
    """

    if role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
        raise ValueError("format-role line requires top or bottom role")
    if not 1 <= minimum_independent_support_regions <= SPATIAL_SUPPORT_REGION_COUNT:
        raise ValueError("format-role support-region requirement is invalid")
    if (
        measurement_set.state != EvidenceState.SUPPORTED
        or not measurement_set.coverage.complete
        or not transition_ids
        or len(set(transition_ids)) != len(transition_ids)
    ):
        return None
    requested = {str(identity) for identity in transition_ids}
    queried_traces = tuple(
        trace
        for trace in measurement_set.query.trace_positions_px
        if support_interval_px is None
        or support_interval_px.contains(
            float(trace), epsilon=PIXEL_CENTER_HALF_EXTENT_PX
        )
    )
    queried_set = set(queried_traces)
    transitions = tuple(
        transition
        for transition in measurement_set.transitions
        if str(transition.transition_id) in requested
        and transition.trace_coordinate_px in queried_set
    )
    if {str(item.transition_id) for item in transitions} != requested:
        return None
    if not queried_traces:
        return None
    points = tuple(
        TransitionPoint(
            transition=transition,
            trace=float(transition.trace_coordinate_px),
            coordinate=transition.coordinate_px,
        )
        for transition in transitions
    )
    minimum_support = 2
    if (
        len({point.trace for point in points}) < minimum_support
        or independent_spatial_support_count(
            queried_traces,
            tuple(point.trace for point in points),
        )
        < minimum_independent_support_regions
    ):
        return None
    if (
        float(np.mean([point.transition.gradient_z for point in points]))
        < spec.gradient_z_minimum
        or float(
            np.mean(
                [
                    max(
                        point.transition.tone_z,
                        point.transition.texture_z,
                    )
                    for point in points
                ]
            )
        )
        < spec.tone_or_texture_z_minimum
    ):
        return None
    fitted = fit_transition_line(
        points,
        boundary_axis_scale_px_per_mm.maximum,
        spec,
    )
    slope = fitted.slope
    intercept = fitted.intercept
    residuals = fitted.residuals
    selected = fitted.selected_points
    angle = _canonical_rotation_degrees(source_axis_long, slope)
    if abs(angle) > spec.maximum_measurable_line_angle_degrees + 1.0e-9:
        return None
    # A shared physical edge must pass through every retained transition's
    # measured position interval.  The sole extra allowance is the named
    # small continuous-bend contract; it does not grow when unrelated image
    # lines contaminate the corridor.
    inlier_threshold = (
        spec.inlier_minimum_threshold_mm
        * boundary_axis_scale_px_per_mm.maximum
    )
    predicted = np.asarray(
        [slope * point.trace + intercept for point in selected],
        dtype=np.float64,
    )
    interval_distance = np.asarray(
        [
            max(
                point.transition.physical_position_interval_px.minimum
                - value,
                0.0,
                value
                - point.transition.physical_position_interval_px.maximum,
            )
            for point, value in zip(selected, predicted, strict=True)
        ],
        dtype=np.float64,
    )
    inlier_mask = interval_distance <= inlier_threshold
    if int(np.count_nonzero(inlier_mask)) < minimum_support:
        return None
    inliers = tuple(
        point
        for point, keep in zip(selected, inlier_mask, strict=True)
        if bool(keep)
    )
    inlier_residuals = residuals[inlier_mask]
    traces = tuple(sorted(point.trace for point in inliers))
    independent_regions = independent_spatial_support_count(
        queried_traces,
        traces,
    )
    if independent_regions < minimum_independent_support_regions:
        return None
    continuity = continuous_trace_support_fraction(
        queried_traces,
        traces,
        spec=spec,
    )
    location_uncertainty = (
        float(
            np.median(
                np.abs(inlier_residuals - np.median(inlier_residuals))
            )
        )
        / math.sqrt(len(inliers))
        + spec.transition_coordinate_sampling_uncertainty_px
    )
    support = FiniteInterval(min(traces), max(traces))
    line = _source_line(
        measurement_set.query.boundary_axis,
        source_axis_long,
        slope,
        intercept,
        support,
    )
    normalized_uncertainty = location_uncertainty / math.hypot(1.0, slope)
    transition_width_uncertainty = float(
        np.median(
            [
                point.transition.localization_interval_px.width / 2.0
                for point in inliers
            ]
        )
    )
    fit_angle_uncertainty = math.degrees(
        math.atan2(
            spec.angle_endpoint_uncertainty_multiplier
            * location_uncertainty,
            max(spec.paired_sampling_uncertainty_px, support.width),
        )
    )
    full_angle_uncertainty = math.degrees(
        math.atan2(
            spec.angle_endpoint_uncertainty_multiplier
            * (
                location_uncertainty
                + float(np.median(np.abs(inlier_residuals)))
                + transition_width_uncertainty
            ),
            max(spec.paired_sampling_uncertainty_px, support.width),
        )
    )
    maximum_slope = math.tan(
        math.radians(spec.maximum_measurable_line_angle_degrees)
    )
    physical_slope = physical_slope_interval(inliers, maximum_slope)
    statistical_fit_angle = FiniteInterval(
        angle - fit_angle_uncertainty,
        angle + fit_angle_uncertainty,
    )
    residual_angle = FiniteInterval(
        angle - full_angle_uncertainty,
        angle + full_angle_uncertainty,
    )
    physical_angle = (
        None
        if physical_slope is None
        else FiniteInterval(
            math.degrees(math.atan(physical_slope.minimum)),
            math.degrees(math.atan(physical_slope.maximum)),
        )
    )
    # The robust fit supplies a representative statistical interval.  The
    # transition extents independently supply the complete physically
    # feasible direction interval.  A small continuous departure that makes
    # the exact straight-line intersection empty retains the residual-based
    # measurement interval; it is never repaired by a placement prior.
    full_angle = residual_angle
    if physical_angle is not None:
        full_angle = FiniteInterval(
            min(physical_angle.minimum, statistical_fit_angle.minimum),
            max(physical_angle.maximum, statistical_fit_angle.maximum),
        )
    selected_ids = tuple(
        sorted((point.transition.transition_id for point in inliers), key=str)
    )
    observation_id = physical_observation_id(
        "format-role-bound-line",
        role.value,
        *(str(identity) for identity in selected_ids),
    )
    return PhotoBoundaryObservation(
        observation_id=observation_id,
        role=role,
        line=line,
        offset_interval_px=FiniteInterval(
            line.offset_px - normalized_uncertainty,
            line.offset_px + normalized_uncertainty,
        ),
        fit_residual_px=float(np.median(np.abs(inlier_residuals))),
        angle_interval_degrees=full_angle,
        trace_support_count=len(inliers),
        queried_trace_count=len(queried_traces),
        independent_support_region_count=independent_regions,
        continuous_support_fraction=continuity,
        transition_ids=selected_ids,
        fit_receipt=fitted.receipt,
        left_background_preference_fraction=(
            sum(
                point.transition.left_texture_mean
                < point.transition.right_texture_mean
                for point in inliers
            )
            / len(inliers)
        ),
        right_background_preference_fraction=(
            sum(
                point.transition.right_texture_mean
                < point.transition.left_texture_mean
                for point in inliers
            )
            / len(inliers)
        ),
        fit_angle_interval_degrees=statistical_fit_angle,
        source_spanning_continuous=(
            source_spanning_continuous_trace_support(
                queried_traces,
                traces,
                spec=spec,
            )
        ),
        trace_coordinates_px=tuple(
            int(point.transition.trace_coordinate_px)
            for point in sorted(inliers, key=lambda item: item.trace)
        ),
        trace_position_intervals_px=tuple(
            point.transition.physical_position_interval_px
            for point in sorted(inliers, key=lambda item: item.trace)
        ),
    )
