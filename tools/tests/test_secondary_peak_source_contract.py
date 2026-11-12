"""Secondary selection identity survives without acquiring gradient authority."""
from dataclasses import replace
from hashlib import sha256
import unittest

import numpy as np

from x5crop.domain import EvidenceState, FiniteInterval, ObservationId, PositiveInterval, WorkspaceExtent
from x5crop.detection.photo_geometry.model import BoundaryAxis, QueryPurpose, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.measurement_model import (
    PhotoBoundaryCoverageReceipt, PhotoBoundaryMeasurementQuery, PhotoBoundaryMeasurementSet, PhotoBoundaryTransition,
)
from x5crop.detection.photo_geometry.registered_transition_measurement import TraceMeasurement, measured_transition_peaks
from x5crop.detection.photo_geometry.transition_peak_source import TransitionPeakTraceSource, TransitionPeakReference
from x5crop.detection.photo_geometry.transition_peak_capture import TransitionPeakCapture, peak_source_receipt
from x5crop.detection.photo_geometry.transition_peak_validation import validate_peak_source_measurements
from x5crop.detection.photo_geometry import sequence_connections as sequence
from x5crop.detection.photo_geometry import native_trace_continuity as cross
from tools.tests.test_sequence_connections_contract import _case as sequence_case, _prepare as sequence_prepare
from tools.tests.test_native_trace_continuity_contract import _case as cross_case, _prepare as cross_prepare
from tools.tests import test_coarse_native_association_contract as association_fixture
from x5crop.detection.photo_geometry.model import BoundaryRole
from x5crop.detection.photo_geometry.template_coarse_sides import coarse_enclosing_binding
from x5crop.detection.photo_geometry.template_output import _support_direction_departure_px


def _trace(sign=1):
    coordinates = np.arange(4, 124, dtype=np.int32)
    gradient = np.full(120, .5)
    tone = np.zeros(120)
    tone[42:51] = (3., 4., 5., 7., 8., 7., 5., 4., 3.)
    texture = np.zeros(120)
    signed = np.full(120, sign*.1)
    digest = sha256()
    for array in (coordinates, gradient, tone, texture, signed):
        digest.update(array.tobytes())
    source = TransitionPeakTraceSource('secondary:field', WorkspaceExtent(64,128), BoundaryAxis.Y,
        10, (4,123), 3, 1, 3., 3., digest.hexdigest())
    return TraceMeasurement(coordinates, gradient, tone, texture, signed,
        np.full(120,10.), np.full(120,30.), np.full(120,1.), np.full(120,5.),
        temporary_bytes=0, peak_source=source)


def _transition(peak):
    return PhotoBoundaryTransition(ObservationId('raw:secondary'), 'query:secondary', 0, 10,
        peak.canonical_coordinate, peak.localization_interval, peak.physical_position_interval,
        peak.gradient_z, peak.tone_z, peak.texture_z, peak.left_tone, peak.right_tone,
        peak.left_texture, peak.right_texture, peak.polarity, peak.peak_width_px, peak.prominence,
        peak.local_noise, texture_sample_coordinate_px=50, peak_source=peak.source_reference)


def _captured(sign=1, *, maximum_bytes=10**6):
    measured = _trace(sign)
    capture = TransitionPeakCapture(maximum_bytes)
    peak, = measured_transition_peaks(measured, SPEC, split_gradient_reversals=False,
                                      peak_source_capture=capture)
    point = _transition(peak)
    coverage = PhotoBoundaryCoverageReceipt('query:secondary', 1, 1, 120, 120, 120, 1, 0, True)
    points,coverage,sources,groups = peak_source_receipt((point,), coverage, (measured.peak_source,), capture)
    query = PhotoBoundaryMeasurementQuery('query:secondary', 0, 'lane:secondary', QueryPurpose.SEQUENCE_ANCHOR_WINDOW,
        BoundaryAxis.Y, (10,), (FiniteInterval(4.,123.),), (FiniteInterval(4.,123.),), 64.,
        PositiveInterval.exact(10.), PositiveInterval.exact(10.), SPEC.measurement_halo_px(10.), ('fixed:source',))
    return measured,peak,capture,PhotoBoundaryMeasurementSet(query, EvidenceState.SUPPORTED,
        points, (), coverage, peak_trace_sources=sources, peak_source_groups=groups)


def _replace_with_secondary(measurement, identity):
    original = next(p for p in measurement.transitions if p.transition_id == identity)
    group = next(g for g in measurement.peak_source_groups if g.primitive_id == original.peak_source.group_id)
    assert len(group.candidate_peak_coordinates_px) == 1
    secondary = replace(group, reliable_gradient_partitions=(), selection_basis='secondary')
    reference = TransitionPeakReference(secondary.primitive_id, 0, original.peak_source.source_coordinate_px, 0)
    point = replace(original, gradient_z=1., tone_z=6., peak_source=reference)
    return replace(measurement,
        transitions=tuple(point if p.transition_id == identity else p for p in measurement.transitions),
        peak_source_groups=tuple(secondary if g is group else g for g in measurement.peak_source_groups))


def _association_case(*, missing=False, conditional=False):
    fixture = association_fixture.CoarseNativeAssociationContractTest()
    groups = tuple(fixture._group(BoundaryRole.TOP,t,view=(8,60)) for t in fixture._NATIVE_TRACES)
    points = tuple(fixture._transition('query:top-corridor',BoundaryRole.TOP,i,t,g)
                   for i,(t,g) in enumerate(zip(fixture._NATIVE_TRACES,groups,strict=True)))
    case = list(fixture._case(native_top_groups=groups,native_top_transitions=points,
                              conditional_top=conditional))
    measurements = []
    for measurement in case[1]:
        matches = tuple(p for p in measurement.transitions
                        if p.trace_coordinate_px == 20 and p.canonical_coordinate_px == 50.)
        if matches:
            original, = matches
            group = next(g for g in measurement.peak_source_groups if g.primitive_id == original.peak_source.group_id)
            secondary = replace(group,reliable_gradient_partitions=(),selection_basis='secondary')
            reference = None if missing else TransitionPeakReference(secondary.primitive_id,0,50,0)
            point = replace(original,gradient_z=1.,tone_z=6.,peak_source=reference)
            measurement = fixture._ns_replace(measurement,
                transitions=tuple(point if p is original else p for p in measurement.transitions),
                peak_source_groups=tuple(secondary if g is group else g for g in measurement.peak_source_groups))
        measurements.append(measurement)
    case[1] = tuple(measurements)
    support = case[0].enclosing_support
    track = replace(support.minimum_track,retained_transitions=tuple(
        p for p in measurements[0].transitions if p.canonical_coordinate_px == 50.))
    case[0] = fixture._ns_replace(case[0],enclosing_support=replace(support,minimum_track=track))
    return fixture,case


class SecondaryPeakSourceContractTest(unittest.TestCase):
    def test_selector_preserves_the_same_peak_and_records_an_unpolarized_original_identity(self):
        for sign in (-1,0,1):
            measured,peak,capture,result = _captured(sign)
            original, = measured_transition_peaks(measured, SPEC, split_gradient_reversals=False)
            self.assertEqual(replace(peak,source_group=None,source_reference=None), original)
            self.assertEqual(peak.polarity, sign)
            self.assertEqual(peak.source_reference.polarity, 0)
            self.assertEqual(peak.source_group.selection_basis, 'secondary')
            self.assertTrue(peak.source_group.complete)
            peak.source_reference.validate_group(peak.source_group)
            self.assertEqual(result.coverage.peak_source_reference_count, 1)
            self.assertEqual(result.coverage.peak_source_retained_bytes,
                measured.peak_source.retained_bytes+peak.source_group.retained_bytes+peak.source_reference.retained_bytes)
            self.assertLessEqual(result.coverage.peak_source_retained_bytes,
                                measured.peak_source.retained_bytes+capture.reserved_bytes)
            validate_peak_source_measurements((result,), source_id=measured.peak_source.source_id,
                                              source_extent=measured.peak_source.source_extent)

    def test_no_gradient_sign_or_selection_basis_can_be_invented(self):
        _,peak,_,result = _captured()
        point, = result.transitions
        for changed in ({'gradient_z':3.}, {'tone_z':1.,'texture_z':1.}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                replace(point, **changed)
        with self.assertRaises(ValueError):
            replace(peak.source_reference, polarity=1).validate_group(peak.source_group)
        with self.assertRaisesRegex(ValueError, 'selection identity'):
            replace(result, transitions=(replace(point,peak_source=None),),
                coverage=replace(result.coverage,peak_source_reference_count=0,
                    peak_source_retained_bytes=result.coverage.peak_source_retained_bytes-512))

    def test_capture_failure_keeps_geometry_and_discards_the_whole_reference_batch(self):
        _,original,_,_ = _captured()
        _,failed,_,result = _captured(maximum_bytes=1024)
        self.assertEqual(replace(original,source_group=None,source_reference=None), failed)
        self.assertTrue(result.coverage.peak_source_bound_exceeded)
        self.assertEqual(result.peak_source_groups, ())
        self.assertEqual(result.coverage.peak_source_reference_count, 0)
        self.assertIsNone(result.transitions[0].peak_source)

    def test_recovered_identity_reaches_output_protection_only_with_independent_continuity(self):
        fixture,missing = _association_case(missing=True)
        proofs,_ = fixture._associate(missing)
        self.assertNotIn(BoundaryRole.TOP,fixture._roles(proofs))
        fixture,complete = _association_case()
        proofs,_ = fixture._associate(complete)
        top, = (p for p in proofs if p.native_observation.role == BoundaryRole.TOP)
        binding = coarse_enclosing_binding(top.coarse_track,BoundaryRole.TOP,pair_id='pair:secondary')
        linked = replace(binding,coarse_native_constraint=top.constraint)
        span = FiniteInterval(10.,35.)
        self.assertGreater(_support_direction_departure_px(binding,0.,span),0.)
        self.assertEqual(_support_direction_departure_px(linked,0.,span),0.)
        self.assertEqual(binding.full_interval_px,linked.full_interval_px)
        self.assertEqual(top.native_observation,complete[3])
        for denied in ('conditional','discontinuous'):
            with self.subTest(denied=denied):
                fixture,case = _association_case(conditional=denied == 'conditional')
                if denied == 'discontinuous':
                    case[2] = fixture._ns_replace(case[2],top_bindings=tuple(
                        replace(b,source_spanning_continuous=False) for b in case[2].top_bindings))
                proofs,_ = fixture._associate(case)
                self.assertNotIn(BoundaryRole.TOP,fixture._roles(proofs))

    def test_secondary_identity_cannot_seed_sequence_gradient_connections(self):
        case = sequence_case()
        evidence = sequence_prepare(case)
        identity = case[1].transition_ids[0]
        measurements = tuple(_replace_with_secondary(m,identity) if any(
            p.transition_id == identity for p in m.transitions) else m for m in case[2])
        requests = sequence.sequence_connection_requests(evidence.parents,measurements,
            source_extent=case[0].source_extent)
        self.assertEqual(requests[0].failure_kind, 'original_gradient_unavailable')
        # An earlier complete strong pixel batch cannot promote the new ref0.
        denied = sequence.assess_sequence_connections(evidence.parents,evidence.requests,measurements,evidence.batch)
        self.assertEqual(denied[0].failure_kind, 'original_gradient_unavailable')
        self.assertIsNone(denied[0].constraint)

    def test_secondary_identity_cannot_seed_cross_gradient_connections(self):
        case = cross_case()
        evidence = cross_prepare(case)
        identity = case[1].observations[0].transition_ids[0]
        measurements = tuple(_replace_with_secondary(m,identity) if any(
            p.transition_id == identity for p in m.transitions) else m for m in case[2])
        requests = cross.continuity_requests(case[1],measurements,source_extent=case[0].source_extent)
        self.assertEqual(requests[0].preliminary_failure, cross.NativeTraceContinuityFailure.ORIGINAL_PEAK_UNAVAILABLE)
        denied = cross.assess_native_continuity(evidence.requests,measurements,evidence.batch)
        self.assertEqual(denied[0].failure_kind, cross.NativeTraceContinuityFailure.ORIGINAL_PEAK_UNAVAILABLE)
        self.assertIsNone(denied[0].constraint)
