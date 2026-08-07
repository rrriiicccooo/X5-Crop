from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import math

import numpy as np

from ...domain import (
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PositiveInterval,
)
from .model import (
    BoundaryAxis,
    BoundaryRole,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryMeasurementSpec,
    PhotoBoundaryObservation,
    PhotoBoundaryTransition,
    SideTransitionRegion,
    SourceCoordinateLine,
)


def make_photo_boundary_measurement_field(
    source_gray: np.ndarray,
    layout: str,
) -> PhotoBoundaryMeasurementField:
    return PhotoBoundaryMeasurementField(source_gray, layout)


def _stable_observation_id(prefix: str, *parts: object) -> ObservationId:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return ObservationId(f"{prefix}:{sha256(payload).hexdigest()[:24]}")


def _robust_z(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values.astype(np.float64, copy=False)
    values = values.astype(np.float64, copy=False)
    center = float(np.median(values))
    mad = float(np.median(np.abs(values - center)))
    scale = max(1.0, 1.4826 * mad)
    result = (values - center) / scale
    np.maximum(result, 0.0, out=result)
    return result


def _window_means(
    values: np.ndarray,
    coordinates: np.ndarray,
    window: int,
    gap: int,
) -> tuple[np.ndarray, np.ndarray]:
    prefix = np.empty(values.size + 1, dtype=np.float64)
    prefix[0] = 0.0
    np.cumsum(values, dtype=np.float64, out=prefix[1:])
    left_stop = coordinates - gap
    left_start = left_stop - window
    right_start = coordinates + gap
    right_stop = right_start + window
    left = (prefix[left_stop] - prefix[left_start]) / float(window)
    right = (prefix[right_stop] - prefix[right_start]) / float(window)
    return left, right
def _trace_measurements(
    values_u8: np.ndarray,
    interval: FiniteInterval,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    int,
]:
    window = max(1, int(math.ceil(spec.local_window_mm * scale_px_per_mm)))
    gap = max(1, int(math.ceil(spec.transition_gap_mm * scale_px_per_mm)))
    lower = max(window + gap, int(math.ceil(interval.minimum)))
    upper = min(
        values_u8.size - window - gap,
        int(math.floor(interval.maximum)) + 1,
    )
    if upper <= lower:
        empty = np.empty(0, dtype=np.float64)
        return (
            np.empty(0, dtype=np.int32),
            empty,
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            empty.copy(),
            0,
        )
    coordinates = np.arange(lower, upper, dtype=np.int32)
    values = values_u8.astype(np.float64, copy=False)
    left_tone, right_tone = _window_means(
        values,
        coordinates,
        window,
        gap,
    )
    tone = np.abs(right_tone - left_tone)

    differences = np.abs(np.diff(values))
    texture_coordinates = np.clip(
        coordinates,
        window + gap,
        differences.size - window - gap,
    )
    left_texture, right_texture = _window_means(
        differences,
        texture_coordinates,
        window,
        gap,
    )
    texture = np.abs(right_texture - left_texture)

    left_gradient = values[coordinates - gap]
    right_gradient = values[
        np.minimum(values.size - 1, coordinates + gap - 1)
    ]
    signed_gradient = right_gradient - left_gradient
    gradient = np.abs(signed_gradient)
    return (
        coordinates,
        _robust_z(gradient),
        _robust_z(tone),
        _robust_z(texture),
        signed_gradient,
        left_tone,
        right_tone,
        left_texture,
        right_texture,
        int(
            coordinates.nbytes
            + left_tone.nbytes
            + right_tone.nbytes
            + differences.nbytes
            + left_texture.nbytes
            + right_texture.nbytes
            + gradient.nbytes
        ),
    )


def _transition_groups(
    coordinates: np.ndarray,
    gradient_z: np.ndarray,
    tone_z: np.ndarray,
    texture_z: np.ndarray,
    signed_gradient: np.ndarray,
    left_tone: np.ndarray,
    right_tone: np.ndarray,
    left_texture: np.ndarray,
    right_texture: np.ndarray,
    scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[
    tuple[
        FiniteInterval,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        int,
        int,
    ], ...
]:
    # Pixel observations preserve the two evidence channels independently.
    # A line transition must satisfy both frozen thresholds after support is
    # aggregated; requiring both at the identical pixel would discard a real
    # edge whenever tone polarity or local texture changes along its length.
    credible = (
        (gradient_z >= spec.gradient_z_minimum)
        | (
            np.maximum(tone_z, texture_z)
            >= spec.tone_or_texture_z_minimum
        )
    )
    indices = np.flatnonzero(credible)
    if indices.size == 0:
        return ()
    split_at = np.flatnonzero(np.diff(indices) > 1) + 1
    groups = np.split(indices, split_at)
    maximum_width = max(
        1.0,
        spec.maximum_transition_interval_mm * scale_px_per_mm,
    )
    records: list[
        tuple[
            FiniteInterval,
            float,
            float,
            float,
            float,
            float,
            float,
            float,
            float,
            float,
            float,
            int,
            int,
        ]
    ] = []
    combined = gradient_z + np.maximum(tone_z, texture_z)
    localization = gradient_z + 0.25 * np.maximum(tone_z, texture_z)
    for group in groups:
        if group.size == 0:
            continue
        peak_index = int(group[int(np.argmax(localization[group]))])
        peak_coordinate = float(coordinates[peak_index])
        outside = np.ones(localization.size, dtype=bool)
        outside[group] = False
        local_noise = float(
            np.median(localization[outside])
            if np.any(outside)
            else np.min(localization[group])
        )
        prominence = max(
            0.0,
            float(localization[peak_index]) - local_noise,
        )
        half_height = local_noise + 0.5 * prominence
        peak_position = int(np.flatnonzero(group == peak_index)[0])
        left_position = peak_position
        right_position = peak_position
        while (
            left_position > 0
            and localization[int(group[left_position - 1])] >= half_height
        ):
            left_position -= 1
        while (
            right_position + 1 < group.size
            and localization[int(group[right_position + 1])] >= half_height
        ):
            right_position += 1
        peak_members = group[left_position : right_position + 1]
        eligible = peak_members[
            np.abs(coordinates[peak_members] - peak_coordinate)
            <= maximum_width / 2.0
        ]
        if eligible.size == 0:
            eligible = np.asarray((peak_index,), dtype=np.int64)
        minimum = max(
            peak_coordinate - maximum_width / 2.0,
            float(coordinates[int(eligible[0])]) - 0.5,
        )
        maximum = min(
            peak_coordinate + maximum_width / 2.0,
            float(coordinates[int(eligible[-1])]) + 0.5,
        )
        polarity_value = float(signed_gradient[peak_index])
        polarity = (
            1
            if polarity_value > 0.0
            else -1
            if polarity_value < 0.0
            else 0
        )
        records.append(
            (
                FiniteInterval(minimum, maximum),
                float(gradient_z[peak_index]),
                float(tone_z[peak_index]),
                float(texture_z[peak_index]),
                float(left_tone[peak_index]),
                float(right_tone[peak_index]),
                float(left_texture[peak_index]),
                float(right_texture[peak_index]),
                float(maximum - minimum),
                prominence,
                local_noise,
                polarity,
                peak_index,
            )
        )
    return tuple(records)


def _measure_query(
    field: PhotoBoundaryMeasurementField,
    query: PhotoBoundaryMeasurementQuery,
    spec: PhotoBoundaryMeasurementSpec,
) -> PhotoBoundaryMeasurementSet:
    registered_coordinate_count = sum(
        max(
            0,
            int(math.floor(interval.maximum))
            - int(math.ceil(interval.minimum))
            + 1,
        )
        for interval in query.search_intervals_px
    )
    transitions: list[PhotoBoundaryTransition] = []
    peak_temporary = 0
    pixel_query_count = 0
    completed_coordinates = 0
    completed_traces = 0
    try:
        axis_extent = (
            field.source_extent.width
            if query.boundary_axis == BoundaryAxis.X
            else field.source_extent.height
        )
        trace_extent = (
            field.source_extent.height
            if query.boundary_axis == BoundaryAxis.X
            else field.source_extent.width
        )
        scale = query.boundary_axis_scale_px_per_mm.maximum
        local_radius = int(
            math.ceil(
                (
                    spec.local_window_mm
                    + spec.transition_gap_mm
                )
                * scale
            )
        )
        for trace_ordinal, (trace, interval, ownership) in enumerate(
            zip(
                query.trace_positions_px,
                query.search_intervals_px,
                query.transition_ownership_intervals_px,
                strict=True,
            )
        ):
            if (
                trace < 0
                or trace >= trace_extent
                or interval.minimum < 0.0
                or interval.maximum > axis_extent - 1
            ):
                raise ValueError("registered query exceeds source authority")
            values = (
                field.source_gray[trace, :]
                if query.boundary_axis == BoundaryAxis.X
                else field.source_gray[:, trace]
            )
            (
                coordinates,
                gradient_z,
                tone_z,
                texture_z,
                signed_gradient,
                left_tone,
                right_tone,
                left_texture,
                right_texture,
                temporary_bytes,
            ) = _trace_measurements(values, interval, scale, spec)
            coordinate_count = max(
                0,
                int(math.floor(interval.maximum))
                - int(math.ceil(interval.minimum))
                + 1,
            )
            completed_coordinates += coordinate_count
            completed_traces += 1
            pixel_query_count += coordinate_count * (
                2 * local_radius + 2
            )
            peak_temporary = max(peak_temporary, temporary_bytes)
            for (
                transition_interval,
                gradient_value,
                tone_value,
                texture_value,
                left_tone_value,
                right_tone_value,
                left_texture_value,
                right_texture_value,
                peak_width_px,
                prominence,
                local_noise,
                polarity,
                peak_index,
            ) in _transition_groups(
                coordinates,
                gradient_z,
                tone_z,
                texture_z,
                signed_gradient,
                left_tone,
                right_tone,
                left_texture,
                right_texture,
                scale,
                spec,
            ):
                if not ownership.contains(
                    float(coordinates[peak_index]),
                    epsilon=1.0e-12,
                ):
                    continue
                transition_id = _stable_observation_id(
                    "photo-transition",
                    query.query_id,
                    trace_ordinal,
                    f"{transition_interval.minimum:.6f}",
                    f"{transition_interval.maximum:.6f}",
                )
                transitions.append(
                    PhotoBoundaryTransition(
                        transition_id=transition_id,
                        query_id=query.query_id,
                        trace_ordinal=trace_ordinal,
                        trace_coordinate_px=trace,
                        coordinate_interval_px=transition_interval,
                        gradient_z=gradient_value,
                        tone_z=tone_value,
                        texture_z=texture_value,
                        left_tone_mean=left_tone_value,
                        right_tone_mean=right_tone_value,
                        left_texture_mean=left_texture_value,
                        right_texture_mean=right_texture_value,
                        polarity=polarity,
                        peak_width_px=peak_width_px,
                        prominence=prominence,
                        local_noise=local_noise,
                        provenance=MeasurementProvenance(
                            root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
                            observation_id=transition_id,
                            dependencies=(MeasurementIdentity.BASE_GRAY,),
                            description=(
                                "source-coordinate local gradient, tone and "
                                "texture transition"
                            ),
                        ),
                    )
                )
    except Exception:
        receipt = PhotoBoundaryCoverageReceipt(
            query_id=query.query_id,
            registered_trace_count=len(query.trace_positions_px),
            completed_trace_count=completed_traces,
            registered_coordinate_count=registered_coordinate_count,
            completed_coordinate_count=completed_coordinates,
            pixel_query_count=pixel_query_count,
            streaming_block_count=(
                0
                if pixel_query_count == 0
                else int(
                    math.ceil(
                        pixel_query_count
                        / spec.maximum_streaming_block_pixels
                    )
                )
            ),
            peak_temporary_bytes=peak_temporary,
            complete=False,
        )
        return PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.UNAVAILABLE,
            transitions=(),
            coverage=receipt,
        )
    receipt = PhotoBoundaryCoverageReceipt(
        query_id=query.query_id,
        registered_trace_count=len(query.trace_positions_px),
        completed_trace_count=completed_traces,
        registered_coordinate_count=registered_coordinate_count,
        completed_coordinate_count=completed_coordinates,
        pixel_query_count=pixel_query_count,
        streaming_block_count=max(
            1,
            int(
                math.ceil(
                    max(1, pixel_query_count)
                    / spec.maximum_streaming_block_pixels
                )
            ),
        ),
        peak_temporary_bytes=peak_temporary,
        complete=True,
    )
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=EvidenceState.SUPPORTED,
        transitions=tuple(transitions),
        coverage=receipt,
    )


def measure_registered_queries(
    field: PhotoBoundaryMeasurementField,
    queries: tuple[PhotoBoundaryMeasurementQuery, ...],
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[PhotoBoundaryMeasurementSet, ...]:
    """Execute the complete pre-registered query lattice deterministically."""

    identities = tuple(query.query_id for query in queries)
    if len(set(identities)) != len(identities):
        raise ValueError("registered measurement queries must be unique")
    if tuple(query.registration_index for query in queries) != tuple(
        range(len(queries))
    ):
        raise ValueError("measurement queries must be completely pre-registered")
    return tuple(_measure_query(field, query, spec) for query in queries)


@dataclass(frozen=True)
class _Point:
    transition: PhotoBoundaryTransition
    trace: float
    coordinate: float
    weight: float


@dataclass
class _SideTrack:
    points: list[_Point]
    last_trace_index: int


def _unique_nearest(
    distances: list[tuple[float, int]],
    tie_tolerance_px: float,
) -> int | None:
    if not distances:
        return None
    ordered = sorted(distances)
    if (
        len(ordered) > 1
        and ordered[1][0] - ordered[0][0] <= tie_tolerance_px
    ):
        return None
    return ordered[0][1]


def provisional_cross_projection_interval(
    coordinate_interval_px: FiniteInterval,
    *,
    trace_coordinate_px: float,
    reference_trace_px: float,
    maximum_angle_degrees: float,
    numeric_uncertainty_px: float,
) -> FiniteInterval:
    """Project one per-trace run before the shared direction is known."""

    if (
        not math.isfinite(trace_coordinate_px)
        or not math.isfinite(reference_trace_px)
        or not math.isfinite(maximum_angle_degrees)
        or not 0.0 <= maximum_angle_degrees < 90.0
        or not math.isfinite(numeric_uncertainty_px)
        or numeric_uncertainty_px < 0.0
    ):
        raise ValueError("provisional cross projection is invalid")
    allowance = (
        abs(trace_coordinate_px - reference_trace_px)
        * math.tan(math.radians(maximum_angle_degrees))
        + numeric_uncertainty_px
    )
    return FiniteInterval(
        coordinate_interval_px.minimum - allowance,
        coordinate_interval_px.maximum + allowance,
    )


def _maximum_coverage_intervals(
    intervals: tuple[FiniteInterval, ...],
) -> tuple[int, tuple[FiniteInterval, ...], tuple[frozenset[int], ...]]:
    if not intervals:
        return 0, (), ()
    endpoints = sorted(
        {
            value
            for interval in intervals
            for value in (interval.minimum, interval.maximum)
        }
    )
    probes = [*endpoints]
    probes.extend(
        (left + right) / 2.0
        for left, right in zip(endpoints, endpoints[1:])
        if right > left
    )
    subsets = {
        frozenset(
            index
            for index, interval in enumerate(intervals)
            if interval.contains(probe, epsilon=1.0e-12)
        )
        for probe in probes
    }
    maximum = max(map(len, subsets), default=0)
    best_subsets = tuple(
        sorted(
            (subset for subset in subsets if len(subset) == maximum),
            key=lambda subset: tuple(sorted(subset)),
        )
    )
    intersections = tuple(
        FiniteInterval(
            max(intervals[index].minimum for index in subset),
            min(intervals[index].maximum for index in subset),
        )
        for subset in best_subsets
        if subset
    )
    unique = tuple(
        FiniteInterval(minimum, maximum_value)
        for minimum, maximum_value in sorted(
            {
                (interval.minimum, interval.maximum)
                for interval in intersections
            }
        )
    )
    return maximum, unique, best_subsets


def robust_scalar_location(
    values: tuple[float, ...],
    weights: tuple[float, ...],
    scale: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> float:
    """Fit one scalar location with the canonical four-round Huber contract."""

    if not values or len(values) != len(weights):
        raise ValueError("robust scalar evidence is invalid")
    array = np.asarray(values, dtype=np.float64)
    weight_array = np.asarray(weights, dtype=np.float64)
    if (
        not np.all(np.isfinite(array))
        or not np.all(np.isfinite(weight_array))
        or np.any(weight_array <= 0.0)
    ):
        raise ValueError("robust scalar evidence must be finite and positive")
    location = float(np.average(array, weights=weight_array))
    for _ in range(spec.huber_irls_rounds):
        residuals = array - location
        center = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - center)))
        threshold = max(
            spec.huber_minimum_threshold_mm * scale.maximum,
            spec.huber_mad_multiplier * mad,
        )
        robust = np.ones_like(residuals)
        mask = np.abs(residuals) > threshold
        robust[mask] = threshold / np.abs(residuals[mask])
        location = float(
            np.average(array, weights=weight_array * robust)
        )
    return location


def track_side_transition_regions(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    reference_trace_px: float,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    support_interval_px: FiniteInterval | None = None,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[SideTransitionRegion, ...]:
    """Track direction-free side proposals without merging parallel edges."""

    if any(
        item.state != EvidenceState.SUPPORTED or not item.coverage.complete
        for item in measurement_sets
    ):
        return ()
    transition_by_id = {
        str(transition.transition_id): transition
        for item in measurement_sets
        for transition in item.transitions
    }
    transitions = tuple(
        sorted(
            (
                transition
                for transition in transition_by_id.values()
                if support_interval_px is None
                or support_interval_px.contains(
                    float(transition.trace_coordinate_px),
                    epsilon=0.5,
                )
            ),
            key=lambda item: (
                item.trace_coordinate_px,
                item.coordinate_px,
                str(item.transition_id),
            ),
        )
    )
    queried_traces = tuple(
        sorted(
            {
                trace
                for item in measurement_sets
                for trace in item.query.trace_positions_px
                if support_interval_px is None
                or support_interval_px.contains(float(trace), epsilon=0.5)
            }
        )
    )
    if not transitions or not queried_traces:
        return ()
    trace_to_index = {
        trace: index for index, trace in enumerate(queried_traces)
    }
    by_trace: dict[int, list[_Point]] = defaultdict(list)
    for transition in transitions:
        by_trace[transition.trace_coordinate_px].append(
            _Point(
                transition=transition,
                trace=float(transition.trace_coordinate_px),
                coordinate=transition.coordinate_px,
                weight=max(
                    1.0,
                    transition.gradient_z
                    + max(transition.tone_z, transition.texture_z),
                ),
            )
        )
    tie_tolerance = max(
        1.0,
        spec.geometry_equivalence_mm
        * boundary_axis_scale_px_per_mm.maximum,
    )
    connection_px = max(
        1.0,
        spec.line_connection_allowance_mm
        * boundary_axis_scale_px_per_mm.maximum,
    )
    maximum_slope = math.tan(
        math.radians(spec.top_bottom_search_angle_degrees)
    )
    active: list[_SideTrack] = []
    completed: list[_SideTrack] = []
    for trace in queried_traces:
        trace_index = trace_to_index[trace]
        current = sorted(
            by_trace.get(trace, ()),
            key=lambda point: (
                point.coordinate,
                str(point.transition.transition_id),
            ),
        )
        eligible: list[_SideTrack] = []
        for track in active:
            if (
                trace_index - track.last_trace_index
                <= spec.maximum_missing_lattice_steps + 1
            ):
                eligible.append(track)
            else:
                completed.append(track)
        active = eligible
        connected_points: set[int] = set()
        gaps = tuple(
            sorted(
                {
                    trace_index - track.last_trace_index
                    for track in active
                }
            )
        )
        # A contiguous track owns the first reciprocal-nearest opportunity.
        # A track using the single permitted missing step may only consume a
        # transition left unmatched by the contiguous class.  This prevents
        # one ambiguous fork from leaving an older ghost track that blocks
        # the same physical edge on every later trace.
        for gap in gaps:
            track_indices = tuple(
                index
                for index, track in enumerate(active)
                if trace_index - track.last_trace_index == gap
            )
            proposed_by_point: dict[int, list[tuple[float, int]]] = (
                defaultdict(list)
            )
            nearest_by_track: dict[int, int | None] = {}
            for track_index in track_indices:
                track = active[track_index]
                last = track.points[-1]
                allowance = (
                    abs(float(trace) - last.trace) * maximum_slope
                    + connection_px
                )
                distances = [
                    (abs(point.coordinate - last.coordinate), point_index)
                    for point_index, point in enumerate(current)
                    if point_index not in connected_points
                    and abs(point.coordinate - last.coordinate)
                    <= allowance + 1.0e-12
                ]
                nearest = _unique_nearest(distances, tie_tolerance)
                nearest_by_track[track_index] = nearest
                if nearest is not None:
                    distance = abs(
                        current[nearest].coordinate - last.coordinate
                    )
                    proposed_by_point[nearest].append(
                        (distance, track_index)
                    )
            nearest_track_by_point = {
                point_index: _unique_nearest(proposals, tie_tolerance)
                for point_index, proposals in proposed_by_point.items()
            }
            for track_index in track_indices:
                point_index = nearest_by_track[track_index]
                if (
                    point_index is not None
                    and nearest_track_by_point.get(point_index)
                    == track_index
                ):
                    active[track_index].points.append(current[point_index])
                    active[track_index].last_trace_index = trace_index
                    connected_points.add(point_index)
        for point_index, point in enumerate(current):
            if point_index not in connected_points:
                active.append(_SideTrack([point], trace_index))
        still_active: list[_SideTrack] = []
        for track in active:
            if (
                trace_index - track.last_trace_index
                <= spec.maximum_missing_lattice_steps
            ):
                still_active.append(track)
            else:
                completed.append(track)
        active = still_active
    completed.extend(active)

    strong_minimum_support = max(
        spec.minimum_trace_count,
        int(math.ceil(spec.minimum_trace_fraction * len(queried_traces))),
    )
    minimum_support = spec.minimum_trace_count
    support_span = max(1.0, float(queried_traces[-1] - queried_traces[0]))
    maximum_connected_gap = (
        (
            float(np.median(np.diff(np.asarray(queried_traces))))
            if len(queried_traces) > 1
            else 1.0
        )
        * (spec.maximum_missing_lattice_steps + 1)
        + 1.0
    )
    regions: dict[tuple[str, ...], SideTransitionRegion] = {}
    for track in completed:
        points = tuple(
            sorted(
                track.points,
                key=lambda item: (
                    item.trace,
                    item.coordinate,
                    str(item.transition.transition_id),
                ),
            )
        )
        traces = tuple(point.trace for point in points)
        if len(set(traces)) < minimum_support:
            continue
        longest_span = 0.0
        run_start = traces[0]
        previous = traces[0]
        for trace in traces[1:]:
            if trace - previous > maximum_connected_gap:
                longest_span = max(longest_span, previous - run_start)
                run_start = trace
            previous = trace
        longest_span = max(longest_span, previous - run_start)
        continuous_fraction = min(1.0, longest_span / support_span)
        if (
            continuous_fraction < spec.minimum_continuous_support_fraction
            or sum(point.transition.gradient_z for point in points)
            / len(points)
            < spec.gradient_z_minimum
            or sum(
                max(point.transition.tone_z, point.transition.texture_z)
                for point in points
            )
            / len(points)
            < spec.tone_or_texture_z_minimum
        ):
            continue
        projected = tuple(
            provisional_cross_projection_interval(
                point.transition.coordinate_interval_px,
                trace_coordinate_px=point.trace,
                reference_trace_px=reference_trace_px,
                maximum_angle_degrees=spec.top_bottom_search_angle_degrees,
                numeric_uncertainty_px=connection_px,
            )
            for point in points
        )
        coverage, intersections, subsets = _maximum_coverage_intervals(
            projected
        )
        if coverage < minimum_support or not intersections:
            continue
        ambiguous = any(
            right.minimum - left.maximum > tie_tolerance
            for left, right in zip(intersections, intersections[1:])
        )
        proposal = FiniteInterval(
            intersections[0].minimum,
            intersections[-1].maximum,
        )
        selected_subset = next(
            subset
            for subset in subsets
            if len(subset) == coverage
            and max(projected[index].minimum for index in subset)
            == intersections[0].minimum
            and min(projected[index].maximum for index in subset)
            == intersections[0].maximum
        )
        selected = tuple(points[index] for index in sorted(selected_subset))
        transition_ids = tuple(
            sorted(
                (point.transition.transition_id for point in selected),
                key=str,
            )
        )
        signature = tuple(map(str, transition_ids))
        centers = np.asarray(
            [point.coordinate for point in selected], dtype=np.float64
        )
        residual = float(
            np.median(np.abs(centers - np.median(centers)))
        )
        background_side_support_fraction = (
            sum(
                (
                    (
                        max(
                            point.transition.left_texture_mean,
                            point.transition.right_texture_mean,
                        )
                        + 1.0
                    )
                    / (
                        min(
                            point.transition.left_texture_mean,
                            point.transition.right_texture_mean,
                        )
                        + 1.0
                    )
                    >= spec.background_texture_ratio_minimum
                )
                or (
                    abs(
                        point.transition.right_tone_mean
                        - point.transition.left_tone_mean
                    )
                    / (
                        1.0
                        + point.transition.left_texture_mean
                        + point.transition.right_texture_mean
                    )
                    >= spec.background_tone_to_texture_minimum
                )
                for point in selected
            )
            / len(selected)
        )
        left_background_preference_fraction = (
            sum(
                point.transition.left_texture_mean
                <= point.transition.right_texture_mean
                for point in selected
            )
            / len(selected)
        )
        right_background_preference_fraction = (
            sum(
                point.transition.right_texture_mean
                <= point.transition.left_texture_mean
                for point in selected
            )
            / len(selected)
        )
        if (
            len(selected) < strong_minimum_support
            and (
                background_side_support_fraction
                < spec.directional_background_support_minimum
                or max(
                    left_background_preference_fraction,
                    right_background_preference_fraction,
                )
                < spec.directional_sequence_support_minimum
            )
        ):
            continue
        region_id = _stable_observation_id(
            "side-region", *(str(item) for item in transition_ids)
        )
        regions[signature] = SideTransitionRegion(
            region_id=str(region_id),
            proposal_position_interval_px=proposal,
            transition_ids=transition_ids,
            trace_support_count=len(selected),
            queried_trace_count=len(queried_traces),
            continuous_support_fraction=continuous_fraction,
            fit_residual_px=residual,
            mean_gradient_z=sum(
                point.transition.gradient_z for point in selected
            )
            / len(selected),
            mean_tone_or_texture_z=sum(
                max(point.transition.tone_z, point.transition.texture_z)
                for point in selected
            )
            / len(selected),
            background_side_support_fraction=(
                background_side_support_fraction
            ),
            left_background_preference_fraction=(
                left_background_preference_fraction
            ),
            right_background_preference_fraction=(
                right_background_preference_fraction
            ),
            ambiguous=ambiguous,
        )
    return tuple(
        sorted(
            regions.values(),
            key=lambda item: (
                item.proposal_position_interval_px.center,
                item.region_id,
            ),
        )
    )


def _weighted_line_fit(
    points: tuple[_Point, ...],
    boundary_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[float, float, np.ndarray, tuple[_Point, ...]]:
    traces = np.asarray([point.trace for point in points], dtype=np.float64)
    coordinates = np.asarray(
        [point.coordinate for point in points],
        dtype=np.float64,
    )
    base_weights = np.asarray(
        [point.weight for point in points],
        dtype=np.float64,
    )
    design = np.column_stack((traces, np.ones_like(traces)))
    weights = base_weights.copy()
    coefficients = np.asarray((0.0, float(np.median(coordinates))))
    for _ in range(spec.huber_irls_rounds):
        weight_sum = float(np.sum(weights))
        weighted_trace_sum = float(np.dot(weights, traces))
        weighted_coordinate_sum = float(np.dot(weights, coordinates))
        weighted_trace_square_sum = float(
            np.dot(weights, traces * traces)
        )
        weighted_cross_sum = float(
            np.dot(weights, traces * coordinates)
        )
        denominator = (
            weight_sum * weighted_trace_square_sum
            - weighted_trace_sum * weighted_trace_sum
        )
        if abs(denominator) <= 1.0e-12:
            slope = 0.0
            intercept = weighted_coordinate_sum / max(
                weight_sum,
                1.0e-12,
            )
        else:
            slope = (
                weight_sum * weighted_cross_sum
                - weighted_trace_sum * weighted_coordinate_sum
            ) / denominator
            intercept = (
                weighted_coordinate_sum
                - slope * weighted_trace_sum
            ) / weight_sum
        coefficients = np.asarray((slope, intercept), dtype=np.float64)
        residuals = coordinates - design @ coefficients
        mad = float(
            np.median(
                np.abs(residuals - np.median(residuals))
            )
        )
        threshold = max(
            spec.huber_minimum_threshold_mm
            * boundary_scale_px_per_mm,
            spec.huber_mad_multiplier * mad,
        )
        huber = np.ones_like(residuals)
        outside = np.abs(residuals) > threshold
        huber[outside] = threshold / np.abs(residuals[outside])
        weights = base_weights * huber

    residuals = coordinates - design @ coefficients
    # One physical edge contributes at most one transition per trace.
    selected: list[_Point] = []
    for trace in sorted(set(point.trace for point in points)):
        indices = np.flatnonzero(traces == trace)
        best = min(
            indices,
            key=lambda index: (
                abs(float(residuals[index])),
                -points[int(index)].weight,
                str(points[int(index)].transition.transition_id),
            ),
        )
        selected.append(points[int(best)])
    if len(selected) != len(points):
        return _weighted_line_fit(
            tuple(selected),
            boundary_scale_px_per_mm,
            spec,
        )
    return (
        float(coefficients[0]),
        float(coefficients[1]),
        residuals,
        tuple(selected),
    )


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


def continuous_trace_support_fraction(
    queried_traces: tuple[int, ...],
    supporting_traces: tuple[int | float, ...],
) -> float:
    """Return the longest allowed-gap support run over the queried span."""

    if not queried_traces or not supporting_traces:
        return 0.0
    queried = tuple(sorted(queried_traces))
    supporting = tuple(sorted(set(supporting_traces)))
    steps = np.diff(np.asarray(queried, dtype=np.float64))
    step = float(np.median(steps)) if steps.size else 1.0
    maximum_gap = step * (
        PHOTO_BOUNDARY_MEASUREMENT_SPEC.maximum_missing_lattice_steps + 1
    ) + 1.0
    longest = 0.0
    run_start = supporting[0]
    previous = supporting[0]
    for trace in supporting[1:]:
        if trace - previous > maximum_gap:
            longest = max(longest, previous - run_start)
            run_start = trace
        previous = trace
    longest = max(longest, previous - run_start)
    queried_span = max(1.0, float(queried[-1] - queried[0]))
    return min(1.0, longest / queried_span)


def fit_template_bound_boundary_observation(
    measurement_set: PhotoBoundaryMeasurementSet,
    *,
    transition_ids: tuple[ObservationId, ...],
    role: BoundaryRole,
    source_axis_long: BoundaryAxis,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    minimum_trace_fraction: float | None = None,
    support_interval_px: FiniteInterval | None = None,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> PhotoBoundaryObservation | None:
    """Fit one robust line from transitions already bound to one template role.

    This is deliberately not a line-family search.  The template producer
    binds one tracked run first; this function then estimates the sole raw
    line supported by that run.  Adding an unrelated transition therefore
    cannot create another slope candidate or move this observation.
    """

    if role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
        raise ValueError("template-bound line requires top or bottom role")
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
        or support_interval_px.contains(float(trace), epsilon=0.5)
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
        _Point(
            transition=transition,
            trace=float(transition.trace_coordinate_px),
            coordinate=transition.coordinate_px,
            weight=max(
                1.0,
                transition.gradient_z
                + max(transition.tone_z, transition.texture_z),
            ),
        )
        for transition in transitions
    )
    support_fraction = (
        spec.minimum_trace_fraction
        if minimum_trace_fraction is None
        else minimum_trace_fraction
    )
    if not 0.0 < support_fraction <= 1.0:
        raise ValueError("template-bound support fraction is invalid")
    minimum_support = max(
        spec.minimum_trace_count,
        math.ceil(support_fraction * len(queried_traces)),
    )
    if len({point.trace for point in points}) < minimum_support:
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
    slope, intercept, residuals, selected = _weighted_line_fit(
        points,
        boundary_axis_scale_px_per_mm.maximum,
        spec,
    )
    angle = _canonical_rotation_degrees(source_axis_long, slope)
    if abs(angle) > spec.top_bottom_search_angle_degrees + 1.0e-9:
        return None
    residual_center = float(np.median(residuals))
    residual_mad = float(
        np.median(np.abs(residuals - residual_center))
    )
    inlier_threshold = max(
        spec.inlier_minimum_threshold_mm
        * boundary_axis_scale_px_per_mm.maximum,
        spec.inlier_mad_multiplier * residual_mad,
    )
    inlier_mask = np.abs(residuals - residual_center) <= inlier_threshold
    if int(np.count_nonzero(inlier_mask)) < minimum_support:
        return None
    inliers = tuple(
        point
        for point, keep in zip(selected, inlier_mask, strict=True)
        if bool(keep)
    )
    inlier_residuals = residuals[inlier_mask]
    traces = tuple(sorted(point.trace for point in inliers))
    continuity = continuous_trace_support_fraction(queried_traces, traces)
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
                point.transition.coordinate_interval_px.width / 2.0
                for point in inliers
            ]
        )
    )
    fit_angle_uncertainty = math.degrees(
        math.atan2(
            spec.angle_endpoint_uncertainty_multiplier
            * location_uncertainty,
            max(1.0, support.width),
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
            max(1.0, support.width),
        )
    )
    selected_ids = tuple(
        sorted((point.transition.transition_id for point in inliers), key=str)
    )
    observation_id = _stable_observation_id(
        "template-bound-line",
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
        angle_interval_degrees=FiniteInterval(
            angle - full_angle_uncertainty,
            angle + full_angle_uncertainty,
        ),
        trace_support_count=len(inliers),
        queried_trace_count=len(queried_traces),
        continuous_support_fraction=continuity,
        transition_ids=selected_ids,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
            observation_id=observation_id,
            dependencies=(MeasurementIdentity.BASE_GRAY,),
            description=(
                "single robust line from transitions bound to one fixed "
                "format template role"
            ),
        ),
        background_side_support_fraction=(
            sum(
                (
                    (
                        max(
                            point.transition.left_texture_mean,
                            point.transition.right_texture_mean,
                        )
                        + 1.0
                    )
                    / (
                        min(
                            point.transition.left_texture_mean,
                            point.transition.right_texture_mean,
                        )
                        + 1.0
                    )
                    >= spec.background_texture_ratio_minimum
                )
                or (
                    abs(
                        point.transition.right_tone_mean
                        - point.transition.left_tone_mean
                    )
                    / (
                        1.0
                        + point.transition.left_texture_mean
                        + point.transition.right_texture_mean
                    )
                    >= spec.background_tone_to_texture_minimum
                )
                for point in inliers
            )
            / len(inliers)
        ),
        left_background_preference_fraction=(
            sum(
                point.transition.left_texture_mean
                <= point.transition.right_texture_mean
                for point in inliers
            )
            / len(inliers)
        ),
        right_background_preference_fraction=(
            sum(
                point.transition.right_texture_mean
                <= point.transition.left_texture_mean
                for point in inliers
            )
            / len(inliers)
        ),
        fit_angle_interval_degrees=FiniteInterval(
            angle - fit_angle_uncertainty,
            angle + fit_angle_uncertainty,
        ),
    )
