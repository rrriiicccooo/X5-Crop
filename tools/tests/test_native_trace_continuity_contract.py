"""Pixel bridges change qualification only after independent peak closure."""
from dataclasses import replace
from copy import deepcopy
import math
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np

from tools.tests.cross_fixture_support import aspect_input, template, binding as fixture_binding
from x5crop.domain import FiniteInterval, PositiveInterval
from x5crop.detection.photo_geometry.boundary_fitting import fit_format_bound_boundary_observation
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementField, PhotoBoundaryMeasurementQuery
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole, QueryPurpose
from x5crop.detection.photo_geometry.native_trace_continuity import (
    NativeTraceContinuityFailure, apply_native_continuity, prepare_native_continuity,
    assess_native_continuity, _planning_reservation,
)
from x5crop.detection.photo_geometry.registered_measurement import measure_registered_queries
from x5crop.detection.photo_geometry.template_cross import fit_template_cross
from x5crop.detection.photo_geometry.template_cross_model import CrossRoleBinding, CrossFitStatus, CrossEvidence
from x5crop.detection.photo_geometry.template_registration import RegisteredCrossEvidence
from x5crop.report.read_models import typed_read_model


def _case(*, broken=False, gapped=False, extra_edge=False, bottom_interval=FiniteInterval(65., 95.)):
    gray = np.full((128, 801), 20, dtype=np.uint8)
    gray[30:80] = np.where(np.arange(801)[None, :] % 2, 190, 210)
    if broken:
        gray[:, 600:615] = 20
    if extra_edge:
        # A fork joins the original boundary through two monotone ramps.
        # Its interior has two negative peaks separated by a positive edge.
        gray[78:80, 601:614] = 20
        gray[80:82, 601:614] = 200
        gray[78:83, 600] = gray[78:83, 614] = [170, 140, 100, 60, 20]
    field = PhotoBoundaryMeasurementField(gray, "horizontal",
        source_rgb=np.repeat(gray[:, :, None].astype(np.uint16)*257, 3, axis=2))
    traces = tuple(range(0, 801, 80))
    queries = tuple(PhotoBoundaryMeasurementQuery(
        query_id=name, registration_index=index, lane_id="lane:bridge-test", purpose=purpose,
        boundary_axis=BoundaryAxis.Y, trace_positions_px=traces,
        search_intervals_px=(interval,)*len(traces),
        transition_ownership_intervals_px=(interval,)*len(traces),
        expected_support_px=80.0, boundary_axis_scale_px_per_mm=PositiveInterval.exact(10.0),
        trace_axis_scale_px_per_mm=PositiveInterval.exact(10.0), measurement_halo_px=4,
        registration_provenance_ids=("registered:bridge-test",),
    ) for index, (name, purpose, interval) in enumerate((
        ("bridge:baseline", QueryPurpose.CROSS_BASELINE, FiniteInterval(0., 127.)),
        ("bridge:top", QueryPurpose.TOP_CORRIDOR, FiniteInterval(15., 35.)),
        ("bridge:bottom", QueryPurpose.BOTTOM_CORRIDOR, bottom_interval),
    )))
    measurements = measure_registered_queries(field, queries)
    bottom = measurements[-1]
    raw = tuple(p for p in bottom.transitions if p.trace_coordinate_px <= 560 and p.polarity == -1
                and (not gapped or p.trace_coordinate_px not in (240, 320)))
    parent = fit_format_bound_boundary_observation(bottom,
        transition_ids=tuple(p.transition_id for p in raw), role=BoundaryRole.BOTTOM,
        source_axis_long=BoundaryAxis.X, boundary_axis_scale_px_per_mm=PositiveInterval.exact(10.0))
    assert parent is not None
    binding = CrossRoleBinding(role=parent.role, run_id="run:bridge-parent", observation_id=parent.observation_id,
        coordinate_interval_px=parent.offset_interval_px, fit_interval_px=parent.offset_interval_px,
        full_interval_px=parent.offset_interval_px, trace_coordinates_px=parent.trace_coordinates_px,
        continuous_support_fraction=parent.continuous_support_fraction,
        independent_support_region_count=parent.independent_support_region_count,
        source_spanning_continuous=parent.source_spanning_continuous,
        role_authorized=parent.right_background_preference_fraction > .5,
        canonical_direction_degrees=math.degrees(math.atan2(-parent.line.normal_x, parent.line.normal_y)),
        fit_direction_interval_degrees=parent.fit_angle_interval_degrees,
        full_direction_interval_degrees=parent.angle_interval_degrees,
        observed_direction_interval_degrees=parent.angle_interval_degrees,
        trace_position_intervals_px=parent.trace_position_intervals_px, physical_line_region=parent.physical_line_region)
    registration = RegisteredCrossEvidence((), (binding,), (parent,), 1,
        registered_top_run_count=0, registered_bottom_run_count=1)
    return field, registration, measurements


def _prepare(case):
    field, registration, measurements = case
    pixels = field.source_extent.width * field.source_extent.height
    return prepare_native_continuity(field, registration, measurements,
        maximum_value_visits=128*pixels, maximum_temporary_bytes=10*pixels+32*1024*1024)


def _cross(registration):
    return fit_template_cross(aspect_input(template=replace(template(count=4), frame_height_px=50.0),
        fixed_height_px=50.0, registered_trace_coordinates_px=tuple(range(0, 801, 80)),
        longitudinal_support_domain_groups_px=((FiniteInterval(0., 160.), FiniteInterval(200., 360.),
            FiniteInterval(400., 560.), FiniteInterval(640., 800.)),),
        top_bindings=(), bottom_bindings=registration.bottom_bindings))


class NativeTraceContinuityContractTest(unittest.TestCase):
    def test_original_pixels_close_an_anchor_that_previously_could_not_project(self):
        case = _case()
        original = case[1]
        parent = original.bottom_bindings[0]
        self.assertTrue(parent.role_authorized)
        self.assertEqual(parent.independent_support_region_count, 3)
        self.assertFalse(parent.source_spanning_continuous)
        self.assertEqual(_cross(original).status, CrossFitStatus.UNRESOLVED)
        evidence = _prepare(case)
        self.assertIsNotNone(evidence)
        self.assertFalse(evidence.work.bound_exceeded)
        self.assertIsNone(evidence.assessments[0].failure_kind)
        extended = apply_native_continuity(original, evidence)
        binding = extended.bottom_bindings[0]
        self.assertFalse(binding.source_spanning_continuous)
        self.assertTrue(binding.effective_source_spanning_continuous)
        self.assertEqual(extended.observations, original.observations)
        self.assertEqual(binding.trace_position_intervals_px, parent.trace_position_intervals_px)
        result = _cross(extended)
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertIsNotNone(result.best)
        self.assertIsNotNone(result.best.direct_bindings[0].native_continuity_constraint)
        from tools.tests.template_test_support import placement_compose, placement_sequence
        from tools.tests.output_fixture_support import _lane
        from x5crop.detection.photo_geometry.template_feasible_geometry import project_format_placement
        from x5crop.detection.photo_geometry.template_output import output_footprint_from_template_placement
        from x5crop.formats import FramePhysicalSpec
        shape = replace(template(count=4), frame_height_px=50.)
        placement = placement_compose(shape, placement_sequence(shape), result.best,
                                      frame_spec=FramePhysicalSpec(10., 5., 2.))
        output = output_footprint_from_template_placement(placement, project_format_placement(placement),
            lane=_lane(), lane_ordinal=4, layout="horizontal")
        self.assertEqual(len(output.boundary_protections), 4)

    def test_same_registered_samples_do_not_close_a_broken_intermediate_path(self):
        complete, broken = _case(), _case(broken=True)
        def geometry(case):
            return [(p.trace_coordinate_px, p.physical_position_interval_px, p.polarity,
                     p.gradient_z, p.tone_z, p.texture_z) for p in case[2][-1].transitions]
        self.assertEqual(geometry(complete), geometry(broken))
        evidence = _prepare(broken)
        self.assertIsNone(evidence.assessments[0].constraint)
        self.assertEqual(evidence.assessments[0].failure_kind,
                         NativeTraceContinuityFailure.DENSE_SIGNAL_UNAVAILABLE)
        self.assertEqual(_cross(apply_native_continuity(broken[1], evidence)).status, CrossFitStatus.UNRESOLVED)

    def test_original_source_digest_is_required_for_every_measured_registered_trace(self):
        case = _case()
        evidence = _prepare(case)
        strips = list(evidence.batch.strips)
        index = next(i for i,s in enumerate(strips) if s.original_trace_sources)
        strip = strips[index]
        sources = list(strip.original_trace_sources)
        sources[0] = replace(sources[0], signal_sha256="f"*64)
        strips[index] = replace(strip, original_trace_sources=tuple(sources))
        batch = replace(evidence.batch, strips=tuple(strips))
        actual = assess_native_continuity(evidence.requests, evidence.measurements, batch)
        self.assertIsNone(actual[0].constraint)
        self.assertEqual(actual[0].failure_kind, NativeTraceContinuityFailure.SOURCE_CONTEXT_CONFLICT)

    def test_local_role_cannot_be_granted_by_a_continuous_signal(self):
        field, original, measurements = _case()
        denied = replace(original, bottom_bindings=(replace(original.bottom_bindings[0], role_authorized=False),))
        pixels = field.source_extent.width*field.source_extent.height
        with patch("x5crop.detection.photo_geometry.native_trace_continuity.continuity_requests",
                   side_effect=AssertionError("no eligible flags must not inspect the raw peak ledger")):
            self.assertIsNone(prepare_native_continuity(field, denied, measurements,
                maximum_value_visits=128*pixels, maximum_temporary_bytes=10*pixels+32*1024*1024))

    def test_disconnected_original_runs_retain_unavailable_planning_work(self):
        case = _case(gapped=True)
        evidence = _prepare(case)
        self.assertIsNotNone(evidence)
        self.assertGreaterEqual(evidence.work.value_visit_bound, _planning_reservation(case[1], case[2])[0])
        self.assertEqual(evidence.work.pixel_query_count, 0)
        self.assertEqual(evidence.assessments[0].failure_kind,
                         NativeTraceContinuityFailure.ORIGINAL_RUN_UNAVAILABLE)
        self.assertIsNone(evidence.assessments[0].constraint)

    def test_a_legal_original_corridor_reaching_the_source_edge_does_not_crash_or_clip_the_proof(self):
        case = _case(bottom_interval=FiniteInterval(65., 127.))
        self.assertTrue(case[2][-1].coverage.complete)
        evidence = _prepare(case)
        self.assertEqual(evidence.assessments[0].failure_kind,
                         NativeTraceContinuityFailure.SOURCE_DOMAIN_UNAVAILABLE)
        self.assertEqual(evidence.work.pixel_query_count, 0)
        self.assertIsNone(evidence.assessments[0].constraint)

    def test_an_unregistered_intermediate_edge_cannot_be_hidden_by_original_samples(self):
        complete, competing = _case(), _case(extra_edge=True)
        def registered_facts(case):
            return tuple((tuple((p.trace_coordinate_px, p.canonical_coordinate_px,
                                 p.physical_position_interval_px, p.polarity, p.gradient_z,
                                 p.tone_z, p.texture_z, p.background_preference_side) for p in m.transitions),
                          tuple(s.signal_sha256 for s in m.peak_trace_sources)) for m in case[2])
        self.assertEqual(registered_facts(complete), registered_facts(competing))
        evidence = _prepare(competing)
        self.assertIsNone(evidence.requests[0].preliminary_failure)
        self.assertIsNone(evidence.assessments[0].constraint)
        self.assertTrue(evidence.assessments[0].conflicting_traces_px)
        self.assertEqual(_cross(apply_native_continuity(competing[1], evidence)).status, CrossFitStatus.UNRESOLVED)

    def test_template_refinements_and_conditional_lines_cannot_seed_pixel_proofs(self):
        field, original, measurements = _case()
        for binding in (replace(original.bottom_bindings[0], evidence=CrossEvidence.TEMPLATE_LOCAL_REFINEMENT),
                        replace(original.bottom_bindings[0], conditional_family_ids=("conditional-family",))):
            with self.subTest(evidence=binding.evidence, conditional=binding.conditional_family_ids):
                inputs = SimpleNamespace(top_bindings=(), bottom_bindings=(binding,), observations=original.observations)
                self.assertIsNone(prepare_native_continuity(field, inputs, measurements,
                    maximum_value_visits=128*field.source_gray.size,
                    maximum_temporary_bytes=10*field.source_gray.size+32*1024*1024))

    def test_remaining_source_budget_cannot_publish_a_partial_pixel_or_proof_batch(self):
        field, registration, measurements = _case()
        planning, _memory = _planning_reservation(registration, measurements)
        for limit in (0, planning+1):
            with self.subTest(limit=limit), patch(
                    "x5crop.detection.photo_geometry.native_trace_continuity.measure_native_trace_bridges",
                    side_effect=AssertionError("unreserved source pixels must not be read")):
                result = prepare_native_continuity(field, registration, measurements,
                    maximum_value_visits=limit, maximum_temporary_bytes=10*field.source_gray.size+32*1024*1024)
                self.assertTrue(result.work.bound_exceeded)
                self.assertIsNone(result.batch)
                self.assertLessEqual(result.work.value_visit_bound, limit)
                self.assertEqual(result.work.pixel_query_count, 0)
                self.assertFalse(any(a.constraint for a in result.assessments))
                self.assertEqual(result.planning_completed, limit != 0)

    def test_a_continuity_certificate_cannot_transfer_photo_roles(self):
        case = _case()
        extended = apply_native_continuity(case[1], _prepare(case)).bottom_bindings[0]
        with self.assertRaisesRegex(ValueError, "original identity or role"):
            replace(extended, role=BoundaryRole.TOP)

    def test_enclosing_consumes_the_same_dense_physical_domain_and_protection(self):
        from x5crop.detection.photo_geometry.template_cross_support import fit_enclosing_support
        from x5crop.detection.photo_geometry.template_feasible_geometry import _support_cross_vertices
        from x5crop.detection.photo_geometry.template_output import _support_trace_intervals, _support_direction_departure_px
        case = _case()
        bottom = apply_native_continuity(case[1], _prepare(case)).bottom_bindings[0]
        constraint = bottom.native_continuity_constraint
        # Isolate the geometric consumer: a new intermediate native interval
        # restricts a state that all original sparse intervals would permit.
        positions = list(constraint.trace_position_intervals_px)
        positions[constraint.trace_coordinates_px.index(600)] = FiniteInterval.exact(80.5)
        bottom = replace(bottom, native_continuity_constraint=replace(
            constraint, trace_position_intervals_px=tuple(positions)))
        traces = case[2][0].query.trace_positions_px
        top = fixture_binding(BoundaryRole.TOP, "enclosing-top", 27., traces=traces,
                              angle_interval=FiniteInterval(-.0001, .0001))
        top = replace(top, trace_position_intervals_px=(FiniteInterval.exact(27.),)*len(traces))
        pool = fit_enclosing_support(template=replace(template(count=4), frame_height_px=50.),
            fixed_height=FiniteInterval.exact(50.), canonical_height_px=50., reference_trace_px=280.,
            top_bindings=(top,), bottom_bindings=(bottom,), registered_trace_coordinates_px=traces,
            longitudinal_support_domain_groups_px=((FiniteInterval(0., 800.),),),
            minimum_shared_trace_support=3, maximum_evaluated_candidates=16)
        self.assertIsNotNone(pool.best)
        placement = SimpleNamespace(cross_fit=SimpleNamespace(enclosing_support_pair=pool.best.pair,
            direct_bindings=(pool.best.top_binding, pool.best.bottom_binding)))
        vertices, _ = _support_cross_vertices(placement)
        self.assertTrue(vertices)
        for _top, position, slope in vertices:
            self.assertAlmostEqual(position + slope*(600.-280.), 80.5)
        self.assertIn((600, FiniteInterval.exact(80.5)), tuple(_support_trace_intervals(bottom)))
        self.assertEqual(_support_direction_departure_px(bottom, 0., FiniteInterval(640., 800.)), 0.)

    def test_ordinary_replay_requires_the_complete_pixel_proof_and_its_consumed_constraint(self):
        from tools.regression.native_continuity_validation import validate_native_continuity
        from tools.regression.report_validation import _read_common_proof
        field, registration, measurements = case = _case()
        evidence = _prepare(case)
        binding = apply_native_continuity(registration, evidence).bottom_bindings[0]
        record = {"measurement": {"source_id": field.source_id, "source_extent": typed_read_model(field.source_extent)},
                  "development": None, "photo_geometry": {"lanes": [{
                      "lane_id": measurements[0].query.lane_id, "native_continuity": typed_read_model(evidence),
                      "native_continuity_work": typed_read_model(evidence.work),
                      "base_cross_registration": typed_read_model(registration),
                      "direct_binding": typed_read_model(binding),
                  }]}}
        validate_native_continuity(record, read_proof=_read_common_proof)
        for mutation in ("assessment", "constraint", "source", "block"):
            with self.subTest(mutation=mutation):
                changed = deepcopy(record)
                lane = changed["photo_geometry"]["lanes"][0]
                if mutation == "assessment":
                    lane["native_continuity"]["assessments"] = []
                elif mutation == "constraint":
                    lane["direct_binding"]["native_continuity_constraint"] = None
                elif mutation == "source":
                    lane["native_continuity"]["batch"]["strips"][0]["original_trace_sources"][0]["signal_sha256"] = "f"*64
                else:
                    lane["native_continuity"]["batch"]["strips"] = []
                with self.assertRaises(ValueError):
                    validate_native_continuity(changed, read_proof=_read_common_proof)
