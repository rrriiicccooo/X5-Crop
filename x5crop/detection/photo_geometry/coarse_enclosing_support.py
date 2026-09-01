"""Compile a source-wide enclosing pair from registered coarse pixels.

The coarse aggregate still owns only query localization.  This module may
add a separate direct support observation when the same registered sparse
traces close two continuous outer tracks around the fixed-format height.
Those tracks are not photo-aperture roles and never supply sequence phase.
"""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Mapping

import numpy as np
from scipy.optimize import linprog

from ...domain import (
    EvidenceState,
    FiniteInterval,
    ObservationId,
    PositiveInterval,
)
from ...formats import OUTPUT_PROTECTION_SPEC
from .measurement_model import (
    BroadMaterialTransitionRegionObservation,
    MaterialBackgroundSide,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .measurement_points import TransitionPoint
from .coarse_enclosing_model import (
    CoarseEnclosingCandidateFact,
    CoarseEnclosingMeasurementBasis,
    CoarseEnclosingResolution,
    CoarseEnclosingResolutionFailureKind,
    CoarseEnclosingSupport,
    CoarseEnclosingTrack,
    CoarseSharedDirection,
    CoarseSupportSide,
)
from .model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    QueryPurpose,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .physical_identity import physical_observation_id
from .registered_transition_measurement import (
    MeasuredTransitionPeak,
    TraceMeasurement,
    measured_transition_peaks,
)
from .robust_line_fit import fit_transition_line, physical_slope_interval
from .trace_support import source_spanning_continuous_trace_support
from .transition_tracking import track_broad_material_transition_regions


def _distance(interval: FiniteInterval, target: float) -> float:
    if interval.contains(target):
        return 0.0
    return min(abs(target - interval.minimum), abs(target - interval.maximum))


def _unique_nearest(
    peaks: tuple[MeasuredTransitionPeak, ...],
    target: float,
    maximum_distance: float,
) -> MeasuredTransitionPeak | None:
    values = tuple(
        (peak, _distance(peak.physical_position_interval, target))
        for peak in peaks
        if _distance(peak.physical_position_interval, target)
        <= maximum_distance
    )
    if not values:
        return None
    nearest = min(value for _peak, value in values)
    selected = tuple(
        peak for peak, value in values if abs(value - nearest) <= 1.0e-9
    )
    return selected[0] if len(selected) == 1 else None


def _transition(
    query: PhotoBoundaryMeasurementQuery,
    *,
    trace_ordinal: int,
    trace: int,
    peak: MeasuredTransitionPeak,
    side: CoarseSupportSide,
) -> PhotoBoundaryTransition:
    return PhotoBoundaryTransition(
        transition_id=physical_observation_id(
            "coarse-enclosing-transition",
            query.query_id,
            side.value,
            str(trace),
            f"{peak.canonical_coordinate:.9f}",
        ),
        query_id=query.query_id,
        trace_ordinal=trace_ordinal,
        trace_coordinate_px=trace,
        canonical_coordinate_px=peak.canonical_coordinate,
        localization_interval_px=peak.localization_interval,
        physical_position_interval_px=peak.physical_position_interval,
        gradient_z=peak.gradient_z,
        tone_z=peak.tone_z,
        texture_z=peak.texture_z,
        left_tone_mean=peak.left_tone,
        right_tone_mean=peak.right_tone,
        left_texture_mean=peak.left_texture,
        right_texture_mean=peak.right_texture,
        polarity=peak.polarity,
        peak_width_px=peak.peak_width_px,
        prominence=peak.prominence,
        local_noise=peak.local_noise,
    )


def _broad_region_transition(
    query: PhotoBoundaryMeasurementQuery,
    *,
    observation: BroadMaterialTransitionRegionObservation,
) -> PhotoBoundaryTransition:
    """Adapt one typed material change without inventing gradient support."""

    return PhotoBoundaryTransition(
        transition_id=observation.transition_id,
        query_id=query.query_id,
        trace_ordinal=observation.trace_ordinal,
        trace_coordinate_px=observation.trace_coordinate_px,
        canonical_coordinate_px=observation.canonical_coordinate_px,
        localization_interval_px=observation.localization_interval_px,
        physical_position_interval_px=(
            observation.physical_position_interval_px
        ),
        gradient_z=0.0,
        tone_z=observation.material_contrast_z,
        texture_z=0.0,
        left_tone_mean=observation.left_tone_mean,
        right_tone_mean=observation.right_tone_mean,
        left_texture_mean=observation.left_texture_mean,
        right_texture_mean=observation.right_texture_mean,
        polarity=observation.polarity,
        peak_width_px=observation.peak_width_px,
        prominence=observation.prominence,
        local_noise=observation.local_noise,
    )


def _fit_track(
    query: PhotoBoundaryMeasurementQuery,
    *,
    side: CoarseSupportSide,
    measurement_basis: CoarseEnclosingMeasurementBasis,
    transitions: tuple[PhotoBoundaryTransition, ...],
    reference_trace_px: float,
    support_traces_by_transition_id: Mapping[
        ObservationId,
        tuple[int, ...],
    ]
    | None = None,
) -> CoarseEnclosingTrack | None:
    def support_traces_for(
        values: tuple[PhotoBoundaryTransition, ...],
    ) -> tuple[int, ...]:
        if support_traces_by_transition_id is None:
            return tuple(
                sorted({item.trace_coordinate_px for item in values})
            )
        return tuple(
            sorted(
                {
                    trace
                    for item in values
                    for trace in support_traces_by_transition_id[
                        item.transition_id
                    ]
                }
            )
        )

    queried_traces = query.trace_positions_px
    traces = tuple(item.trace_coordinate_px for item in transitions)
    support_traces = support_traces_for(transitions)
    if (
        len(transitions) < SPATIAL_SUPPORT_REGION_COUNT
        or independent_spatial_support_count(
            query.trace_positions_px,
            support_traces,
        )
        < SPATIAL_SUPPORT_REGION_COUNT
        or not source_spanning_continuous_trace_support(
            query.trace_positions_px,
            support_traces,
            spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
        )
    ):
        return None
    points = tuple(
        TransitionPoint(
            transition=item,
            trace=float(item.trace_coordinate_px),
            coordinate=float(item.canonical_coordinate_px),
        )
        for item in transitions
    )
    fitted = fit_transition_line(
        points,
        query.boundary_axis_scale_px_per_mm.maximum,
        PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    )
    predicted = np.asarray(
        [
            fitted.slope * point.trace + fitted.intercept
            for point in fitted.selected_points
        ],
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
            for point, value in zip(
                fitted.selected_points,
                predicted,
                strict=True,
            )
        ],
        dtype=np.float64,
    )
    inlier_threshold = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.inlier_minimum_threshold_mm
        * query.boundary_axis_scale_px_per_mm.maximum
    )
    inlier_mask = interval_distance <= inlier_threshold
    retained = tuple(
        point
        for point, keep in zip(
            fitted.selected_points,
            inlier_mask,
            strict=True,
        )
        if bool(keep)
    )
    traces = tuple(int(point.trace) for point in retained)
    support_traces = support_traces_for(
        tuple(point.transition for point in retained)
    )
    if (
        len(retained) < SPATIAL_SUPPORT_REGION_COUNT
        or (
            measurement_basis
            == CoarseEnclosingMeasurementBasis.BROAD_MATERIAL
            and len(
                {
                    point.transition.polarity
                    for point in retained
                }
            )
            != 1
        )
        or independent_spatial_support_count(
            queried_traces,
            support_traces,
        )
        < SPATIAL_SUPPORT_REGION_COUNT
        or not source_spanning_continuous_trace_support(
            queried_traces,
            support_traces,
            spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
        )
    ):
        return None
    fitted = fit_transition_line(
        retained,
        query.boundary_axis_scale_px_per_mm.maximum,
        PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    )
    retained = fitted.selected_points
    residuals = tuple(float(value) for value in fitted.residuals)
    residual_center = float(np.median(residuals))
    residual_mad = float(
        np.median(np.abs(np.asarray(residuals) - residual_center))
    )
    numeric = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC
        .transition_coordinate_sampling_uncertainty_px
    )
    fit_error = residual_mad / math.sqrt(len(retained)) + numeric
    full_error = max(
        fit_error,
        max(
            abs(residual)
            + point.transition.localization_interval_px.width / 2.0
            for residual, point in zip(residuals, retained, strict=True)
        )
        + PHOTO_BOUNDARY_MEASUREMENT_SPEC.line_connection_allowance_px(
            query.boundary_axis_scale_px_per_mm.maximum
        ),
    )
    trace_span = float(max(traces) - min(traces))
    if trace_span <= 0.0:
        return None
    multiplier = PHOTO_BOUNDARY_MEASUREMENT_SPEC.angle_endpoint_uncertainty_multiplier
    fit_slope_error = multiplier * fit_error / trace_span
    full_slope_error = multiplier * full_error / trace_span
    slope = fitted.slope
    canonical_angle = math.degrees(math.atan(slope))
    fit_angle = FiniteInterval(
        math.degrees(math.atan(slope - fit_slope_error)),
        math.degrees(math.atan(slope + fit_slope_error)),
    )
    physical_slope = physical_slope_interval(
        retained,
        math.tan(
            math.radians(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC
                .maximum_measurable_line_angle_degrees
            )
        ),
    )
    if physical_slope is None:
        return None
    measured_full = FiniteInterval(
        math.degrees(math.atan(slope - full_slope_error)),
        math.degrees(math.atan(slope + full_slope_error)),
    )
    physical_angle = FiniteInterval(
        math.degrees(math.atan(physical_slope.minimum)),
        math.degrees(math.atan(physical_slope.maximum)),
    )
    full_angle = FiniteInterval(
        min(fit_angle.minimum, measured_full.minimum, physical_angle.minimum),
        max(fit_angle.maximum, measured_full.maximum, physical_angle.maximum),
    )
    canonical_position = fitted.slope * reference_trace_px + fitted.intercept
    identity = physical_observation_id(
        "coarse-enclosing-track",
        query.query_id,
        measurement_basis.value,
        side.value,
        *(str(point.transition.transition_id) for point in retained),
    )
    return CoarseEnclosingTrack(
        side=side,
        measurement_basis=measurement_basis,
        observation_id=identity,
        reference_trace_px=reference_trace_px,
        canonical_position_px=canonical_position,
        fit_position_interval_px=FiniteInterval(
            canonical_position - fit_error,
            canonical_position + fit_error,
        ),
        full_position_interval_px=FiniteInterval(
            canonical_position - full_error,
            canonical_position + full_error,
        ),
        trace_coordinates_px=tuple(sorted(traces)),
        support_trace_coordinates_px=support_traces,
        canonical_direction_degrees=canonical_angle,
        fit_direction_interval_degrees=fit_angle,
        full_direction_interval_degrees=full_angle,
        observed_direction_interval_degrees=full_angle,
        trace_position_intervals_px=tuple(
            point.transition.physical_position_interval_px
            for point in retained
        ),
        fit_residual_px=float(np.median(np.abs(residuals))),
        independent_support_region_count=SPATIAL_SUPPORT_REGION_COUNT,
        source_spanning_continuous=True,
    )


def _intersection(
    left: FiniteInterval,
    right: FiniteInterval,
) -> FiniteInterval | None:
    minimum = max(left.minimum, right.minimum)
    maximum = min(left.maximum, right.maximum)
    return None if minimum > maximum else FiniteInterval(minimum, maximum)


def _midpoint_transition(
    minimum: PhotoBoundaryTransition,
    maximum: PhotoBoundaryTransition,
) -> PhotoBoundaryTransition:
    if minimum.trace_coordinate_px != maximum.trace_coordinate_px:
        raise ValueError("enclosing sides must share one trace lattice")

    def midpoint(left: float, right: float) -> float:
        return (left + right) / 2.0

    localization = FiniteInterval(
        midpoint(
            minimum.localization_interval_px.minimum,
            maximum.localization_interval_px.minimum,
        ),
        midpoint(
            minimum.localization_interval_px.maximum,
            maximum.localization_interval_px.maximum,
        ),
    )
    physical = FiniteInterval(
        midpoint(
            minimum.physical_position_interval_px.minimum,
            maximum.physical_position_interval_px.minimum,
        ),
        midpoint(
            minimum.physical_position_interval_px.maximum,
            maximum.physical_position_interval_px.maximum,
        ),
    )
    return PhotoBoundaryTransition(
        transition_id=physical_observation_id(
            "coarse-enclosing-midpoint",
            str(minimum.transition_id),
            str(maximum.transition_id),
        ),
        query_id=minimum.query_id,
        trace_ordinal=minimum.trace_ordinal,
        trace_coordinate_px=minimum.trace_coordinate_px,
        canonical_coordinate_px=midpoint(
            minimum.canonical_coordinate_px,
            maximum.canonical_coordinate_px,
        ),
        localization_interval_px=localization,
        physical_position_interval_px=physical,
        gradient_z=midpoint(minimum.gradient_z, maximum.gradient_z),
        tone_z=midpoint(minimum.tone_z, maximum.tone_z),
        texture_z=midpoint(minimum.texture_z, maximum.texture_z),
        left_tone_mean=midpoint(
            minimum.left_tone_mean,
            maximum.left_tone_mean,
        ),
        right_tone_mean=midpoint(
            minimum.right_tone_mean,
            maximum.right_tone_mean,
        ),
        left_texture_mean=midpoint(
            minimum.left_texture_mean,
            maximum.left_texture_mean,
        ),
        right_texture_mean=midpoint(
            minimum.right_texture_mean,
            maximum.right_texture_mean,
        ),
        polarity=0,
        peak_width_px=midpoint(
            minimum.peak_width_px,
            maximum.peak_width_px,
        ),
        prominence=midpoint(minimum.prominence, maximum.prominence),
        local_noise=midpoint(minimum.local_noise, maximum.local_noise),
    )


def _reference_position_interval(
    transitions: tuple[PhotoBoundaryTransition, ...],
    *,
    reference_trace_px: float,
    slope_interval: FiniteInterval,
) -> FiniteInterval | None:
    """Project one line's direct intervals without separating slope/offset."""

    rows: list[tuple[float, float]] = []
    limits: list[float] = []
    for item in transitions:
        distance = float(item.trace_coordinate_px) - reference_trace_px
        interval = item.physical_position_interval_px
        rows.extend(((1.0, distance), (-1.0, -distance)))
        limits.extend((interval.maximum, -interval.minimum))
    bounds = ((None, None), (slope_interval.minimum, slope_interval.maximum))
    results: list[float] = []
    for objective in ((1.0, 0.0), (-1.0, 0.0)):
        fitted = linprog(
            objective,
            A_ub=np.asarray(rows, dtype=np.float64),
            b_ub=np.asarray(limits, dtype=np.float64),
            bounds=bounds,
            method="highs",
        )
        if not fitted.success or fitted.x is None:
            return None
        results.append(float(fitted.x[0]))
    return FiniteInterval(results[0], results[1])


def _shared_tracks(
    query: PhotoBoundaryMeasurementQuery,
    *,
    minimum_track: CoarseEnclosingTrack,
    maximum_track: CoarseEnclosingTrack,
    minimum_transitions: tuple[PhotoBoundaryTransition, ...],
    maximum_transitions: tuple[PhotoBoundaryTransition, ...],
    reference_trace_px: float,
) -> tuple[CoarseEnclosingTrack, CoarseEnclosingTrack] | None:
    """Compile one straight strip direction and keep side bend as position."""

    if tuple(item.trace_coordinate_px for item in minimum_transitions) != tuple(
        item.trace_coordinate_px for item in maximum_transitions
    ):
        return None
    minimum_points = tuple(
        TransitionPoint(item, float(item.trace_coordinate_px), item.canonical_coordinate_px)
        for item in minimum_transitions
    )
    maximum_points = tuple(
        TransitionPoint(item, float(item.trace_coordinate_px), item.canonical_coordinate_px)
        for item in maximum_transitions
    )
    maximum_slope = math.tan(
        math.radians(
            PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_measurable_line_angle_degrees
        )
    )
    minimum_slopes = physical_slope_interval(minimum_points, maximum_slope)
    maximum_slopes = physical_slope_interval(maximum_points, maximum_slope)
    if minimum_slopes is None or maximum_slopes is None:
        return None
    shared_slopes = _intersection(minimum_slopes, maximum_slopes)
    if shared_slopes is None:
        return None
    midpoint_points = tuple(
        TransitionPoint(
            transition := _midpoint_transition(minimum, maximum),
            float(transition.trace_coordinate_px),
            transition.canonical_coordinate_px,
        )
        for minimum, maximum in zip(
            minimum_transitions,
            maximum_transitions,
            strict=True,
        )
    )
    fitted = fit_transition_line(
        midpoint_points,
        query.boundary_axis_scale_px_per_mm.maximum,
        PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    )
    canonical_slope = min(
        shared_slopes.maximum,
        max(shared_slopes.minimum, fitted.slope),
    )
    trace_span = float(
        max(item.trace for item in midpoint_points)
        - min(item.trace for item in midpoint_points)
    )
    if trace_span <= 0.0:
        return None
    numeric = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC
        .transition_coordinate_sampling_uncertainty_px
    )
    residuals = tuple(float(value) for value in fitted.residuals)
    residual_center = float(np.median(residuals))
    residual_mad = float(
        np.median(np.abs(np.asarray(residuals) - residual_center))
    )
    fit_error = residual_mad / math.sqrt(len(midpoint_points)) + numeric
    slope_error = (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.angle_endpoint_uncertainty_multiplier
        * fit_error
        / trace_span
    )
    statistical_slopes = FiniteInterval(
        fitted.slope - slope_error,
        fitted.slope + slope_error,
    )
    fit_slopes = _intersection(statistical_slopes, shared_slopes)
    if fit_slopes is None:
        fit_slopes = FiniteInterval.exact(canonical_slope)
    shared_fit_angle = FiniteInterval(
        math.degrees(math.atan(fit_slopes.minimum)),
        math.degrees(math.atan(fit_slopes.maximum)),
    )
    shared_full_angle = FiniteInterval(
        math.degrees(math.atan(shared_slopes.minimum)),
        math.degrees(math.atan(shared_slopes.maximum)),
    )
    observed_angle = FiniteInterval(
        min(
            minimum_track.observed_direction_interval_degrees.minimum,
            maximum_track.observed_direction_interval_degrees.minimum,
        ),
        max(
            minimum_track.observed_direction_interval_degrees.maximum,
            maximum_track.observed_direction_interval_degrees.maximum,
        ),
    )
    canonical_angle = math.degrees(math.atan(canonical_slope))

    def compile_track(
        raw: CoarseEnclosingTrack,
        transitions: tuple[PhotoBoundaryTransition, ...],
    ) -> CoarseEnclosingTrack | None:
        full_position = _reference_position_interval(
            transitions,
            reference_trace_px=reference_trace_px,
            slope_interval=shared_slopes,
        )
        if full_position is None:
            return None
        canonical_candidates = tuple(
            item.canonical_coordinate_px
            - canonical_slope
            * (float(item.trace_coordinate_px) - reference_trace_px)
            for item in transitions
        )
        canonical = min(
            full_position.maximum,
            max(full_position.minimum, float(np.median(canonical_candidates))),
        )
        deviations = tuple(abs(value - canonical) for value in canonical_candidates)
        position_error = float(np.median(deviations)) / math.sqrt(len(deviations)) + numeric
        fit_position = FiniteInterval(
            max(full_position.minimum, canonical - position_error),
            min(full_position.maximum, canonical + position_error),
        )
        return replace(
            raw,
            canonical_position_px=canonical,
            fit_position_interval_px=fit_position,
            full_position_interval_px=full_position,
            canonical_direction_degrees=canonical_angle,
            fit_direction_interval_degrees=shared_fit_angle,
            full_direction_interval_degrees=shared_full_angle,
            observed_direction_interval_degrees=observed_angle,
            trace_coordinates_px=tuple(
                item.trace_coordinate_px for item in transitions
            ),
            trace_position_intervals_px=tuple(
                item.physical_position_interval_px for item in transitions
            ),
            fit_residual_px=float(np.median(deviations)),
        )

    minimum_shared = compile_track(minimum_track, minimum_transitions)
    maximum_shared = compile_track(maximum_track, maximum_transitions)
    if minimum_shared is None or maximum_shared is None:
        return None
    return minimum_shared, maximum_shared


def _compile_coarse_enclosing_pair(
    query: PhotoBoundaryMeasurementQuery,
    *,
    measurement_basis: CoarseEnclosingMeasurementBasis,
    minimum_transitions: tuple[PhotoBoundaryTransition, ...],
    maximum_transitions: tuple[PhotoBoundaryTransition, ...],
    expected_height_px: PositiveInterval | FiniteInterval,
    reference_trace_px: float,
    support_traces_by_transition_id: Mapping[
        ObservationId,
        tuple[int, ...],
    ]
    | None = None,
) -> tuple[CoarseSharedDirection | None, CoarseEnclosingSupport | None]:
    """Compile one role-free pair from already-unique physical tracks."""

    height = FiniteInterval(
        expected_height_px.minimum,
        expected_height_px.maximum,
    )
    canonical_height = height.center
    minimum_track = _fit_track(
        query,
        side=CoarseSupportSide.MINIMUM,
        measurement_basis=measurement_basis,
        transitions=minimum_transitions,
        reference_trace_px=reference_trace_px,
        support_traces_by_transition_id=support_traces_by_transition_id,
    )
    maximum_track = _fit_track(
        query,
        side=CoarseSupportSide.MAXIMUM,
        measurement_basis=measurement_basis,
        transitions=maximum_transitions,
        reference_trace_px=reference_trace_px,
        support_traces_by_transition_id=support_traces_by_transition_id,
    )
    if minimum_track is None or maximum_track is None:
        return None, None
    common_traces = tuple(
        sorted(
            set(minimum_track.trace_coordinates_px).intersection(
                maximum_track.trace_coordinates_px
            )
        )
    )
    common_support_traces = tuple(
        sorted(
            set(minimum_track.support_trace_coordinates_px).intersection(
                maximum_track.support_trace_coordinates_px
            )
        )
    )
    if (
        independent_spatial_support_count(
            query.trace_positions_px,
            common_traces,
        )
        < SPATIAL_SUPPORT_REGION_COUNT
        or not source_spanning_continuous_trace_support(
            query.trace_positions_px,
            common_support_traces,
            spec=PHOTO_BOUNDARY_MEASUREMENT_SPEC,
        )
    ):
        return None, None
    common = set(common_traces)
    minimum_values = tuple(
        item
        for item in minimum_transitions
        if item.trace_coordinate_px in common
    )
    maximum_values = tuple(
        item
        for item in maximum_transitions
        if item.trace_coordinate_px in common
    )
    shared = _shared_tracks(
        query,
        minimum_track=minimum_track,
        maximum_track=maximum_track,
        minimum_transitions=minimum_values,
        maximum_transitions=maximum_values,
        reference_trace_px=reference_trace_px,
    )
    if shared is None:
        return None, None
    minimum_track, maximum_track = shared
    direction = CoarseSharedDirection(
        direction_id=(
            "coarse-shared-direction:"
            f"{measurement_basis.value}:"
            f"{minimum_track.observation_id}:"
            f"{maximum_track.observation_id}"
        ),
        observation_ids=(
            minimum_track.observation_id,
            maximum_track.observation_id,
        ),
        canonical_direction_degrees=(
            minimum_track.canonical_direction_degrees
        ),
        fit_direction_interval_degrees=(
            minimum_track.fit_direction_interval_degrees
        ),
        full_direction_interval_degrees=(
            minimum_track.full_direction_interval_degrees
        ),
        observed_direction_interval_degrees=(
            minimum_track.observed_direction_interval_degrees
        ),
        trace_coordinates_px=minimum_track.trace_coordinates_px,
    )
    span = FiniteInterval(
        maximum_track.full_position_interval_px.minimum
        - minimum_track.full_position_interval_px.maximum,
        maximum_track.full_position_interval_px.maximum
        - minimum_track.full_position_interval_px.minimum,
    )
    if (
        span.minimum <= canonical_height
        or span.maximum
        > OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
        * canonical_height
    ):
        return direction, None
    return (
        direction,
        CoarseEnclosingSupport(
            minimum_track,
            maximum_track,
            span,
            len(query.trace_positions_px),
        ),
    )


def _observe_sharp_coarse_short_axis(
    query: PhotoBoundaryMeasurementQuery,
    trace_measurements: tuple[TraceMeasurement, ...],
    *,
    sharp_trace_ordinals: tuple[int, ...],
    aggregate_interval_px: FiniteInterval,
    expected_height_px: PositiveInterval | FiniteInterval,
    reference_trace_px: float,
) -> tuple[CoarseSharedDirection | None, CoarseEnclosingSupport | None]:
    """Compile sharp native transitions from the complete sparse lattice."""

    if len(trace_measurements) != len(query.trace_positions_px):
        raise ValueError("coarse enclosing trace measurement is incomplete")
    if (
        not sharp_trace_ordinals
        or tuple(sorted(set(sharp_trace_ordinals)))
        != sharp_trace_ordinals
        or sharp_trace_ordinals[0] < 0
        or sharp_trace_ordinals[-1] >= len(query.trace_positions_px)
    ):
        raise ValueError("coarse sharp trace view is invalid")
    sharp_query = replace(
        query,
        trace_positions_px=tuple(
            query.trace_positions_px[index]
            for index in sharp_trace_ordinals
        ),
        search_intervals_px=tuple(
            query.search_intervals_px[index]
            for index in sharp_trace_ordinals
        ),
        transition_ownership_intervals_px=tuple(
            query.transition_ownership_intervals_px[index]
            for index in sharp_trace_ordinals
        ),
    )
    sharp_measurements = tuple(
        trace_measurements[index] for index in sharp_trace_ordinals
    )
    height = FiniteInterval(
        expected_height_px.minimum,
        expected_height_px.maximum,
    )
    endpoint_margin = (
        (
            OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
            - 1.0
        )
        * height.maximum
        + query.measurement_halo_px
    )
    minimum_values: list[PhotoBoundaryTransition] = []
    maximum_values: list[PhotoBoundaryTransition] = []
    for ordinal, (trace, measured) in enumerate(
        zip(
            sharp_query.trace_positions_px,
            sharp_measurements,
            strict=True,
        )
    ):
        peaks = measured_transition_peaks(
            measured,
            PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            split_gradient_reversals=True,
        )
        minimum = _unique_nearest(
            peaks,
            aggregate_interval_px.minimum,
            endpoint_margin,
        )
        maximum = _unique_nearest(
            peaks,
            aggregate_interval_px.maximum,
            endpoint_margin,
        )
        if minimum is None or maximum is None or minimum is maximum:
            continue
        span = FiniteInterval(
            maximum.physical_position_interval.minimum
            - minimum.physical_position_interval.maximum,
            maximum.physical_position_interval.maximum
            - minimum.physical_position_interval.minimum,
        )
        if (
            span.maximum < height.minimum
            or span.minimum
            > OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
            * height.maximum
        ):
            continue
        minimum_values.append(
            _transition(
                sharp_query,
                trace_ordinal=ordinal,
                trace=trace,
                peak=minimum,
                side=CoarseSupportSide.MINIMUM,
            )
        )
        maximum_values.append(
            _transition(
                sharp_query,
                trace_ordinal=ordinal,
                trace=trace,
                peak=maximum,
                side=CoarseSupportSide.MAXIMUM,
            )
        )
    return _compile_coarse_enclosing_pair(
        sharp_query,
        measurement_basis=(
            CoarseEnclosingMeasurementBasis.SHARP_TRANSITION
        ),
        minimum_transitions=tuple(minimum_values),
        maximum_transitions=tuple(maximum_values),
        expected_height_px=expected_height_px,
        reference_trace_px=reference_trace_px,
    )


def _observe_broad_coarse_short_axis(
    measurement_set: PhotoBoundaryMeasurementSet,
    *,
    aggregate_interval_px: FiniteInterval,
    expected_height_px: PositiveInterval | FiniteInterval,
    reference_trace_px: float,
) -> tuple[CoarseSharedDirection | None, CoarseEnclosingSupport | None]:
    """Compile one unique outward-facing source-wide material pair."""

    query = measurement_set.query
    height = FiniteInterval(
        expected_height_px.minimum,
        expected_height_px.maximum,
    )
    endpoint_margin = (
        (
            OUTPUT_PROTECTION_SPEC.maximum_enclosing_support_height_ratio
            - 1.0
        )
        * height.maximum
        + query.measurement_halo_px
    )
    observations = {
        item.transition_id: item
        for item in measurement_set.broad_material_transitions
    }
    tracked = track_broad_material_transition_regions(
        (measurement_set,),
        reference_trace_px=reference_trace_px,
        boundary_axis_scale_px_per_mm=(
            query.boundary_axis_scale_px_per_mm
        ),
    )

    def candidates(
        *,
        target: float,
        background_side: MaterialBackgroundSide,
    ) -> tuple[
        tuple[
            tuple[PhotoBoundaryTransition, ...],
            Mapping[ObservationId, tuple[int, ...]],
        ],
        ...,
    ]:
        values = []
        for region in tracked:
            if _distance(region.position_interval_px, target) > endpoint_margin:
                continue
            selected = tuple(
                sorted(
                    (observations[item] for item in region.transition_ids),
                    key=lambda item: (
                        item.trace_coordinate_px,
                        str(item.transition_id),
                    ),
                )
            )
            if (
                len(selected) != SPATIAL_SUPPORT_REGION_COUNT
                or any(
                    item.background_side != background_side
                    for item in selected
                )
                or len({item.polarity for item in selected}) != 1
            ):
                continue
            transitions = tuple(
                _broad_region_transition(query, observation=item)
                for item in selected
            )
            support = {
                item.transition_id: item.contributing_trace_coordinates_px
                for item in selected
            }
            values.append((transitions, support))
        return tuple(values)

    minimum_candidates = candidates(
        target=aggregate_interval_px.minimum,
        background_side=MaterialBackgroundSide.LEFT,
    )
    maximum_candidates = candidates(
        target=aggregate_interval_px.maximum,
        background_side=MaterialBackgroundSide.RIGHT,
    )
    if len(minimum_candidates) != 1 or len(maximum_candidates) != 1:
        return None, None
    minimum_values, minimum_support = minimum_candidates[0]
    maximum_values, maximum_support = maximum_candidates[0]
    return _compile_coarse_enclosing_pair(
        query,
        measurement_basis=CoarseEnclosingMeasurementBasis.BROAD_MATERIAL,
        minimum_transitions=minimum_values,
        maximum_transitions=maximum_values,
        expected_height_px=expected_height_px,
        reference_trace_px=reference_trace_px,
        support_traces_by_transition_id={
            **minimum_support,
            **maximum_support,
        },
    )


def _candidate_fact(
    support: CoarseEnclosingSupport,
) -> CoarseEnclosingCandidateFact:
    return CoarseEnclosingCandidateFact(
        measurement_basis=support.minimum_track.measurement_basis,
        minimum_track_observation_id=(
            support.minimum_track.observation_id
        ),
        maximum_track_observation_id=(
            support.maximum_track.observation_id
        ),
    )


def _equivalent_support_pairs(
    left: CoarseEnclosingSupport,
    right: CoarseEnclosingSupport,
) -> bool:
    """Return whether two channels measured the same physical support pair."""

    return all(
        _intersection(first, second) is not None
        for first, second in (
            (
                left.minimum_track.full_position_interval_px,
                right.minimum_track.full_position_interval_px,
            ),
            (
                left.maximum_track.full_position_interval_px,
                right.maximum_track.full_position_interval_px,
            ),
            (
                left.minimum_track.full_direction_interval_degrees,
                right.minimum_track.full_direction_interval_degrees,
            ),
            (
                left.maximum_track.full_direction_interval_degrees,
                right.maximum_track.full_direction_interval_degrees,
            ),
            (left.observed_span_px, right.observed_span_px),
        )
    )


def observe_coarse_short_axis_tracks(
    measurement_set: PhotoBoundaryMeasurementSet,
    *,
    trace_measurements: tuple[TraceMeasurement, ...],
    sharp_trace_ordinals: tuple[int, ...],
    aggregate_interval_px: FiniteInterval | None,
    expected_height_px: PositiveInterval | FiniteInterval,
    reference_trace_px: float,
) -> tuple[
    CoarseSharedDirection | None,
    CoarseEnclosingSupport | None,
    CoarseEnclosingResolution,
]:
    """Resolve one role-free sharp/broad enclosing pair without scoring."""

    query = measurement_set.query
    if query.purpose != QueryPurpose.COARSE_STRIP_SHORT:
        raise ValueError("enclosing support requires the coarse-short query")
    if aggregate_interval_px is None:
        return (
            None,
            None,
            CoarseEnclosingResolution(
                state=EvidenceState.UNAVAILABLE,
                candidates=(),
                selected_candidate=None,
                failure_kind=(
                    CoarseEnclosingResolutionFailureKind
                    .AGGREGATE_SUPPORT_UNAVAILABLE
                ),
            ),
        )
    sharp_direction, sharp_support = _observe_sharp_coarse_short_axis(
        query,
        trace_measurements,
        sharp_trace_ordinals=sharp_trace_ordinals,
        aggregate_interval_px=aggregate_interval_px,
        expected_height_px=expected_height_px,
        reference_trace_px=reference_trace_px,
    )
    broad_direction, broad_support = _observe_broad_coarse_short_axis(
        measurement_set,
        aggregate_interval_px=aggregate_interval_px,
        expected_height_px=expected_height_px,
        reference_trace_px=reference_trace_px,
    )
    supports = tuple(
        value
        for value in (broad_support, sharp_support)
        if value is not None
    )
    candidates = tuple(
        sorted(
            (_candidate_fact(value) for value in supports),
            key=lambda item: item.measurement_basis.value,
        )
    )
    if not supports:
        return (
            sharp_direction,
            None,
            CoarseEnclosingResolution(
                state=EvidenceState.UNAVAILABLE,
                candidates=(),
                selected_candidate=None,
                failure_kind=(
                    CoarseEnclosingResolutionFailureKind.PAIR_UNAVAILABLE
                ),
            ),
        )
    if (
        sharp_support is not None
        and broad_support is not None
        and not _equivalent_support_pairs(sharp_support, broad_support)
    ):
        return (
            None,
            None,
            CoarseEnclosingResolution(
                state=EvidenceState.CONTRADICTED,
                candidates=candidates,
                selected_candidate=None,
                failure_kind=(
                    CoarseEnclosingResolutionFailureKind
                    .NON_EQUIVALENT_PAIR_CANDIDATES
                ),
            ),
        )
    selected_support = (
        sharp_support if sharp_support is not None else broad_support
    )
    selected_direction = (
        sharp_direction if sharp_support is not None else broad_direction
    )
    assert selected_support is not None
    selected_fact = _candidate_fact(selected_support)
    return (
        selected_direction,
        selected_support,
        CoarseEnclosingResolution(
            state=EvidenceState.SUPPORTED,
            candidates=candidates,
            selected_candidate=selected_fact,
            failure_kind=None,
        ),
    )
