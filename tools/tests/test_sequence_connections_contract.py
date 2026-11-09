"""Positive native connections must change states without dropping local risk."""
from dataclasses import replace
from types import SimpleNamespace
import math
import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.photo_geometry_support import make_native_test_field
from x5crop.domain import FiniteInterval, PositiveInterval, ObservationId
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementQuery
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole, QueryPurpose, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.observation_types import BoundaryEdgeObservation, BoundaryEdgeMeasurementBasis
from x5crop.detection.photo_geometry.registered_measurement import measure_registered_queries
from x5crop.detection.photo_geometry.robust_line_fit import physical_line_region
from x5crop.detection.photo_geometry.sequence_connections import (
    prepare_sequence_connections,apply_sequence_connections,validate_sequence_connection_evidence,
    sequence_connection_persistent_input_bound,
)
from x5crop.detection.photo_geometry.sequence_connection_model import SequenceConnectionConstraint, SequenceConnectionWork
from x5crop.detection.photo_geometry.line_observations import PhysicalLineRegion
from x5crop.detection.photo_geometry.template_model import SequenceRoleLineEvidence
from x5crop.detection.photo_geometry.template_output import _sequence_raw_outward_departure
from x5crop.detection.photo_geometry.template_runtime_model import combined_measurement_peak, late_measurement_peak


def _case(*, broken=False, transpose=False):
    gray = np.full((180,201),30,dtype=np.uint8)
    for y in range(180):
        edge = 60+round(3*math.sin(2*math.pi*(y-20)/40))
        # A resolved ramp keeps adjacent signed-response rows four-connected
        # while preserving measurable sub-sample variation between anchors.
        gray[y] = (30+170*np.clip((np.arange(201)-edge)/8.,0.,1.)).astype(np.uint8)
    if broken:
        gray[90] = 30
    axis = BoundaryAxis.X
    if transpose:
        gray = gray.T.copy()
        axis = BoundaryAxis.Y
    field = make_native_test_field(gray,'vertical' if transpose else 'horizontal')
    traces = (40,60,80,100,120,140)
    scale = PositiveInterval.exact(20.)
    baseline = PhotoBoundaryMeasurementQuery('sequence:baseline',0,'lane:connection',QueryPurpose.SEQUENCE_BASELINE,
        axis,traces,(FiniteInterval(0.,200.),)*6,(FiniteInterval(0.,200.),)*6,120.,scale,scale,
        SPEC.measurement_halo_px(20.),('registered:connection',))
    window = replace(baseline,query_id='sequence:window',registration_index=1,purpose=QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
        search_intervals_px=(FiniteInterval(40.,100.),)*6,transition_ownership_intervals_px=(FiniteInterval(40.,100.),)*6)
    measurements = measure_registered_queries(field,(baseline,window))
    original = tuple(p for p in measurements[1].transitions if p.trace_coordinate_px in (60,80,100,120))
    assert len(original)==4 and all(p.peak_source is not None for p in original)
    region = physical_line_region(tuple((p.trace_coordinate_px,p.physical_position_interval_px) for p in original),
        math.tan(math.radians(SPEC.maximum_measurable_line_angle_degrees)),0.)
    center = original[0].canonical_coordinate_px
    protected = FiniteInterval(center-2.,center+2.)
    projected = region.project(0.)
    parent = BoundaryEdgeObservation(ObservationId('native:parent'),'native:run',projected,0.,center,
        FiniteInterval(center-.5,center+.5),FiniteInterval(min(protected.minimum,projected.minimum),
            max(protected.maximum,projected.maximum)),tuple(p.transition_id for p in original),
        tuple(p.trace_coordinate_px for p in original),1,4/6,1.,0.,0.,FiniteInterval.exact(0.),
        FiniteInterval(-4.,4.),BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE,
        ObservationId('aggregate:support'),(BoundaryRole.START,),physical_line_region=region,
        position_protection_interval_px=protected)
    return field,parent,measurements


def _prepare(case,**limits):
    field,parent,measurements = case
    pixels = field.source_extent.width*field.source_extent.height
    budget = dict(maximum_value_visits=128*pixels-sum(m.coverage.pixel_query_count+m.coverage.peak_source_value_visit_bound
        for m in measurements),maximum_temporary_bytes=10*pixels+32*1024*1024,
        persistent_input_bytes=sequence_connection_persistent_input_bound(measurements,1,180))
    return prepare_sequence_connections(field,(parent,),measurements,**(budget|limits))


def _validate(case,evidence):
    field,_,_ = case
    return validate_sequence_connection_evidence(evidence,source_id=field.source_id,source_extent=field.source_extent,
        maximum_value_visits=evidence.budget.maximum_value_visits,
        maximum_temporary_bytes=evidence.budget.maximum_temporary_bytes,
        persistent_input_bytes=evidence.budget.persistent_input_bytes)


class SequenceConnectionsContractTest(unittest.TestCase):
    def test_late_memory_keeps_persistent_inputs_after_streaming_buffers_are_released(self):
        sequence = SequenceConnectionWork(retained_bytes=20,peak_temporary_bytes=800,persistent_input_bytes=150)
        coverage = (SimpleNamespace(peak_temporary_bytes=100),)
        association = SimpleNamespace(peak_temporary_bytes=30)
        continuity = SimpleNamespace(peak_temporary_bytes=40)
        self.assertEqual(late_measurement_peak(coverage,None,sequence,association,continuity),240)
        self.assertEqual(combined_measurement_peak(coverage,None,sequence,association,continuity),950)
        self.assertEqual(late_measurement_peak((SimpleNamespace(peak_temporary_bytes=250),),None,sequence),270)

    def test_same_registered_samples_do_not_prove_a_broken_intermediate_edge(self):
        complete,broken = _case(),_case(broken=True)
        a,b = complete[2][0],broken[2][0]
        self.assertEqual([s.signal_sha256 for s in a.peak_trace_sources],
                         [s.signal_sha256 for s in b.peak_trace_sources])
        positive,negative = _prepare(complete),_prepare(broken)
        _validate(complete,positive)
        _validate(broken,negative)
        self.assertIsNotNone(positive.assessments[0].constraint)
        self.assertIsNone(negative.assessments[0].constraint)
        self.assertTrue(negative.assessments[0].failure_kind)
        self.assertEqual(apply_sequence_connections((broken[1],),negative),(broken[1],))

    def test_complete_signal_failure_keeps_all_obligations_without_a_peak_refinement(self):
        case = _case(broken=True)
        with patch('x5crop.detection.photo_geometry.native_trace_bridge_measurement.measured_transition_peak_geometry',
                   side_effect=AssertionError('failed connection cannot require peak refinement')):
            evidence = _prepare(case)
        self.assertTrue(evidence.planning_completed)
        self.assertFalse(evidence.work.bound_exceeded)
        self.assertIsNotNone(evidence.signal_batch)
        self.assertIsNone(evidence.batch)
        self.assertEqual(evidence.parents,(case[1],))
        _validate(case,evidence)
        with self.assertRaisesRegex(ValueError,'signal stage'):
            _validate(case,replace(evidence,signal_batch=None))
        with self.assertRaisesRegex(ValueError,'continuity result'):
            _validate(case,replace(evidence,requests=(replace(evidence.requests[0],failure_kind=None),)))

    def test_signal_guard_alone_cannot_grant_a_positive_native_constraint(self):
        from x5crop.detection.photo_geometry.sequence_connections import assess_sequence_connections
        case = _case()
        evidence = _prepare(case)
        self.assertIsNotNone(evidence.assessments[0].constraint)
        self.assertTrue(all(not p.record_peaks for p in evidence.signal_batch.plans))
        self.assertTrue(all(p.record_peaks for p in evidence.batch.plans))
        with self.assertRaises(ValueError):
            assess_sequence_connections(evidence.parents,evidence.requests,evidence.measurements,evidence.signal_batch)

    def test_signal_guard_does_not_decode_unused_group_support_or_clip_a_line(self):
        from x5crop.detection.photo_geometry.sequence_connections import guard_sequence_connections
        case = _case()
        evidence = _prepare(case)
        with (patch('x5crop.detection.photo_geometry.native_trace_continuity.decode_credible_mask',
                    side_effect=AssertionError('guard does not assess complete peak groups')),
              patch('x5crop.detection.photo_geometry.native_trace_continuity._clip_line_region',
                    side_effect=AssertionError('guard does not assess a common physical line'))):
            self.assertEqual(guard_sequence_connections(evidence.parents,evidence.requests,evidence.measurements,
                                                       evidence.signal_batch),evidence.requests)

    def test_new_native_states_keep_old_and_new_local_protection_on_both_axes(self):
        for transpose in (False,True):
            with self.subTest(transpose=transpose):
                case = _case(transpose=transpose)
                evidence = _prepare(case)
                _validate(case,evidence)
                parent = case[1]
                edge = apply_sequence_connections((parent,),evidence)[0]
                self.assertIsNotNone(edge.sequence_connection_constraint)
                self.assertEqual(replace(edge,sequence_connection_constraint=None),parent)
                self.assertLess(edge.effective_full_position_interval_px.width,parent.full_position_interval_px.width)
                protection = edge.sequence_connection_constraint.position_protection_interval_px
                self.assertGreater(protection.width,parent.position_protection_interval_px.width)
                for point in (parent.position_protection_interval_px.minimum,parent.position_protection_interval_px.maximum,
                              protection.minimum,protection.maximum):
                    self.assertTrue(edge.effective_full_position_interval_px.contains(point))
                extra = FiniteInterval(parent.canonical_position_px-12.,parent.canonical_position_px+9.)
                material = replace(edge,full_position_interval_px=FiniteInterval(
                    min(parent.full_position_interval_px.minimum,extra.minimum),
                    max(parent.full_position_interval_px.maximum,extra.maximum)),position_protection_interval_px=extra)
                self.assertLessEqual(material.effective_full_position_interval_px.minimum,extra.minimum)
                self.assertGreaterEqual(material.effective_full_position_interval_px.maximum,extra.maximum)

    def test_full_or_group_and_raw_results_cannot_be_replaced_by_unchanged_and_masks(self):
        case = _case()
        evidence = _prepare(case)
        strips = tuple(replace(s,credible_mask_hex=np.packbits(np.ones(
            (s.trace_stop_px-s.trace_start_px)*(s.coordinate_stop_px-s.coordinate_start_px),dtype=np.uint8),
            bitorder='little').tobytes().hex()) for s in evidence.batch.strips)
        altered = replace(evidence,batch=replace(evidence.batch,strips=strips))
        with self.assertRaisesRegex(ValueError,'signal masks'):
            _validate(case,altered)

    def test_unadmitted_batch_never_reads_a_favorable_prefix(self):
        case = _case()
        with patch('x5crop.detection.photo_geometry.sequence_connections.measure_native_trace_signals',
                   side_effect=AssertionError('unadmitted pixels were read')):
            evidence = _prepare(case,maximum_value_visits=0)
        self.assertFalse(evidence.planning_completed)
        self.assertIsNone(evidence.batch)
        self.assertTrue(evidence.work.bound_exceeded)
        self.assertEqual(evidence.work.pixel_query_count,0)
        _validate(case,evidence)

    def test_inferred_raw_departure_cancels_only_its_own_shared_width_state(self):
        identity = ObservationId('sequence:raw-parent')
        region = PhysicalLineRegion(0.,((100.,0.),(110.,0.)))
        constraint = SequenceConnectionConstraint(identity,'source:query',(ObservationId('p:1'),ObservationId('p:2')),
            region,(0,1),(FiniteInterval(100.,110.),)*2,FiniteInterval(100.,110.))
        direct = SequenceRoleLineEvidence(identity,0.,FiniteInterval.exact(105.),FiniteInterval.exact(0.),region,
                                          sequence_connection_constraint=constraint)
        for direction in (1,-1):
            for parent_role in (BoundaryRole.START,BoundaryRole.END):
                for width in (20.,40.):
                    opposite = BoundaryRole.END if parent_role==BoundaryRole.START else BoundaryRole.START
                    sign = direction if opposite==BoundaryRole.END else -direction
                    inferred = replace(direct,physical_position_offset_px=FiniteInterval(min(sign*20.,sign*40.),
                                                                                         max(sign*20.,sign*40.)))
                    parent = SimpleNamespace(role=parent_role,line_evidence=direct)
                    child = SimpleNamespace(role=opposite,line_evidence=inferred)
                    frame = SimpleNamespace(start=parent if parent_role==BoundaryRole.START else child,
                                            end=parent if parent_role==BoundaryRole.END else child)
                    state = SimpleNamespace(sequence_start_px=105. if parent_role==BoundaryRole.START else 105.+sign*width,
                        sequence_end_px=105. if parent_role==BoundaryRole.END else 105.+sign*width)
                    self.assertEqual(_sequence_raw_outward_departure(frame,child,state,direction),5.)


if __name__ == '__main__':
    unittest.main()
