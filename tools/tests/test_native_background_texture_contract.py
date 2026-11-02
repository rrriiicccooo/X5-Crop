from dataclasses import replace
from unittest.mock import patch
import unittest

import numpy as np

from tools.tests.template_test_support import cross_binding
from x5crop.domain import EvidenceState, FiniteInterval, PositiveInterval
from x5crop.image.gray import BaseGrayParameters, make_base_gray_u8
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementQuery
from x5crop.detection.photo_geometry.model import BoundaryAxis, BoundaryRole, QueryPurpose, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.registered_measurement import make_photo_boundary_measurement_field, measure_registered_queries
from x5crop.detection.photo_geometry.native_background_texture import (
    native_background_texture_query, measure_native_background_texture, validate_native_background_textures,
)
from x5crop.detection.photo_geometry.template_registration import local_cross_refinement_anchors
from tools.regression.report_validation import _read_common_proof
from x5crop.report.read_models import typed_read_model
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementSet


def fixture(*, textured=True, vertical=False):
    rgb = np.full((120, 121, 3), 20 * 257, dtype=np.uint16)
    rgb[:50] += (np.arange(50, dtype=np.uint16)[:, None, None] % 2) * 50
    rgb[50:] = 140 * 257
    if textured:
        rgb[50:] += (np.arange(121, dtype=np.uint16)[None, :, None] % 2) * 300
    if vertical:
        rgb = rgb.transpose(1, 0, 2).copy()
    field = make_photo_boundary_measurement_field(make_base_gray_u8(rgb, BaseGrayParameters()),
        "vertical" if vertical else "horizontal", source_rgb=rgb)
    scale = PositiveInterval.exact(20.0)
    traces = (20, 40, 60, 80, 100)
    intervals = (FiniteInterval(0.0, 119.0),) * len(traces)
    query = PhotoBoundaryMeasurementQuery("native-texture:test", 0, "lane:0", QueryPurpose.TOP_CORRIDOR,
        BoundaryAxis.X if vertical else BoundaryAxis.Y, traces, intervals, intervals, 120.0,
        scale, scale, SPEC.measurement_halo_px(20.0), ("native-texture:source",))
    baseline = replace(query, query_id="native-texture:baseline", registration_index=1,
                       purpose=QueryPurpose.CROSS_BASELINE)
    return field, (query, baseline)


class NativeBackgroundTextureContractTest(unittest.TestCase):
    def test_native_two_axis_texture_adds_role_information_without_replacing_gray_facts(self):
        field, queries = fixture()
        before = field.source_rgb.copy()
        measured, _baseline = measure_registered_queries(field, queries)
        self.assertTrue(measured.transitions)
        for transition in measured.transitions:
            # The original centre-column sees no inside longitudinal texture.
            self.assertGreaterEqual(transition.left_texture_mean, transition.right_texture_mean)
            self.assertEqual(transition.background_preference_side, -1)
            self.assertEqual(transition.native_background_texture.state, EvidenceState.SUPPORTED)
        validate_native_background_textures(measured, field.source_extent, SPEC)
        self.assertGreater(measured.coverage.native_texture_pixel_query_count, 0)
        np.testing.assert_array_equal(field.source_rgb, before)
        decoded = _read_common_proof(typed_read_model(measured), PhotoBoundaryMeasurementSet)
        self.assertEqual(decoded, measured)

    def test_both_axes_transpose_with_the_registered_source(self):
        horizontal, hqueries = fixture()
        vertical, vqueries = fixture(vertical=True)
        h, _ = measure_registered_queries(horizontal, hqueries)
        v, _ = measure_registered_queries(vertical, vqueries)
        self.assertEqual(len(h.transitions), len(v.transitions))
        for left, right in zip(h.transitions, v.transitions, strict=True):
            self.assertEqual(left.native_background_texture.left_texture_mean,
                             right.native_background_texture.left_texture_mean)
            self.assertEqual(left.native_background_texture.right_texture_mean,
                             right.native_background_texture.right_texture_mean)
            self.assertEqual(left.background_preference_side, right.background_preference_side)

    def test_flat_interior_does_not_gain_an_outside_role(self):
        field, queries = fixture(textured=False)
        measured, _ = measure_registered_queries(field, queries)
        self.assertTrue(measured.transitions)
        self.assertTrue(all(t.background_preference_side != -1 for t in measured.transitions))

    def test_kernel_cannot_be_clipped_or_moved_to_another_transition(self):
        field, queries = fixture()
        measured, _ = measure_registered_queries(field, queries)
        transition = measured.transitions[0]
        query = native_background_texture_query(field.source_extent, queries[0], transition, SPEC)
        clipped = replace(query, trace_coordinate_px=0)
        evidence = measure_native_background_texture(field, clipped)
        self.assertEqual(evidence.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(evidence.background_preference_side, 0)
        with self.assertRaisesRegex(ValueError, "original transition"):
            replace(transition, native_background_texture=evidence)
        changed = replace(measured, transitions=(replace(transition, native_background_texture=None),
                                                *measured.transitions[1:]))
        with self.assertRaisesRegex(ValueError, "complete registered pixel domain"):
            validate_native_background_textures(changed, field.source_extent, SPEC)

    def test_whole_batch_preflight_fails_before_native_reads(self):
        field, queries = fixture()
        for bounds in ({"max_pixel_query_count": 0}, {"max_peak_temporary_bytes": 0}):
            with self.subTest(bounds=bounds), patch(
                    "x5crop.detection.photo_geometry.registered_measurement.measure_native_background_texture",
                    side_effect=AssertionError("native pixels read before whole-batch preflight")):
                measured, _ = measure_registered_queries(field, queries, **bounds)
            self.assertEqual(measured.state, EvidenceState.UNAVAILABLE)
            self.assertFalse(measured.transitions)
            self.assertFalse(measured.coverage.complete)
            self.assertTrue(measured.coverage.native_texture_bound_exceeded)
            self.assertGreater(measured.coverage.native_texture_query_count, 0)
            self.assertEqual(measured.coverage.native_texture_completed_count, 0)

    def test_local_pair_cannot_suppress_a_complete_anchor_refinement(self):
        domains = ((FiniteInterval(0, 15), FiniteInterval(18, 32), FiniteInterval(35, 49),
                    FiniteInterval(52, 59), FiniteInterval(60, 75), FiniteInterval(80, 100)),)
        top = cross_binding(BoundaryRole.TOP, "top:complete", 100.0,
                            traces=tuple(range(0, 101, 4)), source_spanning=True)
        bottom = cross_binding(BoundaryRole.BOTTOM, "bottom:local", 340.0,
                               traces=(64, 68, 72), source_spanning=False, independent_regions=2)
        self.assertEqual(local_cross_refinement_anchors((top,), (bottom,), FiniteInterval(238, 242), domains),
                         (top,))
