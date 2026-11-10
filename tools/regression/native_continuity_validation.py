"""Replay source-bound native continuity without trusting output qualification."""
from types import SimpleNamespace

from x5crop.domain import WorkspaceExtent
from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.native_trace_continuity import (
    NativeTraceContinuityEvidence, NativeTraceContinuityWork,
    NativeTraceContinuityFailure, NativeTraceContinuityAssessment,
    continuity_requests, continuity_plans, assess_native_continuity, _proof_reservation, _planning_reservation,
    _planning_metadata_reservation,
)
from x5crop.detection.photo_geometry.template_registration import RegisteredCrossEvidence
from x5crop.detection.photo_geometry.transition_peak_validation import validate_peak_source_measurements
from x5crop.detection.photo_geometry.native_trace_bridge_measurement import validate_native_trace_bridge_batch


def validate_development_native_continuity(lane, production, measurements, *, bounds, exterior,
                                         source_id, source_extent, read_proof):
    """Replay admission from the complete inputs before any Cross work ran."""
    from x5crop.detection.photo_geometry.model import QueryPurpose
    from x5crop.detection.photo_geometry.sequence_connection_model import SequenceConnectionWork
    from x5crop.detection.photo_geometry.coarse_native_association_model import CoarseNativeAssociationWork
    from x5crop.detection.photo_geometry.template_runtime_model import late_measurement_peak
    from x5crop.detection.photo_geometry.native_trace_bridge_measurement import (
        native_trace_bridge_preflight_value_visit_bound, _prepare,
    )

    base = read_proof(lane['base_cross_registration'], RegisteredCrossEvidence)
    eligible = any(b.evidence == 'direct' and not b.conditional_family_ids and b.role_authorized
        and b.independent_support_region_count >= 3 and not b.source_spanning_continuous
        and b.physical_line_region is not None for b in (*base.top_bindings, *base.bottom_bindings))
    raw = production['native_continuity']
    if (raw is not None) != eligible:
        raise ValueError('native continuity changed its complete eligible parent set')
    if raw is None:
        return
    evidence = read_proof(raw, NativeTraceContinuityEvidence)
    work = lane['measurement_work']
    sequence = (None if work['sequence_connection_work'] is None else
                read_proof(work['sequence_connection_work'], SequenceConnectionWork))
    association = (None if work['coarse_native_association_work'] is None else
                   read_proof(work['coarse_native_association_work'], CoarseNativeAssociationWork))
    coverage = tuple(m.coverage for m in measurements)
    prior_pixels = exterior.work.pixel_query_count + sum(c.pixel_query_count for c in coverage)
    prior_values = sum(c.peak_source_value_visit_bound for c in coverage)
    if sequence is not None:
        prior_pixels += sequence.pixel_query_count
        prior_values += sequence.value_visit_bound
    if association is not None:
        prior_values += association.value_visit_bound
    values = max(0, bounds.max_pixel_queries-prior_pixels-prior_values)
    memory = max(0, bounds.max_peak_temporary_bytes-late_measurement_peak(
        coverage, exterior.work, sequence, association))
    metadata_visits, metadata_bytes = _planning_metadata_reservation(base, measurements)
    metadata_fits = metadata_visits <= values and metadata_bytes <= memory
    if evidence.planning_metadata_completed != metadata_fits:
        raise ValueError('native continuity changed its original metadata admission')
    if not metadata_fits:
        return
    original = tuple(m for m in measurements if m.query.purpose in {
        QueryPurpose.CROSS_BASELINE, QueryPurpose.TOP_CORRIDOR, QueryPurpose.BOTTOM_CORRIDOR})
    if evidence.measurements != original:
        raise ValueError('native continuity changed its complete registered measurement inventory')
    planning_visits, planning_bytes = _planning_reservation(base, original)
    planning_fits = planning_visits <= values and planning_bytes <= memory
    if evidence.planning_completed != planning_fits:
        raise ValueError('native continuity changed its original planning admission')
    if not planning_fits:
        return
    # Ordinary proof replay checks the requests/plans and complete work. Here
    # the frozen original remaining pool must admit U, even when final W is low.
    plans = continuity_plans(SimpleNamespace(source_id=source_id, source_extent=source_extent),
                             evidence.requests, original)
    visits, _, peak = _proof_reservation(evidence.requests, plans)
    preflight = native_trace_bridge_preflight_value_visit_bound(plans)
    proof_fits = planning_visits+visits+preflight <= values and peak <= memory
    if (evidence.batch is not None) != proof_fits:
        raise ValueError('native continuity changed its original proof admission')
    if not proof_fits:
        return
    batch = evidence.batch
    validate_native_trace_bridge_batch(batch)
    if batch.plans != plans:
        raise ValueError('native continuity changed its original full-row plans')
    pixels = required = required_peak = 0
    fits = True
    if plans:
        _, pixels, required, _, required_peak, _, fits = _prepare(plans, memory-peak)
    fits = fits and required_peak <= memory-peak and pixels+required+preflight <= values-planning_visits-visits
    if (batch.bound_exceeded != (not fits)
            or batch.required_peak_temporary_bytes != required_peak):
        raise ValueError('native continuity changed its original whole-batch admission')


def validate_native_continuity(record, *, read_proof):
    source_id = record["measurement"]["source_id"]
    extent = WorkspaceExtent(**record["measurement"]["source_extent"])
    field = SimpleNamespace(source_id=source_id, source_extent=extent)
    development = {} if record["development"] is None else {
        lane["lane_id"]: lane for lane in record["development"]["lanes"]}
    for lane in record["photo_geometry"]["lanes"]:
        raw = lane["native_continuity"]
        raw_work = lane["native_continuity_work"]
        constraints = {}
        if raw is None:
            if raw_work is not None:
                raise ValueError("native continuity lost its complete source work")
        else:
            evidence = read_proof(raw, NativeTraceContinuityEvidence)
            if evidence.measurements:
                validate_peak_source_measurements(evidence.measurements, source_id=source_id, source_extent=extent)
            base = read_proof(lane["base_cross_registration"], RegisteredCrossEvidence)
            if not evidence.planning_completed:
                metadata_visits, metadata_bytes = _planning_metadata_reservation(base, evidence.measurements)
                expected_unplanned = (NativeTraceContinuityWork(metadata_visits, 0, metadata_bytes, True)
                    if evidence.planning_metadata_completed else NativeTraceContinuityWork(0, 0, 0, True))
                if raw_work != typed_read_model(expected_unplanned) or evidence.batch is not None:
                    raise ValueError("unplanned native continuity lost its completed metadata work")
                requests = ()
            else:
                requests = continuity_requests(base, evidence.measurements, source_extent=extent)
            if typed_read_model(requests) != raw["requests"]:
                raise ValueError("native continuity changed its complete independent parent set")
            plans = continuity_plans(field, requests, evidence.measurements)
            visits, retained, peak = _proof_reservation(requests, plans)
            planning_visits, planning_bytes = _planning_reservation(base, evidence.measurements)
            batch = evidence.batch
            if batch is None:
                expected = tuple(NativeTraceContinuityAssessment(r.parent.observation_id,
                    r.preliminary_failure or NativeTraceContinuityFailure.PROOF_BOUND_EXCEEDED,
                    (), None) for r in requests)
                expected_work = (NativeTraceContinuityWork(planning_visits, planning_bytes, planning_bytes, True)
                                 if evidence.planning_completed else expected_unplanned)
            else:
                validate_native_trace_bridge_batch(batch)
                if batch.plans != plans:
                    raise ValueError("native continuity changed its original full-row queries")
                expected = assess_native_continuity(requests, evidence.measurements, batch)
                expected_work = NativeTraceContinuityWork(
                    planning_visits + visits + batch.completed_value_visit_bound + batch.preflight_value_visit_bound,
                    retained + batch.retained_bytes, max(planning_bytes, peak + batch.peak_temporary_bytes),
                    batch.bound_exceeded, batch.pixel_query_count)
            if (typed_read_model(expected) != raw["assessments"]
                    or typed_read_model(expected_work) != raw["work"] or raw_work != raw["work"]):
                raise ValueError("native continuity changed its raw peaks, branch result or work")
            for measured in evidence.measurements:
                if (measured.query.lane_id != lane["lane_id"]
                        or any(s.source_id != source_id or s.source_extent != extent
                               for s in (*measured.peak_trace_sources,
                                         *(g.source for g in measured.peak_source_groups)))):
                    raise ValueError("native continuity changed its source context")
            constraints = {str(a.observation_id): typed_read_model(a.constraint)
                           for a in expected if a.constraint is not None}
        def visit(value):
            if isinstance(value, dict):
                if "native_continuity_constraint" in value:
                    expected = (constraints.get(value["observation_id"])
                                if value.get("evidence") == "direct" else None)
                    if value["native_continuity_constraint"] != expected:
                        raise ValueError("Cross binding changed its independent native continuity")
                for key, child in value.items():
                    if key != "base_cross_registration":
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(lane)
        if lane["lane_id"] in development:
            detail = development[lane["lane_id"]]
            if detail["native_continuity"] != raw or detail["measurement_work"]["native_continuity_work"] != raw_work:
                raise ValueError("development native continuity changed production facts")
            visit(detail)
