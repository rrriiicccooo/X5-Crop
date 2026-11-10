"""A completed sparse bridge cannot bypass its original whole admission."""
from types import SimpleNamespace
import unittest

from tools.tests.test_native_trace_continuity_contract import _case, _prepare
from tools.regression.native_continuity_validation import validate_development_native_continuity
from tools.regression.report_validation import _read_common_proof
from x5crop.detection.photo_geometry.native_trace_continuity import (
    prepare_native_continuity, _planning_metadata_reservation, _planning_reservation,
)
from x5crop.report.read_models import typed_read_model


def _replay(case, evidence, values, memory):
    field, base, measurements = case
    coverage = tuple(m.coverage for m in measurements)
    original = sum(c.pixel_query_count+c.peak_source_value_visit_bound for c in coverage)
    peak = max(c.peak_temporary_bytes for c in coverage)
    lane = {'base_cross_registration': typed_read_model(base), 'measurement_work': {
        'sequence_connection_work': None, 'coarse_native_association_work': None}}
    validate_development_native_continuity(lane, {'native_continuity': typed_read_model(evidence)},
        measurements, bounds=SimpleNamespace(max_pixel_queries=original+values,
            max_peak_temporary_bytes=peak+memory),
        exterior=SimpleNamespace(work=SimpleNamespace(pixel_query_count=0, peak_temporary_bytes=0)),
        source_id=field.source_id, source_extent=field.source_extent, read_proof=_read_common_proof)


class NativeContinuityAdmissionReplayContractTest(unittest.TestCase):
    def test_complete_sparse_inventory_cannot_justify_an_unaffordable_initial_reservation(self):
        case = _case()
        field, base, measurements = case
        evidence = _prepare(case)
        values = 128*field.source_gray.size
        memory = 10*field.source_gray.size+32*1024*1024
        _replay(case, evidence, values, memory)
        optimistic = evidence.work.pixel_query_count+evidence.work.value_visit_bound
        self.assertLess(evidence.batch.completed_value_visit_bound, evidence.batch.required_value_visit_bound)
        with self.assertRaisesRegex(ValueError, 'admission'):
            _replay(case, evidence, optimistic, memory)
        refused = prepare_native_continuity(field, base, measurements,
            maximum_value_visits=optimistic, maximum_temporary_bytes=memory)
        self.assertTrue(refused.work.bound_exceeded)
        self.assertFalse(refused.batch.strips)
        _replay(case, refused, optimistic, memory)

    def test_metadata_planning_and_proof_failures_replay_the_original_remaining_pool(self):
        case = _case()
        field, base, measurements = case
        metadata, metadata_bytes = _planning_metadata_reservation(base, measurements)
        planning, _ = _planning_reservation(base, measurements)
        memory = 10*field.source_gray.size+32*1024*1024
        for values, allowance in ((0,memory), (metadata,memory), (planning+1,memory),
                                  (128*field.source_gray.size,metadata_bytes-1)):
            with self.subTest(values=values, memory=allowance):
                evidence = prepare_native_continuity(field, base, measurements,
                    maximum_value_visits=values, maximum_temporary_bytes=allowance)
                self.assertTrue(evidence.work.bound_exceeded)
                _replay(case, evidence, values, allowance)
