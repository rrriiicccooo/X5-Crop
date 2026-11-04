"""Replay source-bound native continuity without trusting output qualification."""
from types import SimpleNamespace

from x5crop.domain import WorkspaceExtent
from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.native_trace_continuity import (
    NativeTraceContinuityEvidence, NativeTraceContinuityWork,
    NativeTraceContinuityFailure, NativeTraceContinuityAssessment,
    continuity_requests, continuity_plans, assess_native_continuity, _proof_reservation, _planning_reservation,
)
from x5crop.detection.photo_geometry.template_registration import RegisteredCrossEvidence
from x5crop.detection.photo_geometry.transition_peak_validation import validate_peak_source_measurements
from x5crop.detection.photo_geometry.native_trace_bridge_measurement import validate_native_trace_bridge_batch


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
                if (raw_work != typed_read_model(NativeTraceContinuityWork(0, 0, 0, True))
                        or evidence.requests or evidence.measurements or evidence.batch is not None):
                    raise ValueError("unplanned native continuity exposed a measurement prefix")
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
                                 if evidence.planning_completed else NativeTraceContinuityWork(0, 0, 0, True))
            else:
                validate_native_trace_bridge_batch(batch)
                if batch.plans != plans:
                    raise ValueError("native continuity changed its original full-row queries")
                expected = assess_native_continuity(requests, evidence.measurements, batch)
                expected_work = NativeTraceContinuityWork(
                    planning_visits + visits + batch.value_visit_bound + batch.preflight_value_visit_bound,
                    retained + batch.retained_bytes, peak + batch.peak_temporary_bytes,
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
