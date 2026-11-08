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
from .broad_material_transition_measurement import (
    measure_broad_material_transitions,
)
from .broad_material_association import associate_registered_broad_material
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
    trace_storage_bytes,
    scalar_trace_buffer_reservation,
    window_prefix_cache_bytes,
    transition_peak_scratch_bytes,
)
from .transition_peak_capture import TransitionPeakCapture, peak_source_receipt
from .physical_identity import physical_observation_id
from .native_background_texture import native_background_texture_query, measure_native_background_texture


_BASELINE_WINDOWS = (
    (QueryPurpose.CROSS_BASELINE, frozenset((QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR))),
    (QueryPurpose.SEQUENCE_BASELINE, frozenset((QueryPurpose.SEQUENCE_ANCHOR_WINDOW,))),
)
_BASELINE_PURPOSES = frozenset(purpose for purpose, _windows in _BASELINE_WINDOWS)
_PEAK_SOURCE_WINDOWS = frozenset(purpose for _baseline, windows in _BASELINE_WINDOWS for purpose in windows)


def make_photo_boundary_measurement_field(
    source_gray: np.ndarray,
    layout: str,
    *,
    source_rgb: np.ndarray,
) -> PhotoBoundaryMeasurementField:
    return PhotoBoundaryMeasurementField(source_gray, layout, source_rgb=source_rgb)


def _measure_query(
    field: PhotoBoundaryMeasurementField,
    query: PhotoBoundaryMeasurementQuery,
    spec: PhotoBoundaryMeasurementSpec,
    *,
    premeasured: tuple[TraceMeasurement, ...] | None = None,
    retained_temporary_bytes: int = 0,
    premeasurement_peak_bytes: int = 0,
    peak_source_budget_bytes: int | None = None,
    peak_source_preflight_completed: bool = True,
    peak_source_planning_value_visit_bound: int = 0,
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
    broad_material_association = None
    peak_temporary = max(retained_temporary_bytes, premeasurement_peak_bytes)
    pixel_query_count = 0
    completed_coordinates = 0
    completed_traces = 0
    source_traces = []
    source_capture = (TransitionPeakCapture(
        32 * 1024 * 1024 + 10 * field.source_extent.width * field.source_extent.height
        if peak_source_budget_bytes is None else peak_source_budget_bytes)
        if query.purpose in _PEAK_SOURCE_WINDOWS and peak_source_preflight_completed else None)
    source_preflight_skipped = (query.purpose in _PEAK_SOURCE_WINDOWS or query.purpose in _BASELINE_PURPOSES
                               ) and not peak_source_preflight_completed
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
                measured = measure_trace(values, interval, scale, spec,
                    peak_source_context=((field.source_id, field.source_extent, query.boundary_axis, trace)
                        if source_capture is not None and source_capture.complete else None))
            else:
                measured = premeasured[trace_ordinal]
            if measured.peak_source is not None and (premeasured is None or query.purpose in _BASELINE_PURPOSES):
                source_traces.append(measured.peak_source)
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
                retained_temporary_bytes + (0 if premeasured is not None else trace_storage_bytes(measured))
                + (0 if query.purpose in _BASELINE_PURPOSES else
                   transition_peak_scratch_bytes(int(measured.coordinates.size))),
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
                peak_source_capture=source_capture,
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
                        texture_sample_coordinate_px=int(measured.coordinates[peak.coordinate_index]),
                        peak_source=peak.source_reference,
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
            ) = measure_broad_material_transitions(
                query,
                premeasured,
                spec,
            )
            broad_material_association = associate_registered_broad_material(query, broad_material_transitions, spec)
            peak_temporary = max(
                peak_temporary,
                retained_temporary_bytes + broad_material_temporary,
                retained_temporary_bytes + (0 if broad_material_association is None
                                            else broad_material_association.temporary_numeric_bytes),
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
        _, receipt, sources, groups = peak_source_receipt((), receipt, source_traces, source_capture,
            preflight_skipped=source_preflight_skipped, planning_value_visit_bound=peak_source_planning_value_visit_bound)
        return PhotoBoundaryMeasurementSet(
            query=query,
            state=EvidenceState.UNAVAILABLE,
            transitions=(),
            cross_height_transitions=(),
            coverage=receipt,
            broad_material_transitions=(),
            peak_trace_sources=sources, peak_source_groups=groups,
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
    transitions, receipt, sources, groups = peak_source_receipt(
        tuple(transitions), receipt, source_traces, source_capture, preflight_skipped=source_preflight_skipped,
        planning_value_visit_bound=peak_source_planning_value_visit_bound)
    return PhotoBoundaryMeasurementSet(
        query=query,
        state=EvidenceState.SUPPORTED,
        transitions=transitions,
        cross_height_transitions=cross_height_transitions,
        coverage=receipt,
        broad_material_transitions=broad_material_transitions,
        broad_material_association=broad_material_association,
        peak_trace_sources=sources, peak_source_groups=groups,
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


def _premeasure_registered_windows(
    field: PhotoBoundaryMeasurementField,
    baseline: PhotoBoundaryMeasurementQuery,
    windows: tuple[PhotoBoundaryMeasurementQuery, ...],
    spec: PhotoBoundaryMeasurementSpec,
    capture_peak_sources: bool = True,
    *,
    prefix_cache_budget_bytes: int | None = None,
) -> tuple[dict[str, tuple[TraceMeasurement, ...]], int, int]:
    queries = (baseline, *windows)
    first = baseline
    values_by_query: dict[str, list[TraceMeasurement]] = {
        query.query_id: [] for query in queries
    }
    scale = first.boundary_axis_scale_px_per_mm.maximum
    retained_bytes = 0
    peak_bytes = 0
    cache_budget = (10 * field.source_extent.width * field.source_extent.height + 32 * 1024 * 1024
                    if prefix_cache_budget_bytes is None else prefix_cache_budget_bytes)
    broad = baseline.purpose == QueryPurpose.SEQUENCE_BASELINE
    for trace_ordinal, trace in enumerate(first.trace_positions_px):
        values = (
            field.source_gray[trace, :]
            if first.boundary_axis == BoundaryAxis.X
            else field.source_gray[:, trace]
        )
        capacity = 0
        if broad:
            required = window_prefix_cache_bytes(values.size)
            # L coordinates conservatively cover even an unclipped full row.
            # Only the optional memoization is disabled when the unchanged
            # kernel plus cache cannot fit the source's remaining pool.
            need = scalar_trace_buffer_reservation(values.size, values.size,
                prefix_cache_capacity_bytes=required)
            if retained_bytes + need <= cache_budget:
                capacity = required
        measured = measure_trace(
            values,
            baseline.search_intervals_px[trace_ordinal],
            scale,
            spec,
            include_broad_material=broad,
            prefix_cache_capacity_bytes=capacity,
            peak_source_context=((field.source_id, field.source_extent, first.boundary_axis, trace)
                if capture_peak_sources else None),
        )
        retained_bytes += trace_storage_bytes(measured)
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
    # Reserve all later extraction stages before a window captures provenance.
    # An aggregate owns eight float64 response arrays plus int32 coordinates;
    # its source traces remain in retained_bytes throughout consumption.
    peak_bytes = max(peak_bytes,retained_bytes+max((
        transition_peak_scratch_bytes(int(item.coordinates.size))
        +(68*int(item.coordinates.size) if query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW else 0)
        for query in windows for item in values_by_query[query.query_id]),default=0))
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
    existing_pixel_query_count: int = 0,
    max_pixel_query_count: int | None = None,
    max_peak_temporary_bytes: int | None = None,
    existing_peak_source_retained_bytes: int = 0,
    existing_peak_source_value_visit_bound: int = 0,
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
    baseline_groups = registered_baseline_query_groups(queries)
    groups = {
        query.query_id: (baseline, windows)
        for baseline, windows in baseline_groups
        for query in (baseline, *windows)
    }
    results = {}
    source_limit = (10 * field.source_extent.width * field.source_extent.height + 32 * 1024 * 1024
                    if max_peak_temporary_bytes is None else max_peak_temporary_bytes)
    origin_retained = existing_peak_source_retained_bytes
    pixel_limit = 128 * field.source_extent.width * field.source_extent.height if max_pixel_query_count is None else max_pixel_query_count
    if any(type(value) is not int or value < 0 for value in (existing_pixel_query_count, pixel_limit, source_limit)):
        raise ValueError("registered measurement requires finite source work bounds")
    source_visits, registered_pixels = 0, existing_pixel_query_count
    for query in queries:
        coordinates = sum(max(0, math.floor(interval.maximum) - math.ceil(interval.minimum) + 1)
                          for interval in query.search_intervals_px)
        is_baseline = query.purpose in _BASELINE_PURPOSES
        radius = spec.local_measurement_work_radius_px(query.boundary_axis_scale_px_per_mm.maximum)
        registered_pixels += coordinates * (2 * radius + 2 if is_baseline or query.query_id not in groups else 1)
        if query.purpose == QueryPurpose.CROSS_BASELINE:
            source_visits += 5 * coordinates + 32 * len(query.trace_positions_px)
        elif query.purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR):
            source_visits += 256 * coordinates + 32
    capture_cross_sources = registered_pixels + existing_peak_source_value_visit_bound + source_visits <= pixel_limit

    # Preserve the existing Cross facts and native-texture reservation before
    # optional Sequence provenance uses the same source pool. Registration and
    # returned order stay fixed; neither phase reads candidate geometry.
    cross_ids = frozenset(q.query_id for baseline, windows in baseline_groups
                         if baseline.purpose == QueryPurpose.CROSS_BASELINE for q in (baseline, *windows))
    execution = tuple(q for q in queries if q.query_id in cross_ids) + tuple(
        q for q in queries if q.query_id not in cross_ids)

    def retain(result):
        nonlocal origin_retained
        result = replace(result, coverage=replace(result.coverage,
            peak_temporary_bytes=result.coverage.peak_temporary_bytes + origin_retained))
        origin_retained += result.coverage.peak_source_retained_bytes
        results[result.query.query_id] = result
    for query in execution:
        if query.query_id in results:
            continue
        group = groups.get(query.query_id)
        if group is None:
            retain(_measure_query(field, query, spec,
                peak_source_budget_bytes=0))
            continue
        baseline, windows = group
        capture_sources = capture_cross_sources
        source_preflight_completed = True
        if baseline.purpose == QueryPurpose.SEQUENCE_BASELINE:
            used_visits = existing_peak_source_value_visit_bound + sum(
                m.coverage.peak_source_value_visit_bound for m in results.values())
            # Length-only admission precedes the new domain/buffer scans. An
            # exhausted original pool cannot pay their fixed per-trace/domain
            # scan and per-window capture preflights.
            planning_visits = 32 * len(baseline.trace_positions_px)
            source_preflight_completed = pixel_limit - registered_pixels - used_visits >= planning_visits + 32 * len(windows)
            capture_sources = False
            if source_preflight_completed:
                source_visits = (planning_visits + 5 * sum(max(0, math.floor(i.maximum) - math.ceil(i.minimum) + 1)
                                        for i in baseline.search_intervals_px)
                                 + 32 * len(baseline.trace_positions_px))
                source_visits += sum(256 * sum(max(0, math.floor(i.maximum) - math.ceil(i.minimum) + 1)
                                              for i in q.search_intervals_px) + 32 for q in windows)
                # Complete per-trace construction bounds include broad and
                # optional prefixes, over-reserving all construction scratch.
                length = field.source_extent.width if baseline.boundary_axis == BoundaryAxis.X else field.source_extent.height
                cache = window_prefix_cache_bytes(length)
                buffers = sum(scalar_trace_buffer_reservation(length,
                    max(0, math.floor(i.maximum) - math.ceil(i.minimum) + 1),
                    prefix_cache_capacity_bytes=cache) for i in baseline.search_intervals_px)
                capture_sources = (registered_pixels + used_visits + source_visits <= pixel_limit
                                   and origin_retained + buffers <= source_limit)
        premeasured, retained_bytes, peak_bytes = _premeasure_registered_windows(
            field, baseline, windows, spec, capture_sources,
            prefix_cache_budget_bytes=max(0, source_limit-origin_retained),
        )
        for member in sorted((baseline, *windows), key=lambda item: item.registration_index):
            retain(_measure_query(
                field, member, spec, premeasured=premeasured[member.query_id],
                retained_temporary_bytes=retained_bytes,
                premeasurement_peak_bytes=peak_bytes,
                peak_source_budget_bytes=(max(0, source_limit - origin_retained - peak_bytes) if capture_sources else 0),
                peak_source_preflight_completed=source_preflight_completed,
                peak_source_planning_value_visit_bound=(32 * len(baseline.trace_positions_px)
                    if source_preflight_completed and member is baseline
                    and baseline.purpose == QueryPurpose.SEQUENCE_BASELINE else 0),
            ))
        # Each lattice is fully consumed before another is premeasured.
        # Reports retain scalar/transition facts, never these pixel arrays.
        del premeasured
        if baseline.purpose == QueryPurpose.CROSS_BASELINE:
            members = tuple(results[q.query_id] for q in queries if q.query_id in cross_ids)
            prior_pixels = sum(m.coverage.pixel_query_count for m in members)
            members = _add_native_background_textures(field, members, spec,
                existing_pixel_query_count=registered_pixels-prior_pixels,
                max_pixel_query_count=pixel_limit, max_peak_temporary_bytes=source_limit,
                existing_peak_source_retained_bytes=existing_peak_source_retained_bytes,
                existing_peak_source_value_visit_bound=existing_peak_source_value_visit_bound)
            results.update((m.query.query_id, m) for m in members)
            registered_pixels += sum(m.coverage.pixel_query_count for m in members) - prior_pixels
            origin_retained = existing_peak_source_retained_bytes + sum(
                m.coverage.peak_source_retained_bytes for m in results.values())
    return tuple(results[query.query_id] for query in queries)


def _add_native_background_textures(field, measurements, spec, *, existing_pixel_query_count=0,
                                  max_pixel_query_count=None, max_peak_temporary_bytes=None,
                                  existing_peak_source_retained_bytes=0,
                                  existing_peak_source_value_visit_bound=0):
    pixels = field.source_extent.width * field.source_extent.height
    pixel_limit = 128 * pixels if max_pixel_query_count is None else max_pixel_query_count
    memory_limit = 10 * pixels + 32 * 1024 * 1024 if max_peak_temporary_bytes is None else max_peak_temporary_bytes
    if any(type(value) is not int or value < 0 for value in (existing_pixel_query_count, pixel_limit, memory_limit)):
        raise ValueError("native background texture requires finite source work bounds")
    # Freeze every window from the full raw transition batch, before any new
    # pixel read. Source bounds and work failure cannot select a useful prefix.
    plans = {m.query.query_id: tuple(native_background_texture_query(field.source_extent, m.query, t, spec)
                                    for t in m.transitions)
             for m in measurements if m.state == EvidenceState.SUPPORTED
             and m.query.purpose in (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR)}
    extra = sum(q.pixel_query_count for batch in plans.values() for q in batch)
    origin_retained = existing_peak_source_retained_bytes + sum(m.coverage.peak_source_retained_bytes for m in measurements)
    peak = max(origin_retained + max((q.peak_temporary_bytes for batch in plans.values() for q in batch), default=0),
               max((m.coverage.peak_temporary_bytes for m in measurements), default=0))
    bound_exceeded = (existing_pixel_query_count + sum(m.coverage.pixel_query_count for m in measurements)
                      + existing_peak_source_value_visit_bound
                      + sum(m.coverage.peak_source_value_visit_bound for m in measurements)
                      + extra > pixel_limit or peak > memory_limit)
    results = []
    for measured in measurements:
        batch = plans.get(measured.query.query_id)
        if batch is None:
            results.append(measured)
            continue
        count = len(batch)
        if bound_exceeded:
            coverage = replace(measured.coverage, complete=False, native_texture_query_count=count,
                native_texture_completed_count=0, native_texture_bound_exceeded=True,
                peak_source_reference_count=0,
                peak_source_retained_bytes=(measured.coverage.peak_source_retained_bytes
                    - sum(t.peak_source.retained_bytes for t in measured.transitions if t.peak_source is not None)))
            results.append(replace(measured, state=EvidenceState.UNAVAILABLE, transitions=(), coverage=coverage))
            continue
        transitions = tuple(replace(t, native_background_texture=measure_native_background_texture(field, q))
                            for t, q in zip(measured.transitions, batch, strict=True))
        work = sum(q.pixel_query_count for q in batch)
        total = measured.coverage.pixel_query_count + work
        coverage = replace(measured.coverage, pixel_query_count=total,
            streaming_block_count=max(1, math.ceil(total / spec.maximum_streaming_block_pixels)),
            peak_temporary_bytes=max(measured.coverage.peak_temporary_bytes,
                                     origin_retained + max((q.peak_temporary_bytes for q in batch), default=0)),
            native_texture_query_count=count, native_texture_completed_count=count,
            native_texture_pixel_query_count=work)
        results.append(replace(measured, transitions=transitions, coverage=coverage))
    return tuple(results)
