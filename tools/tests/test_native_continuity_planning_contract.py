"""Reuse neutral planning facts without dropping any failed obligation."""
from dataclasses import replace
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.test_native_trace_continuity_contract import _case, _prepare
from x5crop.domain import ObservationId
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.native_trace_continuity import (
    _planning_reservation, _planning_metadata_reservation, prepare_native_continuity,
    continuity_requests, apply_native_continuity, NativeTraceContinuityFailure,
)


class NativeContinuityPlanningContractTest(unittest.TestCase):
    def test_ineligible_bindings_pay_metadata_scans_without_multiplying_raw_planning(self):
        field, base, measured = _case()
        visits, memory = _planning_reservation(base, measured)
        extra = (replace(base.bottom_bindings[0], role_authorized=False),)*40
        larger = SimpleNamespace(top_bindings=(), bottom_bindings=(*base.bottom_bindings, *extra),
                                 observations=base.observations)
        larger_visits, larger_memory = _planning_reservation(larger, measured)
        self.assertEqual(larger_visits-visits, 128*40 + 16*40*len(base.observations))
        self.assertEqual(larger_memory-memory, 256*40)
        self.assertEqual(continuity_requests(base, measured, source_extent=field.source_extent),
                         continuity_requests(larger, measured, source_extent=field.source_extent))

    def test_failed_original_runs_still_pay_the_same_raw_planning_scope(self):
        field, base, measured = case = _case(gapped=True)
        result = _prepare(case)
        self.assertEqual(result.assessments[0].failure_kind, NativeTraceContinuityFailure.ORIGINAL_RUN_UNAVAILABLE)
        self.assertGreaterEqual(result.work.value_visit_bound, _planning_reservation(base, measured)[0])
        self.assertGreaterEqual(result.work.peak_temporary_bytes, _planning_reservation(base, measured)[1])
        self.assertEqual(len(result.requests), 1)

    def test_metadata_preflight_is_paid_before_eligibility_lookup_and_no_raw_prefix_is_read(self):
        field, base, measured = _case()
        metadata, memory = _planning_metadata_reservation(base, measured)
        with patch("x5crop.detection.photo_geometry.native_trace_continuity._planning_reservation",
                   side_effect=AssertionError("eligibility lookup must be reserved first")):
            result = prepare_native_continuity(field, base, measured,
                maximum_value_visits=metadata-1, maximum_temporary_bytes=memory)
        self.assertFalse(result.planning_metadata_completed)
        self.assertEqual(result.work.value_visit_bound, 0)
        with patch("x5crop.detection.photo_geometry.native_trace_continuity.continuity_requests",
                   side_effect=AssertionError("raw planning must be reserved first")):
            result = prepare_native_continuity(field, base, measured,
                maximum_value_visits=metadata, maximum_temporary_bytes=10*field.source_gray.size+32*1024*1024)
        self.assertTrue(result.planning_metadata_completed)
        self.assertFalse(result.planning_completed)
        self.assertEqual(result.work.value_visit_bound, metadata)
        self.assertEqual(result.work.peak_temporary_bytes, memory)
        self.assertEqual(result.requests, ())
        self.assertEqual(len(result.measurements), 3)
        from x5crop.report.read_models import typed_read_model
        from tools.regression.report_validation import _read_common_proof
        from tools.regression.native_continuity_validation import validate_native_continuity
        record = {"measurement": {"source_id": field.source_id, "source_extent": typed_read_model(field.source_extent)},
                  "development": None, "photo_geometry": {"lanes": [{"lane_id": measured[0].query.lane_id,
                      "native_continuity": typed_read_model(result), "native_continuity_work": typed_read_model(result.work),
                      "base_cross_registration": typed_read_model(base),
                      "direct_binding": typed_read_model(base.bottom_bindings[0])}]}}
        validate_native_continuity(record, read_proof=_read_common_proof)
        forged = deepcopy(record)
        lane = forged["photo_geometry"]["lanes"][0]
        lane["native_continuity"]["work"]["value_visit_bound"] = 0
        lane["native_continuity_work"]["value_visit_bound"] = 0
        with self.assertRaises(ValueError):
            validate_native_continuity(forged, read_proof=_read_common_proof)

    def test_each_trace_projection_is_shared_by_all_its_raw_peaks(self):
        field, base, measured = _case()
        bottom = measured[-1]
        extra = tuple(replace(p, transition_id=ObservationId(f"duplicate:{p.transition_id}"))
                      for p in bottom.transitions if p.trace_coordinate_px>560)
        coverage = replace(bottom.coverage,
            peak_source_reference_count=bottom.coverage.peak_source_reference_count+len(extra),
            peak_source_retained_bytes=bottom.coverage.peak_source_retained_bytes
                                      +sum(p.peak_source.retained_bytes for p in extra))
        bottom = replace(bottom, transitions=(*bottom.transitions, *extra), coverage=coverage)
        original = PhysicalLineRegion.project
        with patch.object(PhysicalLineRegion, "project", autospec=True, side_effect=original) as project:
            requests = continuity_requests(base, (*measured[:-1], bottom), source_extent=field.source_extent)
        self.assertEqual(project.call_count, len({p.trace_coordinate_px for p in extra}))
        self.assertEqual(requests[0].preliminary_failure, NativeTraceContinuityFailure.RAW_PEAK_COMPETITION)
        self.assertIsNone(_prepare((field, base, (*measured[:-1], bottom))).assessments[0].constraint)

    def test_unavailable_or_already_applied_proofs_reuse_the_immutable_registration(self):
        case = _case(broken=True)
        evidence = _prepare(case)
        self.assertIs(apply_native_continuity(case[1], evidence), case[1])
        case = _case()
        evidence = _prepare(case)
        extended = apply_native_continuity(case[1], evidence)
        self.assertIs(apply_native_continuity(extended, evidence), extended)
