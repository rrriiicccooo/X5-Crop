"""Execute bounded, pre-registered pixel measurement queries."""

from __future__ import annotations

import math

import numpy as np

from ...domain import EvidenceState
from .measurement_model import (
    PhotoBoundaryCoverageReceipt,
    PhotoBoundaryMeasurementField,
    PhotoBoundaryMeasurementQuery,
    PhotoBoundaryMeasurementSet,
    PhotoBoundaryTransition,
)
from .model import (
    BoundaryAxis,
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    PhotoBoundaryMeasurementSpec,
    QueryPurpose,
)
from .registered_transition_measurement import (
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
            values = (
                field.source_gray[trace, :]
                if query.boundary_axis == BoundaryAxis.X
                else field.source_gray[:, trace]
            )
            measured = measure_trace(values, interval, scale, spec)
            coordinate_count = max(
                0,
                int(math.floor(interval.maximum))
                - int(math.ceil(interval.minimum))
                + 1,
            )
            completed_coordinates += coordinate_count
            completed_traces += 1
            pixel_query_count += coordinate_count * (2 * local_radius + 2)
            peak_temporary = max(
                peak_temporary,
                measured.temporary_bytes,
            )
            for peak in measured_transition_peaks(
                measured,
                spec,
                split_gradient_reversals=query.purpose
                in {
                    QueryPurpose.TOP_CORRIDOR,
                    QueryPurpose.BOTTOM_CORRIDOR,
                },
            ):
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
        coverage=receipt,
    )


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
