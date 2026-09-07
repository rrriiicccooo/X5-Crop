"""Execute bounded, pre-registered pixel measurement queries."""

from __future__ import annotations

from dataclasses import fields, replace
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
from .broad_material_transition_measurement import (
    measure_broad_material_transition_regions,
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


_BASELINE_WINDOWS = (
    (QueryPurpose.CROSS_BASELINE, frozenset((QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR))),
    (QueryPurpose.SEQUENCE_BASELINE, frozenset((QueryPurpose.SEQUENCE_ANCHOR_WINDOW,))),
)
_BASELINE_PURPOSES = frozenset(purpose for purpose, _windows in _BASELINE_WINDOWS)


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
    retained_temporary_bytes: int = 0,
    premeasurement_peak_bytes: int = 0,
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
    broad_material_transitions = ()
    peak_temporary = max(retained_temporary_bytes, premeasurement_peak_bytes)
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
        local_radius = spec.local_measurement_work_radius_px(scale)
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
                or query.purpose in _BASELINE_PURPOSES
                else 1
            )
            peak_temporary = max(
                peak_temporary,
                retained_temporary_bytes + measured.temporary_bytes,
            )
            peaks = (
                ()
                if query.purpose in _BASELINE_PURPOSES
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
                retained_temporary_bytes + cross_height_temporary,
            )
            (
                broad_material_transitions,
                broad_material_temporary,
            ) = measure_broad_material_transition_regions(
                query,
                premeasured,
                spec,
            )
            peak_temporary = max(
                peak_temporary,
                retained_temporary_bytes + broad_material_temporary,
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
            broad_material_transitions=(),
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
        broad_material_transitions=broad_material_transitions,
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
    broad = measured.broad_material
    sliced_broad = (
        None
        if broad is None
        else replace(
            broad,
            signed_tone_by_scale=tuple(
                item[retained] for item in broad.signed_tone_by_scale
            ),
            left_tone_by_scale=tuple(
                item[retained] for item in broad.left_tone_by_scale
            ),
            right_tone_by_scale=tuple(
                item[retained] for item in broad.right_tone_by_scale
            ),
            left_texture_by_scale=tuple(
                item[retained] for item in broad.left_texture_by_scale
            ),
            right_texture_by_scale=tuple(
                item[retained] for item in broad.right_texture_by_scale
            ),
            observable=broad.observable[retained],
            supported=broad.supported[retained],
            polarity=broad.polarity[retained],
            background_side=broad.background_side[retained],
            contrast_lower_bound=broad.contrast_lower_bound[retained],
            contrast_z=broad.contrast_z[retained],
            background_uniformity_upper_bound=(
                broad.background_uniformity_upper_bound[retained]
            ),
            left_tone=broad.left_tone[retained],
            right_tone=broad.right_tone[retained],
            left_texture=broad.left_texture[retained],
            right_texture=broad.right_texture[retained],
        )
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
        broad_material=sliced_broad,
    )


def _trace_storage_bytes(measured: TraceMeasurement) -> int:
    """Count retained NumPy storage once; slices and broad aliases are views."""

    buffers: dict[int, int] = {}
    for record in (measured, measured.broad_material):
        if record is None:
            continue
        for field in fields(record):
            value = getattr(record, field.name)
            for array in (value if isinstance(value, tuple) else (value,)):
                if not isinstance(array, np.ndarray):
                    continue
                root = array
                while isinstance(root.base, np.ndarray):
                    root = root.base
                buffers[id(root)] = root.nbytes
    return sum(buffers.values())


def _premeasure_registered_windows(
    field: PhotoBoundaryMeasurementField,
    baseline: PhotoBoundaryMeasurementQuery,
    windows: tuple[PhotoBoundaryMeasurementQuery, ...],
    spec: PhotoBoundaryMeasurementSpec,
) -> tuple[dict[str, tuple[TraceMeasurement, ...]], int, int]:
    queries = (baseline, *windows)
    first = baseline
    values_by_query: dict[str, list[TraceMeasurement]] = {
        query.query_id: [] for query in queries
    }
    scale = first.boundary_axis_scale_px_per_mm.maximum
    retained_bytes = 0
    peak_bytes = 0
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
            include_broad_material=baseline.purpose == QueryPurpose.SEQUENCE_BASELINE,
        )
        retained_bytes += _trace_storage_bytes(measured)
        # All earlier traces remain live. The per-trace work allowance is
        # additional to retained storage, conservatively covering overlap
        # during construction/consumption rather than pretending one trace
        # is the complete batch. This is not process RSS.
        peak_bytes = max(peak_bytes, retained_bytes + measured.temporary_bytes)
        values_by_query[baseline.query_id].append(measured)
        for query in windows:
            values_by_query[query.query_id].append(
                _slice_trace_measurement(
                    measured,
                    query.search_intervals_px[trace_ordinal],
                )
            )
    return (
        {identity: tuple(values) for identity, values in values_by_query.items()},
        retained_bytes,
        peak_bytes,
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


def registered_baseline_query_groups(
    queries: tuple[PhotoBoundaryMeasurementQuery, ...],
) -> tuple[tuple[PhotoBoundaryMeasurementQuery, tuple[PhotoBoundaryMeasurementQuery, ...]], ...]:
    """Compile and validate the two fixed, candidate-independent lattices."""

    groups = []
    for purpose, window_purposes in _BASELINE_WINDOWS:
        baselines = tuple(query for query in queries if query.purpose == purpose)
        windows = tuple(query for query in queries if query.purpose in window_purposes)
        if len(baselines) != (1 if windows else 0):
            raise ValueError(f"{purpose.value} windows require one registered baseline")
        if not windows:
            continue
        baseline = baselines[0]
        if any(
            query.boundary_axis != baseline.boundary_axis
            or query.lane_id != baseline.lane_id
            or query.trace_positions_px != baseline.trace_positions_px
            or query.boundary_axis_scale_px_per_mm != baseline.boundary_axis_scale_px_per_mm
            or query.trace_axis_scale_px_per_mm != baseline.trace_axis_scale_px_per_mm
            for query in windows
        ):
            raise ValueError("baseline and windows must share one lane and trace lattice")
        if any(
            window.minimum < full.minimum or window.maximum > full.maximum
            for query in windows
            for window, full in zip(query.search_intervals_px, baseline.search_intervals_px, strict=True)
        ):
            raise ValueError("baseline must contain every registered window")
        groups.append((baseline, windows))
    return tuple(groups)


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
    groups = {
        query.query_id: (baseline, windows)
        for baseline, windows in registered_baseline_query_groups(queries)
        for query in (baseline, *windows)
    }
    results = {}
    for query in queries:
        if query.query_id in results:
            continue
        group = groups.get(query.query_id)
        if group is None:
            results[query.query_id] = _measure_query(field, query, spec)
            continue
        baseline, windows = group
        premeasured, retained_bytes, peak_bytes = _premeasure_registered_windows(
            field, baseline, windows, spec,
        )
        for member in sorted((baseline, *windows), key=lambda item: item.registration_index):
            results[member.query_id] = _measure_query(
                field, member, spec, premeasured=premeasured[member.query_id],
                retained_temporary_bytes=retained_bytes,
                premeasurement_peak_bytes=peak_bytes,
            )
        # Each lattice is fully consumed before another is premeasured.
        # Reports retain scalar/transition facts, never these pixel arrays.
        del premeasured
    return tuple(results[query.query_id] for query in queries)
