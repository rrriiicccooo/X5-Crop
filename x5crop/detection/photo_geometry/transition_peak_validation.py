"""Bind peak provenance to the registered source and normalization queries."""

import math

from ...domain import FiniteInterval
from .model import PHOTO_BOUNDARY_MEASUREMENT_SPEC, QueryPurpose


def validate_transition_peak_reference(transition, groups):
    reference = transition.peak_source
    if reference is None:
        return
    group = groups.get(reference.group_id)
    if group is None or group.source.trace_coordinate_px != transition.trace_coordinate_px:
        raise ValueError("transition lost its original measured peak group")
    reference.validate_group(group)
    candidates, index = group.candidate_peak_coordinates_px, reference.candidate_ordinal
    low = (group.credible_group_domain_px[0] - .5 if index == 0 else
           math.floor((candidates[index-1] + candidates[index]) / 2) + .5)
    high = (group.credible_group_domain_px[1] + .5 if index + 1 == len(candidates) else
            math.floor((candidates[index] + candidates[index+1]) / 2) + .5)
    if transition.physical_position_interval_px != FiniteInterval(low, high):
        raise ValueError("transition changed its original polarity partition")


def validate_peak_source_measurements(measurements, *, source_id, source_extent, coarse_support=None):
    """No pixel replay: validate frozen contexts, full views and raw references."""
    by_purpose = {item.query.purpose: item for item in measurements}
    spec = PHOTO_BOUNDARY_MEASUREMENT_SPEC
    for measurement in measurements:
        query = measurement.query
        own = {source.trace_coordinate_px: source for source in measurement.peak_trace_sources}
        if len(own) != len(measurement.peak_trace_sources):
            raise ValueError("normalization source was registered twice on one trace")
        interval_by_trace = dict(zip(query.trace_positions_px, query.search_intervals_px, strict=True))
        scale = query.boundary_axis_scale_px_per_mm.maximum
        window, gap = spec.local_window_px(scale), spec.transition_gap_px(scale)
        axis_extent = source_extent.width if query.boundary_axis.value == "x" else source_extent.height
        for source in (*measurement.peak_trace_sources, *(group.source for group in measurement.peak_source_groups)):
            if (source.source_id != source_id or source.source_extent != source_extent
                    or source.boundary_axis != query.boundary_axis or source.trace_coordinate_px not in interval_by_trace
                    or source.window_px != window or source.gap_px != gap
                    or source.gradient_z_minimum != spec.gradient_z_minimum
                    or source.tone_or_texture_z_minimum != spec.tone_or_texture_z_minimum):
                raise ValueError("peak source changed its registered source/kernel context")
        for trace, source in own.items():
            interval = interval_by_trace[trace]
            expected = (max(window + gap, math.ceil(interval.minimum)),
                        min(axis_extent - window - gap - 1, math.floor(interval.maximum)))
            if source.normalization_domain_px != expected:
                raise ValueError("peak normalization source changed its original complete domain")
        source_ledger = own
        baseline_purpose = ({QueryPurpose.TOP_CORRIDOR: QueryPurpose.CROSS_BASELINE,
                             QueryPurpose.BOTTOM_CORRIDOR: QueryPurpose.CROSS_BASELINE,
                             QueryPurpose.SEQUENCE_ANCHOR_WINDOW: QueryPurpose.SEQUENCE_BASELINE}.get(query.purpose))
        if baseline_purpose is not None:
            baseline = by_purpose.get(baseline_purpose)
            if baseline is not None:
                source_ledger = {source.trace_coordinate_px: source for source in baseline.peak_trace_sources}
        for group in measurement.peak_source_groups:
            source = group.source
            interval = interval_by_trace[source.trace_coordinate_px]
            expected = (max(source.normalization_domain_px[0], math.ceil(interval.minimum)),
                        min(source.normalization_domain_px[1], math.floor(interval.maximum)))
            if (source_ledger.get(source.trace_coordinate_px) != source
                    or group.measurement_domain_px != expected):
                raise ValueError("peak group changed its registered normalization source or query view")
        if measurement.coverage.peak_source_bound_exceeded and measurement.peak_source_groups:
            raise ValueError("incomplete peak source capture retained an authorized prefix")
        if query.purpose != QueryPurpose.COARSE_STRIP_SHORT:
            _validate_source_value_work(measurement)
    if coarse_support is not None:
        from .coarse_strip_support import _coarse_short_trace_lattices
        coarse = by_purpose[QueryPurpose.COARSE_STRIP_SHORT]
        sharp_ordinals = _coarse_short_trace_lattices(coarse.query.trace_positions_px)[1]
        sharp_traces = tuple(coarse.query.trace_positions_px[index] for index in sharp_ordinals)
        groups = {group.primitive_id: group for group in coarse.peak_source_groups}
        support = coarse_support.enclosing_support
        raw = (() if support is None else tuple(point for track in (support.minimum_track, support.maximum_track)
                                               for point in track.retained_transitions))
        references = tuple(item for item in raw if item.peak_source is not None)
        _validate_source_value_work(coarse, raw_count=len(raw))
        if coarse.coverage.peak_source_reference_count != len(references):
            raise ValueError("coarse raw track ledger changed its original peak reference count")
        if coarse.coverage.peak_source_retained_bytes < (1024 * len(raw)
                + sum(item.peak_source.retained_bytes for item in references)
                + sum(item.retained_bytes for item in coarse.peak_trace_sources)
                + sum(item.retained_bytes for item in coarse.peak_source_groups)):
            raise ValueError("coarse raw track ledger lost its retained storage")
        for point in references:
            query = coarse.query
            if (point.query_id != query.query_id or point.trace_ordinal >= len(sharp_traces)
                    or sharp_traces[point.trace_ordinal] != point.trace_coordinate_px):
                raise ValueError("coarse raw peak changed its original registered query/trace")
            validate_transition_peak_reference(point, groups)


def _validate_source_value_work(measurement, *, raw_count=0):
    coverage = measurement.coverage
    base = sum(source.signal_value_visit_count + 32 for source in measurement.peak_trace_sources) + 8 * raw_count
    expected = ((base + 256 * coverage.registered_coordinate_count + 32,)
                if coverage.peak_source_capture_attempted else (base, base + 32))
    if coverage.peak_source_value_visit_bound not in expected:
        raise ValueError("peak source value work changed its complete capture/validation bound")
