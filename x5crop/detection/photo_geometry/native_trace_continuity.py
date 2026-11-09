"""Independent, conservative extensions of an already authorized native run.

The pixel owner observes complete gaps before a template is consulted. A
connected response alone grants nothing: every row must identify one original
measurement peak, preserve the original source context, and share one physical
line domain. Missing or competing peaks remain unavailable, never refuted.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from bisect import bisect_right
from enum import Enum
from functools import cached_property
import math

import cv2
import numpy as np

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .line_observations import PhotoBoundaryObservation, PhysicalLineRegion
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import BoundaryRole, QueryPurpose, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from .native_trace_bridge_measurement import (
    NativeTraceBridgePlan, NativeTraceBridgeBatch, decode_mask,
    measure_native_trace_bridges, peaks_at_row, decode_credible_mask, native_trace_bridge_preflight_value_visit_bound,
    native_trace_bridge_normalization_domain,
)
from .robust_line_fit import _clip_line_region
from .trace_support import source_spanning_continuous_trace_support, trace_support_is_one_connected_run


class NativeTraceContinuityFailure(str, Enum):
    ORIGINAL_PEAK_UNAVAILABLE = "original_peak_unavailable"
    ORIGINAL_GROUP_UNAVAILABLE = "original_peak_group_unavailable"
    ORIGINAL_RUN_UNAVAILABLE = "original_run_unavailable"
    SOURCE_DOMAIN_UNAVAILABLE = "source_domain_unavailable"
    COMPLETE_EXTENSION_UNAVAILABLE = "complete_extension_unavailable"
    RAW_PEAK_COMPETITION = "raw_peak_competition"
    SOURCE_CONTEXT_CONFLICT = "source_context_conflict"
    DENSE_SIGNAL_UNAVAILABLE = "dense_signal_unavailable"
    DENSE_PEAK_COMPETITION = "dense_peak_competition"
    DENSE_GROUP_UNAVAILABLE = "dense_peak_group_unavailable"
    PHYSICAL_DOMAIN_UNAVAILABLE = "physical_domain_unavailable"
    MEASUREMENT_BOUND_EXCEEDED = "measurement_bound_exceeded"
    PROOF_BOUND_EXCEEDED = "proof_bound_exceeded"


def _region(parent, positions):
    vertices = parent.vertices
    for trace, interval in positions:
        distance = trace - parent.reference_trace_px
        vertices = _clip_line_region(vertices, 1.0, distance, interval.maximum)
        vertices = _clip_line_region(vertices, -1.0, -distance, -interval.minimum)
        if not vertices:
            return None
    return PhysicalLineRegion(parent.reference_trace_px, vertices)


@dataclass(frozen=True)
class NativeTraceContinuityConstraint:
    association_id: str
    observation_id: ObservationId
    role: BoundaryRole
    query_id: str
    query_trace_coordinates_px: tuple[int, ...]
    original_physical_line_region: PhysicalLineRegion
    trace_coordinates_px: tuple[int, ...]
    trace_position_intervals_px: tuple[FiniteInterval, ...]
    supporting_transition_ids: tuple[ObservationId, ...]

    def __post_init__(self):
        if (not self.association_id or not self.query_id
                or not isinstance(self.observation_id, ObservationId)
                or self.role not in (BoundaryRole.TOP, BoundaryRole.BOTTOM)
                or not isinstance(self.original_physical_line_region, PhysicalLineRegion)
                or len(self.trace_coordinates_px) < 3
                or tuple(sorted(set(self.trace_coordinates_px))) != self.trace_coordinates_px
                or len(self.trace_coordinates_px) != len(self.trace_position_intervals_px)
                or any(not isinstance(i, FiniteInterval) for i in self.trace_position_intervals_px)
                or tuple(sorted(set(self.query_trace_coordinates_px))) != self.query_trace_coordinates_px
                or not self.supporting_transition_ids
                or tuple(sorted(set(self.supporting_transition_ids), key=str)) != self.supporting_transition_ids
                or not source_spanning_continuous_trace_support(
                    self.query_trace_coordinates_px, self.trace_coordinates_px, spec=SPEC)):
            raise ValueError("native continuity lost its complete original trace domain")

    @cached_property
    def physical_line_region(self):
        region = _region(self.original_physical_line_region,
                         zip(self.trace_coordinates_px, self.trace_position_intervals_px, strict=True))
        if region is None:
            raise ValueError("native continuity has no common physical line domain")
        return region


@dataclass(frozen=True)
class NativeTraceContinuityRequest:
    parent: PhotoBoundaryObservation
    query_id: str
    polarity: int
    supporting_transition_ids: tuple[ObservationId, ...]
    trace_intervals_px: tuple[tuple[int, int], ...]
    preliminary_failure: NativeTraceContinuityFailure | None = None


@dataclass(frozen=True)
class NativeTraceContinuityAssessment:
    observation_id: ObservationId
    failure_kind: NativeTraceContinuityFailure | None
    conflicting_traces_px: tuple[int, ...]
    constraint: NativeTraceContinuityConstraint | None

    def __post_init__(self):
        if ((self.constraint is None) != (self.failure_kind is not None)
                or self.constraint is not None and self.constraint.observation_id != self.observation_id
                or tuple(sorted(set(self.conflicting_traces_px))) != self.conflicting_traces_px):
            raise ValueError("native continuity assessment changed its original parent")

    @property
    def state(self):
        return EvidenceState.SUPPORTED if self.constraint is not None else EvidenceState.UNAVAILABLE


@dataclass(frozen=True)
class NativeTraceContinuityWork:
    value_visit_bound: int = 0
    retained_bytes: int = 0
    peak_temporary_bytes: int = 0
    bound_exceeded: bool = False
    pixel_query_count: int = 0

    def __post_init__(self):
        if (any(type(i) is not int or i < 0 for i in
                (self.value_visit_bound, self.retained_bytes, self.peak_temporary_bytes, self.pixel_query_count))
                or type(self.bound_exceeded) is not bool or self.retained_bytes > self.peak_temporary_bytes):
            raise ValueError("native continuity work receipt is invalid")


@dataclass(frozen=True)
class NativeTraceContinuityEvidence:
    requests: tuple[NativeTraceContinuityRequest, ...]
    measurements: tuple[PhotoBoundaryMeasurementSet, ...]
    batch: NativeTraceBridgeBatch | None
    assessments: tuple[NativeTraceContinuityAssessment, ...]
    work: NativeTraceContinuityWork
    planning_completed: bool = True
    planning_metadata_completed: bool = True

    def __post_init__(self):
        ids = tuple(r.parent.observation_id for r in self.requests)
        if (type(self.planning_completed) is not bool or type(self.planning_metadata_completed) is not bool
                or self.planning_completed and not self.planning_metadata_completed
                or self.planning_metadata_completed and (len(self.measurements) != 3
                    or {m.query.purpose for m in self.measurements} != {
                        QueryPurpose.CROSS_BASELINE, QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR})
                or not self.planning_metadata_completed and (self.measurements or self.requests or self.batch is not None
                    or self.assessments or self.work != NativeTraceContinuityWork(0, 0, 0, True))
                or not self.planning_completed and (self.requests or self.batch is not None
                    or self.assessments or not self.work.bound_exceeded)
                or self.batch is not None and any(not p.split_gradient_reversals or not p.record_peaks
                                                  for p in self.batch.plans)
                or self.batch is not None and self.batch.response_source_plans is not None
                or len(set(ids)) != len(ids)
                or tuple(a.observation_id for a in self.assessments) != ids
                or self.work.bound_exceeded and any(a.constraint for a in self.assessments)):
            raise ValueError("native continuity omitted a registered parent")


def _planning_eligible(binding, parent):
    return (binding.evidence == "direct" and not binding.conditional_family_ids and binding.role_authorized
            and parent.independent_support_region_count >= 3
            and not parent.source_spanning_continuous and parent.physical_line_region is not None)


def continuity_requests(registration, measurement_sets, *, source_extent):
    """Select only a physical proof obligation; never a template or fit score."""
    measurements = {BoundaryRole.TOP: next(m for m in measurement_sets if m.query.purpose == QueryPurpose.TOP_CORRIDOR),
                    BoundaryRole.BOTTOM: next(m for m in measurement_sets if m.query.purpose == QueryPurpose.BOTTOM_CORRIDOR)}
    observations = {o.observation_id: o for o in registration.observations}
    complete_peak_inventory = {}
    by_role = {}
    groups_by_role = {}
    for role, measured in measurements.items():
        by_id, by_trace = {}, {}
        for point in measured.transitions:
            complete_peak_inventory.setdefault(point.trace_coordinate_px, []).append(point)
            by_id[point.transition_id] = point
            by_trace.setdefault(point.trace_coordinate_px, []).append(point)
        by_role[role] = by_id, by_trace
        # Typed measurement construction already computed these immutable
        # primitive IDs and charged their full source/group capture work.
        groups_by_role[role] = {group.primitive_id: group for group in measured.peak_source_groups}
    requests = []
    for binding in (*registration.top_bindings, *registration.bottom_bindings):
        parent = observations[binding.observation_id]
        if not _planning_eligible(binding, parent):
            continue
        measured = measurements[parent.role]
        by_id, by_trace = by_role[parent.role]
        original = tuple(by_id[i] for i in parent.transition_ids)
        polarities = {p.polarity for p in original}
        failure = (None if trace_support_is_one_connected_run(
            measured.query.trace_positions_px, parent.trace_coordinates_px, spec=SPEC)
            else NativeTraceContinuityFailure.ORIGINAL_RUN_UNAVAILABLE)
        if (len(set(measured.query.search_intervals_px)) != 1
                or len(set(measured.query.transition_ownership_intervals_px)) != 1):
            failure = failure or NativeTraceContinuityFailure.SOURCE_CONTEXT_CONFLICT
        baseline = next(m.query for m in measurement_sets if m.query.purpose == QueryPurpose.CROSS_BASELINE
                        and m.query.lane_id == measured.query.lane_id
                        and m.query.boundary_axis == measured.query.boundary_axis)
        if (len(set(baseline.search_intervals_px)) != 1
                or baseline.boundary_axis_scale_px_per_mm != measured.query.boundary_axis_scale_px_per_mm):
            failure = failure or NativeTraceContinuityFailure.SOURCE_CONTEXT_CONFLICT
        observable_start, observable_stop = native_trace_bridge_normalization_domain(
            source_extent, baseline.boundary_axis, baseline.search_intervals_px[0],
            baseline.boundary_axis_scale_px_per_mm.maximum)
        if any(math.ceil(i.minimum) < observable_start or math.floor(i.maximum) >= observable_stop
               for i in measured.query.search_intervals_px):
            failure = failure or NativeTraceContinuityFailure.SOURCE_DOMAIN_UNAVAILABLE
        polarity = next(iter(polarities)) if len(polarities) == 1 else 0
        if not polarity or any(p.peak_source is None for p in original):
            failure = failure or NativeTraceContinuityFailure.ORIGINAL_PEAK_UNAVAILABLE
        low, high = parent.trace_coordinates_px[0], parent.trace_coordinates_px[-1]
        outside = {}
        for trace, points in by_trace.items():
            if low <= trace <= high:
                continue
            # Every peak on this same trace uses exactly the same native
            # projection. Keep the complete point inventory, project once.
            region = parent.physical_line_region.project(float(trace))
            matching = [point for point in points
                        if region.maximum >= point.physical_position_interval_px.minimum
                        and point.physical_position_interval_px.maximum >= region.minimum]
            if matching:
                outside[trace] = matching
        if any(len(points) != 1 for points in outside.values()):
            failure = failure or NativeTraceContinuityFailure.RAW_PEAK_COMPETITION
        extensions = tuple(points[0] for points in outside.values() if len(points) == 1)
        if any(p.polarity != polarity or p.peak_source is None for p in extensions):
            failure = failure or NativeTraceContinuityFailure.ORIGINAL_PEAK_UNAVAILABLE
        support = tuple(sorted((*original, *extensions), key=lambda p: p.trace_coordinate_px))
        for point in support:
            if point.peak_source is None:
                continue
            coordinate = float(point.peak_source.source_coordinate_px)
            aliases = tuple(p for p in complete_peak_inventory[point.trace_coordinate_px]
                            if p.physical_position_interval_px.contains(coordinate))
            if aliases != (point,):
                failure = failure or NativeTraceContinuityFailure.RAW_PEAK_COMPETITION
        if not source_spanning_continuous_trace_support(
                measured.query.trace_positions_px, tuple(p.trace_coordinate_px for p in support), spec=SPEC):
            failure = failure or NativeTraceContinuityFailure.COMPLETE_EXTENSION_UNAVAILABLE
        if _region(parent.physical_line_region,
                   ((p.trace_coordinate_px, p.physical_position_interval_px) for p in support)) is None:
            failure = failure or NativeTraceContinuityFailure.PHYSICAL_DOMAIN_UNAVAILABLE
        groups = groups_by_role[parent.role]
        if any(point.peak_source is not None and (
                groups.get(point.peak_source.group_id) is None
                or not groups[point.peak_source.group_id].complete) for point in support):
            failure = failure or NativeTraceContinuityFailure.ORIGINAL_GROUP_UNAVAILABLE
        queried = measured.query.trace_positions_px
        step = float(np.median(np.diff(np.asarray(queried, dtype=np.float64))))
        allowance = step * (SPEC.maximum_missing_lattice_steps + 1) + SPEC.paired_sampling_uncertainty_px
        intervals = tuple(interval for condition, interval in (
            (low > queried[0] + allowance, (queried[0], low + 1)),
            (high < queried[-1] - allowance, (high, queried[-1] + 1)),
        ) if condition)
        requests.append(NativeTraceContinuityRequest(parent, measured.query.query_id, polarity,
            tuple(sorted((p.transition_id for p in support), key=str)), intervals, failure))
    return tuple(requests)


def _merge(intervals):
    result = []
    for low, high in sorted(intervals):
        if result and low <= result[-1][1]:
            result[-1] = (result[-1][0], max(high, result[-1][1]))
        else:
            result.append((low, high))
    return tuple(result)


def continuity_plans(field, requests, measurements):
    by_query = {m.query.query_id: m for m in measurements}
    baselines = tuple(m.query for m in measurements if m.query.purpose == QueryPurpose.CROSS_BASELINE)
    plans = []
    for query_id in sorted({r.query_id for r in requests if r.preliminary_failure is None}):
        query = by_query[query_id].query
        baseline = next(b for b in baselines if b.lane_id == query.lane_id and b.boundary_axis == query.boundary_axis)
        if any(i != baseline.search_intervals_px[0] for i in baseline.search_intervals_px):
            raise ValueError("native continuity requires the original complete normalization domain")
        plans.append(NativeTraceBridgePlan(field.source_id, field.source_extent, query.boundary_axis,
            query.query_id, baseline.query_id, baseline.search_intervals_px[0],
            FiniteInterval(min(i.minimum for i in query.search_intervals_px),
                           max(i.maximum for i in query.search_intervals_px)),
            _merge(interval for r in requests if r.query_id == query_id and r.preliminary_failure is None
                   for interval in r.trace_intervals_px), query.boundary_axis_scale_px_per_mm.maximum,
            query.trace_positions_px))
    return tuple(plans)


def _proof_reservation(requests, plans):
    sites = sum((stop-start) * (math.floor(p.coordinate_interval_px.maximum)
                - math.ceil(p.coordinate_interval_px.minimum) + 1)
                for p in plans for start, stop in p.trace_intervals_px)
    rows = [len(r.parent.trace_coordinates_px) + sum(high-low for low, high in r.trace_intervals_px)
            for r in requests if r.preliminary_failure is None]
    visits = 4096 + 48 * sites * max(1, len(rows)) + sum(64*n*(n+8) for n in rows)
    retained = 4096 + 256 * sum(len(r.supporting_transition_ids)+1 for r in requests) + sum(512*n for n in rows)
    peak = retained + 20 * sites + sum(128*n for n in rows)
    return visits, retained, peak


def _planning_metadata_reservation(registration, measurement_sets):
    count = len(registration.top_bindings) + len(registration.bottom_bindings)
    observations = len(registration.observations)
    points = sum(len(m.transitions) for m in measurement_sets if m.query.purpose in
                 (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR))
    groups = sum(len(m.peak_source_groups) for m in measurement_sets if m.query.purpose in
                 (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR))
    return (4096 + 128*(count+observations+points+groups) + 16*count*observations,
            4096 + 64*(count+observations+groups))


def _planning_reservation(registration, measurement_sets):
    count = len(registration.top_bindings) + len(registration.bottom_bindings)
    # Only metadata is inspected here. Failed raw/continuity obligations are
    # still eligible and charged; no outcome, candidate or source pixel is read.
    eligible = 0
    for binding in (*registration.top_bindings, *registration.bottom_bindings):
        parent = next(o for o in registration.observations if o.observation_id == binding.observation_id)
        eligible += _planning_eligible(binding, parent)
    points = sum(len(m.transitions) for m in measurement_sets if m.query.purpose in
                 (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR))
    groups = sum(len(m.peak_source_groups) for m in measurement_sets if m.query.purpose in
                 (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR))
    vertices = max((len(o.physical_line_region.vertices) for o in registration.observations
                    if o.physical_line_region is not None), default=0)
    metadata_visits, metadata_bytes = _planning_metadata_reservation(registration, measurement_sets)
    return (metadata_visits + 16*eligible*points*(vertices+2*points+8),
            max(metadata_bytes, 4096 + 256*(eligible*points+count+points+groups)))


def _bridge_context(batch, plan_index, low, high, polarity, *, include_credible=True):
    strips = tuple(sorted((s for s in batch.strips if s.plan_index == plan_index
                           and s.trace_start_px < high and s.trace_stop_px > low),
                          key=lambda s: s.trace_start_px))
    chunks, credible_chunks, next_trace = [], [], low
    sources = {}
    for strip in strips:
        first, stop = max(low, strip.trace_start_px), min(high, strip.trace_stop_px)
        if first != next_trace:
            raise ValueError("native continuity lost a complete intermediate trace block")
        chunks.append(decode_mask(strip,polarity,trace_interval_px=(first,stop)))
        if include_credible:
            credible_chunks.append(decode_credible_mask(strip,trace_interval_px=(first,stop)))
        next_trace = stop
        for source in strip.original_trace_sources:
            if source.trace_coordinate_px in sources and sources[source.trace_coordinate_px] != source:
                raise ValueError("native continuity mixed original trace source contexts")
            sources[source.trace_coordinate_px] = source
    if next_trace != high:
        raise ValueError("native continuity lost its final intermediate trace block")
    mask = np.concatenate(chunks, axis=0)
    credible = np.concatenate(credible_chunks, axis=0) if include_credible else None
    _count, labels = cv2.connectedComponents(mask, connectivity=4, ltype=cv2.CV_32S)
    return labels, credible, strips, tuple(s.trace_start_px for s in strips), sources


def _dense_group_complete(credible_row, column, peak, coordinate_start):
    """Require both observed OR flanks, not merely an interior AND component."""
    if not 0 <= column < credible_row.size or not credible_row[column]:
        return False
    gaps = np.flatnonzero(credible_row == 0)
    ordinal = int(np.searchsorted(gaps, column))
    if ordinal == 0 or ordinal == gaps.size:
        return False
    low, high = int(gaps[ordinal-1])+1, int(gaps[ordinal])-1
    interval = peak.physical_position_interval_px
    return (interval.minimum >= coordinate_start+low-0.5
            and interval.maximum <= coordinate_start+high+0.5)


def assess_native_continuity(requests, measurements, batch):
    """Replay full masks and original peaks; unavailable is never exclusion."""
    from .native_trace_bridge_measurement import decode_mask
    if batch is not None and (batch.response_source_plans is not None
            or any(not p.split_gradient_reversals or not p.record_peaks for p in batch.plans)):
        raise ValueError("Cross continuity requires the original split peak selector")
    measurements_by_id = {m.query.query_id: m for m in measurements}
    baseline_sources = {s.trace_coordinate_px: s for m in measurements
                        if m.query.purpose == QueryPurpose.CROSS_BASELINE for s in m.peak_trace_sources}
    # The two sign views are neutral pixel facts, reused within this one replay.
    contexts = {}
    assessments = []
    for request in requests:
        parent = request.parent
        failure = request.preliminary_failure
        conflicts = set()
        positions = dict(zip(parent.trace_coordinates_px, parent.trace_position_intervals_px, strict=True))
        if failure is None and (batch is None or batch.bound_exceeded):
            failure = NativeTraceContinuityFailure.MEASUREMENT_BOUND_EXCEEDED
        measurement = measurements_by_id[request.query_id]
        raw_by_id = {p.transition_id: p for p in measurement.transitions}
        if failure is None:
            plan_index = next(i for i, p in enumerate(batch.plans) if p.original_query_id == request.query_id)
            for low, high in request.trace_intervals_px:
                key = (plan_index, low, high, request.polarity)
                if key not in contexts:
                    contexts.clear()
                    contexts[key] = _bridge_context(batch, plan_index, low, high, request.polarity)
                labels, credible, strips, starts, sources = contexts[key]
                coordinate_start = strips[0].coordinate_start_px
                anchor_trace = (parent.trace_coordinates_px[0] if low < parent.trace_coordinates_px[0]
                                else parent.trace_coordinates_px[-1])
                anchor = next(raw_by_id[i] for i in parent.transition_ids
                              if raw_by_id[i].trace_coordinate_px == anchor_trace)
                column = anchor.peak_source.source_coordinate_px - coordinate_start
                component = int(labels[anchor_trace-low, column])
                if component == 0:
                    failure = failure or NativeTraceContinuityFailure.DENSE_SIGNAL_UNAVAILABLE
                    conflicts.add(anchor_trace)
                    continue
                selected = labels == component
                if np.any(selected[:, 0]) or np.any(selected[:, -1]):
                    failure = failure or NativeTraceContinuityFailure.DENSE_SIGNAL_UNAVAILABLE
                for trace in measurement.query.trace_positions_px:
                    if not low <= trace < high:
                        continue
                    if sources.get(trace) != baseline_sources.get(trace):
                        failure = failure or NativeTraceContinuityFailure.SOURCE_CONTEXT_CONFLICT
                        conflicts.add(trace)
                required = tuple(raw_by_id[i] for i in request.supporting_transition_ids
                                 if low <= raw_by_id[i].trace_coordinate_px < high)
                for point in required:
                    source_column = point.peak_source.source_coordinate_px - coordinate_start
                    if (not 0 <= source_column < labels.shape[1]
                            or int(labels[point.trace_coordinate_px-low, source_column]) != component):
                        failure = failure or NativeTraceContinuityFailure.DENSE_SIGNAL_UNAVAILABLE
                        conflicts.add(point.trace_coordinate_px)
                active = np.flatnonzero(np.any(selected, axis=1))
                for row in active:
                    trace = int(row) + low
                    if not low <= trace < high:
                        continue
                    matches = []
                    strip = strips[bisect_right(starts, trace)-1]
                    peaks = peaks_at_row(strip, trace-strip.trace_start_px)
                    for peak in peaks:
                        column = peak.source_coordinate_px-coordinate_start
                        if 0 <= column < labels.shape[1] and labels[int(row), column] == component:
                            matches.append(peak)
                    if len(matches) != 1:
                        failure = failure or NativeTraceContinuityFailure.DENSE_PEAK_COMPETITION
                        conflicts.add(trace)
                        continue
                    peak = matches[0]
                    column = peak.source_coordinate_px-coordinate_start
                    aliases = tuple(p for p in peaks if p.physical_position_interval_px.contains(float(peak.source_coordinate_px)))
                    if (peak.polarity != request.polarity or not 0 <= column < labels.shape[1]
                            or labels[int(row), column] != component or aliases != (peak,)):
                        failure = failure or NativeTraceContinuityFailure.DENSE_SIGNAL_UNAVAILABLE
                        conflicts.add(trace)
                        continue
                    if not _dense_group_complete(credible[int(row)], column, peak, coordinate_start):
                        failure = failure or NativeTraceContinuityFailure.DENSE_GROUP_UNAVAILABLE
                        conflicts.add(trace)
                        continue
                    old = positions.get(trace)
                    interval = peak.physical_position_interval_px
                    if old is not None and old != interval:
                        failure = failure or NativeTraceContinuityFailure.SOURCE_CONTEXT_CONFLICT
                        conflicts.add(trace)
                    positions[trace] = interval
        constraint = None
        if failure is None:
            ordered = tuple(sorted(positions))
            try:
                constraint = NativeTraceContinuityConstraint(
                    f"native-trace-continuity:{parent.observation_id}", parent.observation_id, parent.role,
                    request.query_id, measurement.query.trace_positions_px, parent.physical_line_region,
                    ordered, tuple(positions[t] for t in ordered), request.supporting_transition_ids)
                constraint.physical_line_region
            except ValueError:
                constraint = None
                failure = NativeTraceContinuityFailure.PHYSICAL_DOMAIN_UNAVAILABLE
        assessments.append(NativeTraceContinuityAssessment(parent.observation_id, failure,
            tuple(sorted(conflicts)), constraint))
    return tuple(assessments)


def prepare_native_continuity(field, registration, measurement_sets, *, maximum_value_visits, maximum_temporary_bytes):
    if any(type(value) is not int or value < 0 for value in (maximum_value_visits, maximum_temporary_bytes)):
        raise ValueError("native continuity requires non-negative remaining source budgets")
    # This flag-only guard reads no raw peak inventory. Once planning starts,
    # even an unavailable original raster run retains its complete work.
    if not any(b.evidence == "direct" and not b.conditional_family_ids and b.role_authorized
               and b.independent_support_region_count >= 3 and not b.source_spanning_continuous
               and b.physical_line_region is not None
               for b in (*registration.top_bindings, *registration.bottom_bindings)):
        return None
    metadata_visits, metadata_bytes = _planning_metadata_reservation(registration, measurement_sets)
    if metadata_visits > maximum_value_visits or metadata_bytes > maximum_temporary_bytes:
        return NativeTraceContinuityEvidence((), (), None, (), NativeTraceContinuityWork(
            0, 0, 0, True), planning_completed=False, planning_metadata_completed=False)
    measurements = tuple(m for m in measurement_sets if m.query.purpose in
                         (QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR, QueryPurpose.CROSS_BASELINE))
    planning_visits, planning_bytes = _planning_reservation(registration, measurements)
    if planning_visits > maximum_value_visits or planning_bytes > maximum_temporary_bytes:
        return NativeTraceContinuityEvidence((), measurements, None, (), NativeTraceContinuityWork(
            metadata_visits, 0, metadata_bytes, True), planning_completed=False)
    requests = continuity_requests(registration, measurements, source_extent=field.source_extent)
    if not requests:
        raise ValueError("native continuity planning lost its eligible original parent")
    plans = continuity_plans(field, requests, measurements)
    visits, retained, peak = _proof_reservation(requests, plans)
    if (planning_visits + visits + native_trace_bridge_preflight_value_visit_bound(plans) > maximum_value_visits
            or peak > maximum_temporary_bytes):
        assessments = tuple(NativeTraceContinuityAssessment(r.parent.observation_id,
            r.preliminary_failure or NativeTraceContinuityFailure.PROOF_BOUND_EXCEEDED, (), None) for r in requests)
        return NativeTraceContinuityEvidence(requests, measurements, None, assessments,
            NativeTraceContinuityWork(planning_visits, planning_bytes, planning_bytes, True))
    batch = measure_native_trace_bridges(field, plans,
        maximum_pixel_queries=maximum_value_visits-planning_visits-visits,
        maximum_temporary_bytes=maximum_temporary_bytes-peak)
    assessments = assess_native_continuity(requests, measurements, batch)
    work = NativeTraceContinuityWork(
        planning_visits + visits + batch.value_visit_bound + batch.preflight_value_visit_bound,
        retained + batch.retained_bytes, max(planning_bytes, peak + batch.peak_temporary_bytes),
        batch.bound_exceeded, batch.pixel_query_count)
    return NativeTraceContinuityEvidence(requests, measurements, batch, assessments, work)


def apply_native_continuity(registration, evidence):
    if evidence is None:
        return registration
    constraints = {a.observation_id: a.constraint for a in evidence.assessments if a.constraint is not None}
    if not constraints:
        return registration
    def apply(bindings):
        return tuple(replace(b, native_continuity_constraint=constraints[b.observation_id])
                     if b.observation_id in constraints and b.native_continuity_constraint != constraints[b.observation_id]
                     else b for b in bindings)
    top, bottom = apply(registration.top_bindings), apply(registration.bottom_bindings)
    if all(new is old for new, old in zip((*top, *bottom),
            (*registration.top_bindings, *registration.bottom_bindings), strict=True)):
        return registration
    return replace(registration, top_bindings=top, bottom_bindings=bottom)
