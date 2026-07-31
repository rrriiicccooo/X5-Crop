from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import math
from time import perf_counter

import numpy as np

from ...domain import (
    EvidenceState,
    FiniteInterval,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
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
            int,
            int,
        ]
    ] = []
    combined = gradient_z + np.maximum(tone_z, texture_z)
    for group in groups:
        if group.size == 0:
            continue
        peak_index = int(group[int(np.argmax(combined[group]))])
        peak_coordinate = float(coordinates[peak_index])
        eligible = group[
            np.abs(coordinates[group] - peak_coordinate)
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
        polarity = 1 if polarity_value > 0.0 else -1 if polarity_value < 0.0 else 0
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
        for trace_ordinal, (trace, interval) in enumerate(
            zip(
                query.trace_positions_px,
                query.search_intervals_px,
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
            shared_measurement_reuse_count=0,
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
        shared_measurement_reuse_count=0,
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


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def _line_components(
    points: tuple[_Point, ...],
    trace_step_px: float,
    boundary_scale_px_per_mm: float,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[tuple[_Point, ...], ...]:
    if not points:
        return ()
    by_trace: dict[float, list[int]] = defaultdict(list)
    for index, point in enumerate(points):
        by_trace[point.trace].append(index)
    traces = sorted(by_trace)
    sets = _DisjointSet(len(points))
    maximum_trace_gap = (
        trace_step_px
        * (spec.maximum_missing_lattice_steps + 1)
        + 1.0
    )
    for left_index, left_trace in enumerate(traces):
        for right_trace in traces[left_index + 1 :]:
            delta_trace = right_trace - left_trace
            if delta_trace > maximum_trace_gap:
                break
            coordinate_allowance = (
                abs(delta_trace)
                * math.tan(
                    math.radians(spec.maximum_search_angle_degrees)
                )
                + spec.line_connection_allowance_mm
                * boundary_scale_px_per_mm
            )
            right_points = sorted(
                by_trace[right_trace],
                key=lambda index: points[index].coordinate,
            )
            right_coordinates = np.asarray(
                [points[index].coordinate for index in right_points],
                dtype=np.float64,
            )
            for left_point_index in by_trace[left_trace]:
                center = points[left_point_index].coordinate
                start = int(
                    np.searchsorted(
                        right_coordinates,
                        center - coordinate_allowance,
                        side="left",
                    )
                )
                stop = int(
                    np.searchsorted(
                        right_coordinates,
                        center + coordinate_allowance,
                        side="right",
                    )
                )
                for position in range(start, stop):
                    sets.union(left_point_index, right_points[position])
    grouped: dict[int, list[_Point]] = defaultdict(list)
    for index, point in enumerate(points):
        grouped[sets.find(index)].append(point)
    return tuple(
        tuple(
            sorted(
                group,
                key=lambda item: (
                    item.trace,
                    item.coordinate,
                    str(item.transition.transition_id),
                ),
            )
        )
        for group in grouped.values()
    )


def _hough_line_families(
    points: tuple[_Point, ...],
    *,
    support_span_px: float,
    trace_step_px: float,
    boundary_scale_px_per_mm: float,
    minimum_support: int,
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[tuple[_Point, ...], ...]:
    """Enumerate supported near-axis line families without graph percolation.

    A dense connected-component graph can accidentally join several parallel
    photo/internal edges through short texture fragments.  This deterministic
    bounded-angle accumulator keeps each candidate tied to one line equation.
    It enumerates every supported bin and performs no score/top-N truncation.
    """

    if not points:
        return ()
    maximum_slope = math.tan(
        math.radians(spec.maximum_search_angle_degrees)
    )
    connection_px = max(
        1.0,
        spec.line_connection_allowance_mm
        * boundary_scale_px_per_mm,
    )
    slope_step = max(
        1.0e-5,
        connection_px / max(1.0, support_span_px),
    )
    slope_count = int(
        math.ceil(2.0 * maximum_slope / slope_step)
    ) + 1
    slopes = np.linspace(
        -maximum_slope,
        maximum_slope,
        slope_count,
        dtype=np.float64,
    )
    traces = np.asarray([point.trace for point in points], dtype=np.float64)
    coordinates = np.asarray(
        [point.coordinate for point in points],
        dtype=np.float64,
    )
    family_by_geometry_bin: dict[
        tuple[int, int],
        tuple[
            tuple[int, float, tuple[str, ...]],
            tuple[_Point, ...],
        ],
    ] = {}
    bin_width = 2.0 * connection_px
    geometry_equivalence_px = max(
        1.0,
        spec.geometry_equivalence_mm * boundary_scale_px_per_mm,
    )
    slope_equivalence = geometry_equivalence_px / max(
        1.0,
        support_span_px,
    )
    support_center = float(np.median(traces))
    for slope in slopes:
        intercepts = coordinates - slope * traces
        for shift in (0.0, 0.5):
            bin_indices = np.floor(
                intercepts / bin_width + shift
            ).astype(np.int64)
            grouped: dict[int, list[int]] = defaultdict(list)
            for point_index, bin_index in enumerate(bin_indices):
                grouped[int(bin_index)].append(point_index)
            for indices in grouped.values():
                trace_groups: dict[float, list[int]] = defaultdict(list)
                for point_index in indices:
                    trace_groups[points[point_index].trace].append(point_index)
                if len(trace_groups) < minimum_support:
                    continue
                center = float(np.median(intercepts[indices]))
                selected = tuple(
                    points[
                        min(
                            point_indices,
                            key=lambda index: (
                                abs(float(intercepts[index]) - center),
                                -points[index].weight,
                                str(points[index].transition.transition_id),
                            ),
                        )
                    ]
                    for _trace, point_indices in sorted(trace_groups.items())
                )
                selected_traces = tuple(point.trace for point in selected)
                if len(selected_traces) < minimum_support:
                    continue
                if (
                    sum(
                        point.transition.gradient_z
                        for point in selected
                    )
                    / len(selected)
                    < spec.gradient_z_minimum
                    or sum(
                        max(
                            point.transition.tone_z,
                            point.transition.texture_z,
                        )
                        for point in selected
                    )
                    / len(selected)
                    < spec.tone_or_texture_z_minimum
                ):
                    continue
                longest_span = 0.0
                run_start = selected_traces[0]
                previous = selected_traces[0]
                maximum_connected_gap = (
                    trace_step_px
                    * (spec.maximum_missing_lattice_steps + 1)
                    + 1.0
                )
                for trace in selected_traces[1:]:
                    if trace - previous > maximum_connected_gap:
                        longest_span = max(
                            longest_span,
                            previous - run_start,
                        )
                        run_start = trace
                    previous = trace
                longest_span = max(
                    longest_span,
                    previous - run_start,
                )
                if (
                    longest_span / max(1.0, support_span_px)
                    < spec.minimum_continuous_support_fraction
                ):
                    continue
                signature = tuple(
                    sorted(
                        (
                            str(point.transition.transition_id)
                            for point in selected
                        )
                    )
                )
                center_coordinate = center + float(slope) * support_center
                geometry_key = (
                    int(round(center_coordinate / geometry_equivalence_px)),
                    int(round(float(slope) / slope_equivalence)),
                )
                quality = (
                    len(selected),
                    sum(point.weight for point in selected),
                    tuple(reversed(signature)),
                )
                existing = family_by_geometry_bin.get(geometry_key)
                if existing is None or quality > existing[0]:
                    family_by_geometry_bin[geometry_key] = (
                        quality,
                        selected,
                    )
    return tuple(
        family_by_geometry_bin[key][1]
        for key in sorted(family_by_geometry_bin)
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
    role: BoundaryRole,
    slope: float,
) -> float:
    return math.degrees(
        math.atan(slope)
        if role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
        else -math.atan(slope)
    )


def fit_boundary_line_families(
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    role: BoundaryRole,
    source_axis_long: BoundaryAxis,
    support_interval_px: FiniteInterval,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    trace_axis_scale_px_per_mm: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[PhotoBoundaryObservation, ...]:
    """Fit every fully measured physical line family in one support span."""

    supported_sets = tuple(
        item
        for item in measurement_sets
        if item.state == EvidenceState.SUPPORTED
    )
    if len(supported_sets) != len(measurement_sets):
        return ()
    transitions = tuple(
        transition
        for item in supported_sets
        for transition in item.transitions
        if support_interval_px.contains(
            float(transition.trace_coordinate_px),
            epsilon=0.5,
        )
    )
    queried_traces = tuple(
        sorted(
            {
                trace
                for item in supported_sets
                for trace in item.query.trace_positions_px
                if support_interval_px.contains(float(trace), epsilon=0.5)
            }
        )
    )
    if not queried_traces:
        return ()
    boundary_axis = supported_sets[0].query.boundary_axis
    if any(
        item.query.boundary_axis != boundary_axis
        for item in supported_sets
    ):
        raise ValueError("one line fit cannot mix source boundary axes")
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
    trace_differences = np.diff(np.asarray(queried_traces, dtype=np.float64))
    trace_step = (
        float(np.median(trace_differences))
        if trace_differences.size
        else spec.lattice_minimum_mm
        * trace_axis_scale_px_per_mm.maximum
    )
    minimum_support = max(
        spec.minimum_trace_count,
        int(math.ceil(spec.minimum_trace_fraction * len(queried_traces))),
    )
    observations: list[PhotoBoundaryObservation] = []
    for family in _hough_line_families(
        points,
        support_span_px=support_interval_px.width,
        trace_step_px=trace_step,
        boundary_scale_px_per_mm=(
            boundary_axis_scale_px_per_mm.maximum
        ),
        minimum_support=minimum_support,
        spec=spec,
    ):
        unique_trace_count = len(set(point.trace for point in family))
        if unique_trace_count < minimum_support:
            continue
        # The two frozen evidence requirements are line-family facts.  Check
        # them before the four-round robust fit so weak texture ridges do not
        # consume an IRLS solve merely because either channel produced a
        # local transition proposal.  The same requirements are checked again
        # on fitted inliers below; this is dominance by missing evidence, not
        # a score/top-N truncation.
        if (
            float(
                np.mean(
                    [
                        point.transition.gradient_z
                        for point in family
                    ]
                )
            )
            < spec.gradient_z_minimum
            or float(
                np.mean(
                    [
                        max(
                            point.transition.tone_z,
                            point.transition.texture_z,
                        )
                        for point in family
                    ]
                )
            )
            < spec.tone_or_texture_z_minimum
        ):
            continue
        preliminary_traces = tuple(
            sorted(point.trace for point in family)
        )
        preliminary_maximum_gap = (
            trace_step
            * (spec.maximum_missing_lattice_steps + 1)
            + 1.0
        )
        preliminary_longest_span = 0.0
        run_start = preliminary_traces[0]
        previous = preliminary_traces[0]
        for trace in preliminary_traces[1:]:
            if trace - previous > preliminary_maximum_gap:
                preliminary_longest_span = max(
                    preliminary_longest_span,
                    previous - run_start,
                )
                run_start = trace
            previous = trace
        preliminary_longest_span = max(
            preliminary_longest_span,
            previous - run_start,
        )
        if (
            preliminary_longest_span
            / max(1.0, support_interval_px.width)
            < spec.minimum_continuous_support_fraction
        ):
            continue
        slope, intercept, residuals, selected = _weighted_line_fit(
            family,
            boundary_axis_scale_px_per_mm.maximum,
            spec,
        )
        angle = _canonical_rotation_degrees(role, slope)
        if abs(angle) > spec.maximum_search_angle_degrees + 1.0e-9:
            continue
        traces = tuple(sorted(point.trace for point in selected))
        support_span = max(traces) - min(traces) if len(traces) > 1 else 0.0
        coarse_span = max(1.0, support_interval_px.width)
        maximum_connected_gap = (
            trace_step
            * (spec.maximum_missing_lattice_steps + 1)
            + 1.0
        )
        run_starts = [traces[0]]
        run_stops: list[float] = []
        for left, right in zip(traces, traces[1:]):
            if right - left > maximum_connected_gap:
                run_stops.append(left)
                run_starts.append(right)
        run_stops.append(traces[-1])
        longest_continuous_span = max(
            stop - start
            for start, stop in zip(
                run_starts,
                run_stops,
                strict=True,
            )
        )
        continuous_fraction = min(
            1.0,
            longest_continuous_span / coarse_span,
        )
        if continuous_fraction < spec.minimum_continuous_support_fraction:
            continue
        residual_center = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - residual_center)))
        inlier_threshold = max(
            spec.inlier_minimum_threshold_mm
            * boundary_axis_scale_px_per_mm.maximum,
            spec.inlier_mad_multiplier * mad,
        )
        inliers = np.abs(residuals - residual_center) <= inlier_threshold
        if int(np.count_nonzero(inliers)) < minimum_support:
            continue
        selected_inliers = tuple(
            point
            for point, keep in zip(selected, inliers, strict=True)
            if bool(keep)
        )
        if (
            float(
                np.mean(
                    [
                        point.transition.gradient_z
                        for point in selected_inliers
                    ]
                )
            )
            < spec.gradient_z_minimum
            or float(
                np.mean(
                    [
                        max(
                            point.transition.tone_z,
                            point.transition.texture_z,
                        )
                        for point in selected_inliers
                    ]
                )
            )
            < spec.tone_or_texture_z_minimum
        ):
            continue
        transition_half_width = max(
            point.transition.coordinate_interval_px.width / 2.0
            for point in selected
        )
        numeric_sampling_error = 0.5
        coordinate_uncertainty = (
            transition_half_width
            + inlier_threshold
            + numeric_sampling_error
        )
        line = _source_line(
            boundary_axis,
            source_axis_long,
            slope,
            intercept,
            FiniteInterval(min(traces), max(traces)),
        )
        normalized_uncertainty = coordinate_uncertainty / math.hypot(
            1.0,
            slope,
        )
        angle_uncertainty = math.degrees(
            math.atan2(
                spec.angle_endpoint_uncertainty_multiplier
                * coordinate_uncertainty,
                max(1.0, support_span),
            )
        )
        transition_ids = tuple(
            sorted(
                (
                    point.transition.transition_id
                    for point in selected
                ),
                key=str,
            )
        )
        observation_id = _stable_observation_id(
            "photo-line",
            role.value,
            *(str(item) for item in transition_ids),
        )
        observations.append(
            # A background/separator side is a pixel observation, not an
            # edge-authority shortcut.  It may rank otherwise compatible
            # lines, while contact/overlap lines remain valid with zero
            # background support.
            PhotoBoundaryObservation(
                observation_id=observation_id,
                role=role,
                line=line,
                offset_interval_px=FiniteInterval(
                    line.offset_px - normalized_uncertainty,
                    line.offset_px + normalized_uncertainty,
                ),
                fit_residual_px=float(
                    np.median(np.abs(residuals))
                ),
                angle_interval_degrees=FiniteInterval(
                    angle - angle_uncertainty,
                    angle + angle_uncertainty,
                ),
                trace_support_count=len(selected),
                queried_trace_count=len(queried_traces),
                continuous_support_fraction=continuous_fraction,
                transition_ids=transition_ids,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.PHOTO_BOUNDARY,
                    observation_id=observation_id,
                    dependencies=(MeasurementIdentity.BASE_GRAY,),
                    description=(
                        "deterministic weighted-Huber source-coordinate "
                        "photo-boundary line family"
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
                        for point in selected_inliers
                    )
                    / len(selected_inliers)
                ),
                left_background_preference_fraction=(
                    sum(
                        point.transition.left_texture_mean
                        <= point.transition.right_texture_mean
                        for point in selected_inliers
                    )
                    / len(selected_inliers)
                ),
                right_background_preference_fraction=(
                    sum(
                        point.transition.right_texture_mean
                        <= point.transition.left_texture_mean
                        for point in selected_inliers
                    )
                    / len(selected_inliers)
                ),
            )
        )
    return deduplicate_boundary_observations(
        tuple(observations),
        boundary_axis_scale_px_per_mm,
        spec,
    )


def _intervals_overlap(
    left: FiniteInterval,
    right: FiniteInterval,
) -> bool:
    return (
        left.minimum <= right.maximum
        and right.minimum <= left.maximum
    )


def boundary_observations_equivalent(
    left: PhotoBoundaryObservation,
    right: PhotoBoundaryObservation,
    boundary_axis_scale_px_per_mm: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> bool:
    tolerance = max(
        1.0,
        spec.geometry_equivalence_mm
        * boundary_axis_scale_px_per_mm.maximum,
    )
    return (
        left.role == right.role
        and abs(left.line.offset_px - right.line.offset_px) <= tolerance
        and _intervals_overlap(
            left.angle_interval_degrees,
            right.angle_interval_degrees,
        )
    )


def deduplicate_boundary_observations(
    observations: tuple[PhotoBoundaryObservation, ...],
    boundary_axis_scale_px_per_mm: PositiveInterval,
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
) -> tuple[PhotoBoundaryObservation, ...]:
    """Physical dedup precedes every candidate-count decision."""

    tolerance = max(
        1.0,
        spec.geometry_equivalence_mm
        * boundary_axis_scale_px_per_mm.maximum,
    )
    retained: list[PhotoBoundaryObservation] = []
    for observation in sorted(
        observations,
        key=lambda item: (
            item.line.offset_px,
            item.fit_residual_px,
            str(item.observation_id),
        ),
    ):
        equivalent_index = None
        for index in range(len(retained) - 1, -1, -1):
            existing = retained[index]
            if (
                observation.line.offset_px
                - existing.line.offset_px
                > 2.0 * tolerance
            ):
                break
            if boundary_observations_equivalent(
                existing,
                observation,
                boundary_axis_scale_px_per_mm,
                spec,
            ):
                equivalent_index = index
                break
        if equivalent_index is None:
            retained.append(observation)
            continue
        existing = retained[equivalent_index]
        preferred = min(
            (existing, observation),
            key=lambda item: (
                -item.trace_support_count,
                item.measurement_uncertainty_px,
                item.fit_residual_px,
                str(item.observation_id),
            ),
        )
        retained[equivalent_index] = preferred
    return tuple(
        sorted(
            retained,
            key=lambda item: (
                item.line.offset_px,
                str(item.observation_id),
            ),
        )
    )
