"""Candidate-independent dense constraints for aggregate-supported native edges.

The original parent, roles, statistical protection and raw ledger survive.
Unavailable connections never refute an interpretation or add an anchor.
"""
from bisect import bisect_right
from dataclasses import dataclass, replace
import math

import numpy as np

from ...domain import ObservationId, FiniteInterval
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import QueryPurpose, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from .observation_types import BoundaryEdgeObservation, BoundaryEdgeMeasurementBasis
from .native_trace_bridge_measurement import (
    NativeTraceBridgePlan, NativeTraceBridgeBatch, peaks_at_row,
    native_trace_bridge_normalization_domain, native_trace_bridge_preflight_value_visit_bound,
    validate_native_trace_bridge_batch,
    native_trace_bridge_retained_byte_bound,
    measure_native_trace_signals, refine_native_trace_responses, native_trace_response_cache_byte_bound,
    native_trace_response_consumption_work, validate_native_trace_response_reuse,
    _prepare as _bridge_reservation,
)
from .native_trace_continuity import _bridge_context, _dense_group_complete
from .sequence_connection_model import SequenceConnectionConstraint, SequenceConnectionWork, SequenceConnectionBudget
from .trace_support import trace_support_is_one_connected_run
from .transition_peak_source import same_transition_peak
from .robust_line_fit import LINE_REGION_ARITHMETIC_EPSILON_PX


@dataclass(frozen=True)
class SequenceConnectionRequest:
    observation_id: ObservationId
    query_id: str | None
    trace_interval_px: tuple[int,int]
    polarity: int
    failure_kind: str | None


@dataclass(frozen=True)
class SequenceConnectionAssessment:
    observation_id: ObservationId
    failure_kind: str | None
    constraint: SequenceConnectionConstraint | None

    def __post_init__(self):
        if ((self.failure_kind is None) != (self.constraint is not None)
                or self.constraint is not None and self.constraint.observation_id != self.observation_id):
            raise ValueError("Sequence connection omitted its unavailable obligation")


@dataclass(frozen=True)
class SequenceConnectionEvidence:
    parents: tuple[BoundaryEdgeObservation,...]
    measurements: tuple[PhotoBoundaryMeasurementSet,...]
    requests: tuple[SequenceConnectionRequest,...]
    batch: NativeTraceBridgeBatch | None
    assessments: tuple[SequenceConnectionAssessment,...]
    work: SequenceConnectionWork
    planning_completed: bool
    budget: SequenceConnectionBudget
    signal_batch: NativeTraceBridgeBatch | None = None

    def __post_init__(self):
        ids = tuple(p.observation_id for p in self.parents)
        if (not isinstance(self.budget,SequenceConnectionBudget)
                or self.work.value_visit_bound+self.work.pixel_query_count > self.budget.maximum_value_visits
                or self.work.persistent_input_bytes+self.work.peak_temporary_bytes > self.budget.maximum_temporary_bytes
                or len(set(ids)) != len(ids) or any(p.sequence_connection_constraint is not None for p in self.parents)
                or type(self.planning_completed) is not bool
                or self.planning_completed and (tuple(r.observation_id for r in self.requests) != ids
                    or tuple(a.observation_id for a in self.assessments) != ids)
                or not self.planning_completed and (self.requests or self.assessments or self.batch is not None
                                                    or self.signal_batch is not None)
                or self.signal_batch is not None and any(p.record_peaks for p in self.signal_batch.plans)
                or self.work.bound_exceeded and any(a.constraint is not None for a in self.assessments)):
            raise ValueError("Sequence connection changed its complete parent ledger")


def eligible_sequence_connection_parent(parent):
    return (parent.measurement_basis == BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE
            and bool(parent.qualified_anchor_roles) and parent.physical_line_region is not None
            and parent.position_protection_interval_px is not None)


def _counts(parents, measurements):
    points = sum(len(m.transitions) for m in measurements)
    groups = sum(len(m.peak_source_groups) for m in measurements)
    raw = sum(len(p.transition_ids) for p in parents)
    vertices = max((len(p.physical_line_region.vertices) for p in parents),default=0)
    # Covers complete query/trace/group indices, all alias candidates and
    # typed context checks. No successful-prefix or point-outcome discount.
    visits = 4096+128*(len(parents)+len(measurements)+points+groups)+32*raw*(points+vertices+8)
    memory = 8192+512*(points+groups+raw+len(parents)+len(measurements))
    return visits,memory


def sequence_connection_requests(parents, measurements, *, source_extent):
    windows = tuple(m for m in measurements if m.query.purpose == QueryPurpose.SEQUENCE_ANCHOR_WINDOW)
    baseline = next(m for m in measurements if m.query.purpose == QueryPurpose.SEQUENCE_BASELINE)
    by_id = {p.transition_id:p for m in windows for p in m.transitions}
    by_query = {m.query.query_id:m for m in windows}
    groups = {g.primitive_id:g for m in windows for g in m.peak_source_groups}
    by_trace = {}
    for p in by_id.values():
        by_trace.setdefault(p.trace_coordinate_px,[]).append(p)
    result = []
    for parent in parents:
        failure = None
        original = tuple(by_id.get(i) for i in parent.transition_ids)
        ids = {p.query_id for p in original if p is not None}
        query_id = next(iter(ids)) if len(ids)==1 else None
        interval = (min(parent.trace_coordinates_px),max(parent.trace_coordinates_px)+1)
        if any(p is None for p in original) or query_id is None:
            failure = "original_query_unavailable"
        else:
            measured = by_query[query_id]
            query = measured.query
            if (not measured.coverage.complete or len(set(query.search_intervals_px)) != 1
                    or len(set(query.transition_ownership_intervals_px)) != 1
                    or baseline.query.trace_positions_px != query.trace_positions_px
                    or baseline.query.boundary_axis_scale_px_per_mm != query.boundary_axis_scale_px_per_mm):
                failure = "source_context_conflict"
            if not trace_support_is_one_connected_run(query.trace_positions_px,parent.trace_coordinates_px,spec=SPEC):
                failure = failure or "original_run_unavailable"
            low, high = native_trace_bridge_normalization_domain(source_extent,query.boundary_axis,
                baseline.query.search_intervals_px[0],query.boundary_axis_scale_px_per_mm.maximum)
            if any(math.ceil(i.minimum)<low or math.floor(i.maximum)>=high for i in query.search_intervals_px):
                failure = failure or "source_domain_unavailable"
            for p in original:
                ref = p.peak_source
                if (ref is None or ref.group_id not in groups or not groups[ref.group_id].complete
                        or p.polarity != parent.polarity or p.polarity == 0):
                    failure = failure or "original_peak_group_unavailable"
                    continue
                for alias in by_trace[p.trace_coordinate_px]:
                    if not alias.physical_position_interval_px.contains(float(ref.source_coordinate_px)):
                        continue
                    other = alias.peak_source
                    if (other is None or other.group_id not in groups or not same_transition_peak(
                            ref,groups[ref.group_id],other,groups[other.group_id])):
                        failure = failure or "raw_peak_competition"
        result.append(SequenceConnectionRequest(parent.observation_id,query_id,interval,parent.polarity,failure))
    return tuple(result)


def sequence_connection_plans(field, requests, measurements):
    by_query = {m.query.query_id:m.query for m in measurements}
    baseline = next(m.query for m in measurements if m.query.purpose == QueryPurpose.SEQUENCE_BASELINE)
    plans = []
    for identity in sorted({r.query_id for r in requests if r.failure_kind is None}):
        query = by_query[identity]
        intervals = []
        for low,high in sorted(r.trace_interval_px for r in requests if r.query_id==identity and r.failure_kind is None):
            if intervals and low <= intervals[-1][1]:
                intervals[-1] = (intervals[-1][0],max(high,intervals[-1][1]))
            else:
                intervals.append((low,high))
        plans.append(NativeTraceBridgePlan(field.source_id,field.source_extent,query.boundary_axis,
            identity,baseline.query_id,baseline.search_intervals_px[0],query.search_intervals_px[0],
            tuple(intervals),query.boundary_axis_scale_px_per_mm.maximum,query.trace_positions_px,False))
    return tuple(plans)


def _proof_bounds(parents, requests, plans):
    widths = {p.original_query_id:math.floor(p.coordinate_interval_px.maximum)-math.ceil(p.coordinate_interval_px.minimum)+1
              for p in plans}
    sites = sum((r.trace_interval_px[1]-r.trace_interval_px[0])*widths[r.query_id]
                for r in requests if r.failure_kind is None)
    sizes = [r.trace_interval_px[1]-r.trace_interval_px[0] for r in requests if r.failure_kind is None]
    max_sites = max(((r.trace_interval_px[1]-r.trace_interval_px[0])*widths[r.query_id]
                     for r in requests if r.failure_kind is None),default=0)
    # Each complete recorded peak also tests its two interval differences
    # against the original parent's projection (eight scalar operations).
    # Project all original vertices afresh per row; never a selected prefix.
    domain_work = sum(128*(r.trace_interval_px[1]-r.trace_interval_px[0])*(len(p.physical_line_region.vertices)+1)
                      for p,r in zip(parents,requests,strict=True) if r.failure_kind is None)
    visits = 4096+56*sites+domain_work+sum(64*n*(n+8) for n in sizes)
    retained = 4096+512*sum(sizes)+1024*sum(len(p.transition_ids) for p in parents)
    # One request helper owns all decoded arrays; it returns plain tuples
    # before the next helper allocates another context. All constraints and
    # the complete encoded batch remain retained, independent of success.
    memory = retained+20*max_sites+4096*max(widths.values(),default=0)+128*max(sizes,default=0)
    return visits,retained,memory


def _guard_value_bound(parents,requests,plans,measurements):
    """Signal connectivity only: no peak/flank/physical-line clipping work."""
    by_query = {m.query.query_id:m for m in measurements}
    by_plan = {p.original_query_id:p for p in plans}
    baseline = next(m for m in measurements if m.query.purpose==QueryPurpose.SEQUENCE_BASELINE)
    all_rows = sum(b-a for p in plans for a,b in p.trace_intervals_px)
    visits = 4096
    for parent,request in zip(parents,requests,strict=True):
        if request.failure_kind is not None:
            continue
        plan = by_plan[request.query_id]
        width = math.floor(plan.coordinate_interval_px.maximum)-math.ceil(plan.coordinate_interval_px.minimum)+1
        rows = request.trace_interval_px[1]-request.trace_interval_px[0]
        source_rows = sum(b-a for a,b in plan.trace_intervals_px)
        # Decode only the requested rows. The 32-site allowance covers packed
        # unpacking, concatenation, four-neighbour component passes, selection
        # and corridor tests. Whole intersecting hex strings are still strictly
        # validated; one extra visit per complete source site bounds that scan.
        visits += 32*rows*width+source_rows*width
        # Every strip may be singleton. Include complete strip selection/sort,
        # original source indexing, raw lookup and parent/measurement scans.
        visits += (128*(all_rows+len(plans)+len(measurements)+len(baseline.peak_trace_sources)
                       +len(baseline.query.trace_positions_px)+len(by_query[request.query_id].transitions)
                       +len(parent.transition_ids))
                   +16*source_rows*max(1,source_rows.bit_length()))
    return visits


def _connection_context(parent,request,measurements,batch,*,include_credible=True):
    plan_index = next(i for i,p in enumerate(batch.plans) if p.original_query_id==request.query_id)
    low,high = request.trace_interval_px
    labels,credible,strips,starts,sources = _bridge_context(batch,plan_index,low,high,request.polarity,
                                                         include_credible=include_credible)
    coordinate_start = strips[0].coordinate_start_px
    baseline = next(m for m in measurements if m.query.purpose == QueryPurpose.SEQUENCE_BASELINE)
    old_sources = {s.trace_coordinate_px:s for s in baseline.peak_trace_sources}
    measured = next(m for m in measurements if m.query.query_id==request.query_id)
    raw = {p.transition_id:p for p in measured.transitions}
    original = tuple(raw[i] for i in parent.transition_ids)
    component = int(labels[original[0].trace_coordinate_px-low,
                           original[0].peak_source.source_coordinate_px-coordinate_start])
    failure = None if component else "dense_signal_unavailable"
    selected = labels==component if component else np.zeros_like(labels,dtype=bool)
    if np.any(selected[:,0]) or np.any(selected[:,-1]):
        failure = failure or "dense_signal_unavailable"
    for trace in baseline.query.trace_positions_px:
        if low <= trace < high and sources.get(trace) != old_sources.get(trace):
            failure = failure or "source_context_conflict"
    for p in original:
        if labels[p.trace_coordinate_px-low,p.peak_source.source_coordinate_px-coordinate_start] != component:
            failure = failure or "original_connection_unavailable"
    return failure,labels,credible,strips,starts,original,component,coordinate_start


def _guard_one(parent,request,measurements,batch):
    if request.failure_kind is not None:
        return request
    # Only scalar failure survives this stack; decoded contexts are released
    # before another parent or the full peak measurement starts.
    failure,*_context = _connection_context(parent,request,measurements,batch,include_credible=False)
    return replace(request,failure_kind=failure)


def guard_sequence_connections(parents,requests,measurements,batch):
    if batch.bound_exceeded or any(p.record_peaks or p.split_gradient_reversals for p in batch.plans):
        raise ValueError('Sequence signal guard requires its complete signal-only batch')
    return tuple(_guard_one(p,r,measurements,batch) for p,r in zip(parents,requests,strict=True))


def _assess_one(parent, request, measurements, batch):
    if request.failure_kind is not None:
        return SequenceConnectionAssessment(parent.observation_id,request.failure_kind,None)
    if batch is None or batch.bound_exceeded:
        return SequenceConnectionAssessment(parent.observation_id,"measurement_bound_exceeded",None)
    if any(not p.record_peaks for p in batch.plans):
        raise ValueError('signal-only measurements cannot grant a Sequence constraint')
    failure,labels,credible,strips,starts,original,component,coordinate_start = _connection_context(
        parent,request,measurements,batch)
    if failure is not None:
        # The complete measured batch and parent obligation remain recorded.
        # A failed necessary connection cannot gain a constraint from later
        # peak checks, so no dense peak decoding is needed for this parent.
        return SequenceConnectionAssessment(parent.observation_id,failure,None)
    positions = []
    low,high = request.trace_interval_px
    measured = next(m for m in measurements if m.query.query_id==request.query_id)
    slope = -math.tan(math.radians(parent.canonical_direction_degrees))
    residual_radius = 0.
    for trace in range(low,high):
        strip = strips[bisect_right(starts,trace)-1]
        peaks = peaks_at_row(strip,trace-strip.trace_start_px)
        connected = tuple(p for p in peaks if labels[trace-low,p.source_coordinate_px-coordinate_start]==component) if component else ()
        projected = parent.physical_line_region.project(float(trace))
        # This is the necessary projection of the independently established
        # original joint domain, not a canonical distance or a template window.
        # Keep tangencies and arithmetic uncertainty; retain every original
        # record and its full interval even when it cannot belong to this parent.
        matches = tuple(p for p in connected
            if p.physical_position_interval_px.maximum-projected.minimum >= -LINE_REGION_ARITHMETIC_EPSILON_PX
            and p.physical_position_interval_px.minimum-projected.maximum <= LINE_REGION_ARITHMETIC_EPSILON_PX) if component else ()
        if len(matches) != 1:
            failure = failure or ("physical_domain_unavailable" if connected and not matches else "dense_peak_competition")
            continue
        peak = matches[0]
        if peak.localization_width_px is None:
            failure = failure or 'dense_localization_unavailable'
        else:
            predicted = parent.canonical_position_px+slope*(trace-parent.reference_trace_px)
            residual_radius = max(residual_radius,abs(peak.canonical_coordinate_px-predicted)+peak.localization_width_px/2)
        if (peak.polarity != request.polarity or sum(p.physical_position_interval_px.contains(
                float(peak.source_coordinate_px)) for p in peaks) != 1):
            failure = failure or "dense_peak_competition"
        column = peak.source_coordinate_px-coordinate_start
        if not _dense_group_complete(credible[trace-low],column,peak,coordinate_start):
            failure = failure or "dense_group_unavailable"
        else:
            # Sequence keeps exactly one candidate per complete OR group.
            # Its physical interval is that whole group, not an arbitrary
            # smaller interval inside the same connected response.
            gaps = np.flatnonzero(credible[trace-low] == 0)
            ordinal = int(np.searchsorted(gaps,column))
            expected_interval = FiniteInterval(coordinate_start+int(gaps[ordinal-1])+.5,
                                               coordinate_start+int(gaps[ordinal])-.5)
            if peak.physical_position_interval_px != expected_interval:
                failure = failure or "dense_group_unavailable"
        existing = tuple(p for p in original if p.trace_coordinate_px==trace)
        if existing and any(p.physical_position_interval_px != peak.physical_position_interval_px
                           or p.peak_source.source_coordinate_px != peak.source_coordinate_px for p in existing):
            failure = failure or "source_context_conflict"
        positions.append(peak.physical_position_interval_px)
    constraint = None
    if failure is None:
        radius = residual_radius+SPEC.line_connection_allowance_px(measured.query.boundary_axis_scale_px_per_mm.maximum)
        protection = FiniteInterval(parent.canonical_position_px-radius,parent.canonical_position_px+radius)
        constraint = SequenceConnectionConstraint(parent.observation_id,request.query_id,parent.transition_ids,
            parent.physical_line_region,tuple(range(low,high)),tuple(positions),protection)
        try:
            constraint.physical_line_region
        except ValueError:
            constraint,failure = None,"physical_domain_unavailable"
    return SequenceConnectionAssessment(parent.observation_id,failure,constraint)


def assess_sequence_connections(parents,requests,measurements,batch):
    if batch is not None and any(p.split_gradient_reversals or not p.record_peaks for p in batch.plans):
        raise ValueError("Sequence connection changed its original single-peak selector")
    return tuple(_assess_one(p,r,measurements,batch) for p,r in zip(parents,requests,strict=True))


@dataclass(frozen=True)
class _PhasedReservation:
    signal_plans: tuple[NativeTraceBridgePlan,...]
    planning_visits: int
    guard_visits: int
    guard_memory: int
    signal_memory: int
    full_memory: int
    signal_value_budget: int
    admitted: bool


def _phased_reservation(parents,requests,plans,measurements,visits,memory,budget):
    signals = tuple(replace(p,record_peaks=False,retain_responses=True) for p in plans)
    proof_visits,_,guard_memory = _proof_bounds(parents,requests,plans)
    guard_visits = _guard_value_bound(parents,requests,plans,measurements)
    signal_preflight = native_trace_bridge_preflight_value_visit_bound(signals)
    full_preflight = native_trace_bridge_preflight_value_visit_bound(plans,signals)
    # Length-only estimates belong to the complete metadata planning charge.
    # Reserve the two actual bridge preparations before either is executed.
    planning = visits+signal_preflight+full_preflight
    available = max(0,budget.maximum_temporary_bytes-budget.persistent_input_bytes-memory)
    signal_retained = native_trace_bridge_retained_byte_bound(signals)
    response_cache = native_trace_response_cache_byte_bound(signals)
    full_memory = max(0,available-signal_retained)
    if planning > budget.maximum_value_visits:
        return _PhasedReservation(signals,visits,guard_visits,guard_memory,available,full_memory,0,False)
    _,signal_pixels,signal_values,_,signal_peak,_,signal_fits = _bridge_reservation(signals,available)
    _,full_pixels,full_values,_,_,_,full_fits = _bridge_reservation(plans,full_memory,signals)
    full_work = full_pixels+full_values+full_preflight if plans else 0
    signal_budget = max(0,budget.maximum_value_visits-planning-guard_visits-proof_visits-full_work)
    admitted = (signal_fits and full_fits
        and signal_pixels+signal_values+signal_preflight <= signal_budget
        and signal_peak <= available and signal_retained+response_cache+guard_memory <= available)
    return _PhasedReservation(signals,planning,guard_visits,guard_memory,available,full_memory,
                              signal_budget,admitted)


def _unadmitted(parents,measures,requests,memory,budget,reservation):
    assessments = tuple(SequenceConnectionAssessment(r.observation_id,r.failure_kind or "proof_bound_exceeded",None)
                        for r in requests)
    return SequenceConnectionEvidence(parents,measures,requests,None,assessments,
        SequenceConnectionWork(reservation.planning_visits,0,memory,memory,budget.persistent_input_bytes,True),True,budget)


def _full_value_budget(parents,requests,plans,signal,reservation,budget):
    proof_visits,_,_ = _proof_bounds(parents,requests,plans)
    return max(0,budget.maximum_value_visits-reservation.planning_visits-reservation.guard_visits
        -signal.pixel_query_count-signal.value_visit_bound-signal.preflight_value_visit_bound-proof_visits)


def prepare_sequence_connections(field, edges, measurements, *, maximum_value_visits, maximum_temporary_bytes,
                                 persistent_input_bytes):
    budget = SequenceConnectionBudget(maximum_value_visits,maximum_temporary_bytes,persistent_input_bytes)
    parents = tuple(p for p in edges if eligible_sequence_connection_parent(p))
    if not parents:
        return None
    if maximum_value_visits < 4096 or persistent_input_bytes+8192 > maximum_temporary_bytes:
        return SequenceConnectionEvidence(parents,(),(),None,(),SequenceConnectionWork(bound_exceeded=True),False,budget)
    measures = tuple(m for m in measurements if m.query.purpose in {
        QueryPurpose.SEQUENCE_BASELINE,QueryPurpose.SEQUENCE_ANCHOR_WINDOW})
    visits,planning_memory = _counts(parents,measures)
    if visits > maximum_value_visits or planning_memory+persistent_input_bytes > maximum_temporary_bytes:
        return SequenceConnectionEvidence(parents,(),(),None,(),SequenceConnectionWork(
            4096,0,8192,8192,persistent_input_bytes,True),False,budget)
    requests = sequence_connection_requests(parents,measures,source_extent=field.source_extent)
    plans = sequence_connection_plans(field,requests,measures)
    reservation = _phased_reservation(parents,requests,plans,measures,visits,planning_memory,budget)
    if not reservation.admitted:
        return _unadmitted(parents,measures,requests,planning_memory,budget,reservation)
    signal,cache = measure_native_trace_signals(field,reservation.signal_plans,
        maximum_pixel_queries=reservation.signal_value_budget,maximum_temporary_bytes=reservation.signal_memory)
    requests = guard_sequence_connections(parents,requests,measures,signal)
    plans = sequence_connection_plans(field,requests,measures)
    batch = (refine_native_trace_responses(signal,cache,plans,
        maximum_pixel_queries=_full_value_budget(parents,requests,plans,signal,reservation,budget),
        maximum_temporary_bytes=reservation.full_memory) if plans else None)
    cache.release()
    return _finish(parents,measures,requests,signal,batch,planning_memory,budget,reservation)


def _finish(parents,measures,requests,signal,batch,planning_memory,budget,reservation):
    maximum_temporary_bytes,persistent_input_bytes = budget.maximum_temporary_bytes,budget.persistent_input_bytes
    proof_visits,proof_retained,proof_memory = _proof_bounds(parents,requests,() if batch is None else batch.plans)
    proof_fits = batch is not None and not batch.bound_exceeded and (
        persistent_input_bytes+planning_memory+signal.retained_bytes+batch.retained_bytes+proof_memory <= maximum_temporary_bytes)
    if proof_fits:
        assessments = assess_sequence_connections(parents,requests,measures,batch)
    else:
        assessments = tuple(SequenceConnectionAssessment(r.observation_id,r.failure_kind or "proof_bound_exceeded",None)
                            for r in requests)
    release_work = native_trace_response_consumption_work(signal.plans) if batch is None or batch.bound_exceeded else 0
    batch_values = release_work+(0 if batch is None else batch.value_visit_bound+batch.preflight_value_visit_bound)
    batch_retained = 0 if batch is None else batch.retained_bytes
    actual_visits = (reservation.planning_visits+signal.value_visit_bound+signal.preflight_value_visit_bound
                     +reservation.guard_visits+batch_values+(proof_visits if proof_fits else 0))
    retained = planning_memory+signal.retained_bytes+batch_retained+(proof_retained if proof_fits else 0)
    peak = max(planning_memory,planning_memory+signal.peak_temporary_bytes,
               planning_memory+signal.retained_bytes+signal.response_cache_bytes+reservation.guard_memory,
               planning_memory+signal.retained_bytes+(0 if batch is None else batch.peak_temporary_bytes),
               planning_memory+signal.retained_bytes+batch_retained+proof_memory if proof_fits else retained)
    return SequenceConnectionEvidence(parents,measures,requests,batch,assessments,
        SequenceConnectionWork(actual_visits,signal.pixel_query_count+(0 if batch is None else batch.pixel_query_count),
            retained,peak,persistent_input_bytes,batch is not None and (batch.bound_exceeded or not proof_fits)),
        True,budget,signal)


def _validate_bridge_reservation(batch,plans,values,memory,response_sources=None):
    validate_native_trace_bridge_batch(batch)
    if batch.plans != plans or batch.response_source_plans != response_sources:
        raise ValueError("Sequence connection changed its complete original query views")
    if plans:
        _,pixels,visits,_,peak,_,fits = _bridge_reservation(plans,memory,response_sources)
        exceeded = not fits or peak > memory or pixels+visits+native_trace_bridge_preflight_value_visit_bound(plans,response_sources)>values
        if (batch.bound_exceeded != exceeded or batch.required_pixel_query_count != pixels
                or batch.required_value_visit_bound != visits or batch.required_peak_temporary_bytes != peak):
            raise ValueError("Sequence measurement changed its complete source reservation")


def validate_sequence_connection_evidence(evidence, *, source_id, source_extent,
        maximum_value_visits, maximum_temporary_bytes, persistent_input_bytes):
    """Replay frozen queries, original peaks, complete masks and resource phases."""
    from types import SimpleNamespace
    from .transition_peak_validation import validate_peak_source_measurements
    budget = SequenceConnectionBudget(maximum_value_visits,maximum_temporary_bytes,persistent_input_bytes)
    if evidence.budget != budget:
        raise ValueError("Sequence connection changed its frozen caller budget")
    if not evidence.planning_completed:
        expected = (SequenceConnectionWork(bound_exceeded=True)
            if maximum_value_visits < 4096 or persistent_input_bytes+8192 > maximum_temporary_bytes
            else SequenceConnectionWork(4096,0,8192,8192,persistent_input_bytes,True))
        if evidence.work != expected:
            raise ValueError("unplanned Sequence connection erased executed work")
        return
    measures = evidence.measurements
    validate_peak_source_measurements(measures,source_id=source_id,source_extent=source_extent)
    visits,memory = _counts(evidence.parents,measures)
    if visits > maximum_value_visits or memory+persistent_input_bytes > maximum_temporary_bytes:
        raise ValueError("Sequence connection skipped its complete planning reservation")
    requests = sequence_connection_requests(evidence.parents,measures,source_extent=source_extent)
    field = SimpleNamespace(source_id=source_id,source_extent=source_extent)
    plans = sequence_connection_plans(field,requests,measures)
    reservation = _phased_reservation(evidence.parents,requests,plans,measures,visits,memory,budget)
    if not reservation.admitted:
        expected = _unadmitted(evidence.parents,measures,requests,memory,budget,reservation)
    else:
        signal = evidence.signal_batch
        if signal is None:
            raise ValueError('Sequence connection omitted its admitted complete signal stage')
        _validate_bridge_reservation(signal,reservation.signal_plans,reservation.signal_value_budget,reservation.signal_memory)
        requests = guard_sequence_connections(evidence.parents,requests,measures,signal)
        plans = sequence_connection_plans(field,requests,measures)
        batch = evidence.batch
        if bool(plans) != (batch is not None):
            raise ValueError('Sequence connection omitted or invented its complete refinement obligation')
        if batch is not None:
            _validate_bridge_reservation(batch,plans,_full_value_budget(evidence.parents,requests,plans,signal,reservation,budget),
                                         reservation.full_memory,signal.plans)
            validate_native_trace_response_reuse(batch,signal)
        expected = _finish(evidence.parents,measures,requests,signal,batch,memory,budget,reservation)
    if evidence != expected:
        raise ValueError("Sequence connection changed its raw continuity result or work")


def apply_sequence_connections(edges,evidence):
    constraints = {} if evidence is None else {a.observation_id:a.constraint for a in evidence.assessments
                                              if a.constraint is not None}
    return tuple(replace(p,sequence_connection_constraint=constraints[p.observation_id])
                 if p.observation_id in constraints else p for p in edges)


def sequence_connection_persistent_input_bound(measurements, edge_count, cross_extent):
    """Only scalar/tuple ledgers survive the released baseline NumPy arrays.

    Provenance has its own retained byte owner. Per-point DTOs, edge/region
    ledgers, query indices and exterior prefix tuples are additionally covered
    even though the measurement phase borrows the existing immutable objects.
    """
    points = sum(len(m.transitions)+len(m.cross_height_transitions)+len(m.broad_material_transitions)
                 for m in measurements)
    groups = sum(len(m.peak_source_groups) for m in measurements)
    provenance = sum(m.coverage.peak_source_retained_bytes for m in measurements)
    return provenance+4096+1024*(points+groups+len(measurements))+4096*(edge_count+cross_extent)
