"""Execute bounded, pre-registered pixel measurement queries."""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np

from ...domain import EvidenceState, FiniteInterval
from .measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .cross_height_transition_measurement import (
    measure_cross_height_transition_regions,
)
from .model import (
    BoundaryAxis,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
    QueryPurpose,
)
from .registered_transition_measurement import (
    TraceMeasurement,
    measure_trace,
    measured_transition_peaks,
)
from .physical_identity import physical_observation_id


def make_photo_boundary_measurement_field(
    source_gray: np.ndarray,
    layout: str,
) -> PhotoBoundaryMeasurementField:
    return PhotoBoundaryMeasurementField(source_gray, layout)


def _measure_query(
    field: PhotoBoundaryMeasurementField,
    query: PhotoBoundaryMeasurementQuery,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    premeasured: tuple[TraceMeasurement, ...] | None = None,
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
    cross_height_transitions = ()
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
            math.ceil((spec.local_window_mm + spec.transition_gap_mm) * scale)
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
            if premeasured is None:
                values = (
                    field.source_gray[trace, :]
                    if query.boundary_axis == BoundaryAxis.X
                    else field.source_gray[:, trace]
                )
                measured = measure_trace(values, interval, scale, spec)
            else:
                measured = premeasured[trace_ordinal]
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
                if premeasured is None
                or query.purpose == QueryPurpose.SEQUENCE_BASELINE
                else 1
            )
            peak_temporary = max(
                peak_temporary,
                measured.temporary_bytes,
            )
            peaks = (
                ()
                if query.purpose == QueryPurpose.SEQUENCE_BASELINE
                else measured_transition_peaks(
                measured,
                spec,
                split_gradient_reversals=query.purpose
                in {
                    QueryPurpose.TOP_CORRIDOR,
                    QueryPurpose.BOTTOM_CORRIDOR,
                },
                )
            )
            for peak in peaks:
                if not ownership.contains(
                    float(measured.coordinates[peak.coordinate_index]),
                    epsilon=1.0e-12,
                ):
                    continue
                transition_id = physical_observation_id(
                    "photo-transition",
                    query.query_id,
                    trace_ordinal,
                    f"{peak.localization_interval.minimum:.6f}",
                    f"{peak.localization_interval.maximum:.6f}",
                    f"{peak.physical_position_interval.minimum:.6f}",
                    f"{peak.physical_position_interval.maximum:.6f}",
                )
                transitions.append(
                    PhotoBoundaryTransition(
                        transition_id=transition_id,
                        query_id=query.query_id,
                        trace_ordinal=trace_ordinal,
                        trace_coordinate_px=trace,
                        canonical_coordinate_px=peak.canonical_coordinate,
                        localization_interval_px=peak.localization_interval,
                        physical_position_interval_px=(
                            peak.physical_position_interval
                        ),
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
                )
        if premeasured is not None:
            (
                cross_height_transitions,
                cross_height_temporary,
            ) = measure_cross_height_transition_regions(
                query,
                premeasured,
                spec,
            )
            peak_temporary = max(
                peak_temporary,
                cross_height_temporary,
            )
    except Exception:
        receipt = _coverage_receipt(
            query,
            spec,
            registered_coordinate_count=registered_coordinate_count,
            completed_coordinates=completed_coordinates,
            completed_traces=completed_traces,
            pixel_query_count=pixel_query_count,
            peak_temporary=peak_temporary,
            complete=False,
        )
        return PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.UNAVAILABLE,
            transitions=(),
            cross_height_transitions=(),
            coverage=receipt,
        )
    receipt = _coverage_receipt(
        query,
        spec,
        registered_coordinate_count=registered_coordinate_count,
        completed_coordinates=completed_coordinates,
        completed_traces=completed_traces,
        pixel_query_count=pixel_query_count,
        peak_temporary=peak_temporary,
        complete=True,
    )
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=EvidenceState.SUPPORTED,
        transitions=tuple(transitions),
        cross_height_transitions=cross_height_transitions,
        coverage=receipt,
    )


def _slice_trace_measurement(
    measured: TraceMeasurement,
    interval: FiniteInterval,
) -> TraceMeasurement:
    retained = slice(
        measured.coordinates.searchsorted(
            math.ceil(interval.minimum), side="left"
        ),
        measured.coordinates.searchsorted(
            math.floor(interval.maximum), side="right"
        ),
    )
    return replace(
        measured,
        coordinates=measured.coordinates[retained],
        gradient_z=measured.gradient_z[retained],
        tone_z=measured.tone_z[retained],
        texture_z=measured.texture_z[retained],
        signed_gradient=measured.signed_gradient[retained],
        left_tone=measured.left_tone[retained],
        right_tone=measured.right_tone[retained],
        left_texture=measured.left_texture[retained],
        right_texture=measured.right_texture[retained],
    )


def _premeasure_sequence_windows(
    field: PhotoBoundaryMeasurementField,
    baseline: PhotoBoundaryMeasurementQuery,
    windows: tuple[PhotoBoundaryMeasurementQuery, ...],
    spec: PhotoBoundaryMeasurementSpec,
) -> dict[str, tuple[TraceMeasurement, ...]]:
    queries = (baseline, *windows)
    first = baseline
    if any(
        query.boundary_axis != first.boundary_axis
        or query.trace_positions_px != first.trace_positions_px
        or query.boundary_axis_scale_px_per_mm
        != first.boundary_axis_scale_px_per_mm
        for query in queries[1:]
    ):
        raise ValueError("sequence baseline and windows must share one trace lattice")
    values_by_query: dict[str, list[TraceMeasurement]] = {
        query.query_id: [] for query in queries
    }
    scale = first.boundary_axis_scale_px_per_mm.maximum
    for trace_ordinal, trace in enumerate(first.trace_positions_px):
        values = (
            field.source_gray[trace, :]
            if first.boundary_axis == BoundaryAxis.X
            else field.source_gray[:, trace]
        )
        measured = measure_trace(
            values,
            baseline.search_intervals_px[trace_ordinal],
            scale,
            spec,
        )
        values_by_query[baseline.query_id].append(measured)
        for query in windows:
            values_by_query[query.query_id].append(
                _slice_trace_measurement(
                    measured,
                    query.search_intervals_px[trace_ordinal],
                )
            )
    return {
        identity: tuple(values)
        for identity, values in values_by_query.items()
    }


def _coverage_receipt(
    query: PhotoBoundaryMeasurementQuery,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    registered_coordinate_count: int,
    completed_coordinates: int,
    completed_traces: int,
    pixel_query_count: int,
    peak_temporary: int,
    complete: bool,
) -> PhotoBoundaryCoverageReceipt:
    return PhotoBoundaryCoverageReceipt(
        query_id=query.query_id,
        registered_trace_count=len(query.trace_positions_px),
        completed_trace_count=completed_traces,
        registered_coordinate_count=registered_coordinate_count,
        completed_coordinate_count=completed_coordinates,
        pixel_query_count=pixel_query_count,
        streaming_block_count=(
            0
            if pixel_query_count == 0 and not complete
            else max(
                1,
                int(
                    math.ceil(
                        max(1, pixel_query_count)
                        / spec.maximum_streaming_block_pixels
                    )
                ),
            )
        ),
        peak_temporary_bytes=peak_temporary,
        complete=complete,
    )


def measure_registered_queries(
    field: PhotoBoundaryMeasurementField,
    queries: tuple[PhotoBoundaryMeasurementQuery, ...],
    spec: PhotoBoundaryMeasurementSpec = PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    *,
    registration_start: int = 0,
) -> tuple[PhotoBoundaryMeasurementSet, ...]:
    """Execute the complete pre-registered query lattice deterministically."""

    if registration_start < 0:
        raise ValueError("measurement registration start cannot be negative")
    identities = tuple(query.query_id for query in queries)
    if len(set(identities)) != len(identities):
        raise ValueError("registered measurement queries must be unique")
    if tuple(query.registration_index for query in queries) != tuple(
        range(registration_start, registration_start + len(queries))
    ):
        raise ValueError("measurement queries must be completely pre-registered")
    sequence_baselines = tuple(
        query
        for query in queries
        if query.purpose == QueryPurpose.SEQUENCE_BASELINE
    )
    sequence_windows = tuple(
        query
        for query in queries
        if query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW
    )
    if len(sequence_baselines) != (1 if sequence_windows else 0):
        raise ValueError("sequence windows require one registered baseline")
    premeasured = (
        {}
        if not sequence_windows
        else _premeasure_sequence_windows(
            field,
            sequence_baselines[0],
            sequence_windows,
            spec,
        )
    )
    return tuple(
        _measure_query(
            field,
            query,
            spec,
            premeasured=premeasured.get(query.query_id),
        )
        for query in queries
    )
