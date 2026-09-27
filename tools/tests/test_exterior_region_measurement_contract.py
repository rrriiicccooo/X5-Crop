from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from x5crop.domain import Box, FiniteInterval
from x5crop.detection.photo_geometry.exterior_region_measurement import (
    ExteriorRegionAvailability, ExteriorRegionQuery, _box_sums,
    measure_exterior_region,
)
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementField
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.registered_transition_measurement import measure_trace
from x5crop.run_local_identity import source_identity_scope
from x5crop.report.read_models import typed_read_model
from tools.regression.report_validation import _read_common_proof
from x5crop.detection.photo_geometry.exterior_region_measurement import ExteriorRegionMeasurement


def _source():
    gray = np.full((600,1500), 255, dtype=np.uint8)
    for begin, end in ((100,450),(550,950),(1050,1450)):
        gray[90:540,begin:end] = 80
    # A visible weak patch between any coarse nine-trace samples.
    gray[60:90,430:450] = 250
    return gray


def _measure(gray, *, layout="horizontal", box=None):
    if box is None:
        box = Box(0,0,gray.shape[1],gray.shape[0])
    field = PhotoBoundaryMeasurementField(gray if layout == "horizontal" else gray.T.copy(), layout)
    query = ExteriorRegionQuery("lane:0",layout,box,10.,"physical-plan:test")
    return measure_exterior_region(field,query)


class ExteriorRegionMeasurementContractTest(unittest.TestCase):
    def test_query_identity_survives_source_scope_and_report_replay(self):
        with source_identity_scope():
            result = _measure(_source())
            serialized = typed_read_model(result)
        with source_identity_scope():
            unrelated = replace(result.query, registration_provenance_id="another-plan")
            self.assertNotEqual(unrelated.query_id, result.work.query_id)
            replay = _read_common_proof(serialized, ExteriorRegionMeasurement)
            self.assertEqual(replay, result)

    def test_exact_kernel_sums_match_independent_pixel_windows(self):
        rng = np.random.default_rng(157)
        gray = rng.integers(0,256,(31,47),dtype=np.uint8)
        sums, peak = _box_sums(gray)
        expected = np.array([[int(gray[y:y+5,x:x+5].sum()) for x in range(43)] for y in range(27)])
        np.testing.assert_array_equal(sums,expected)
        mirrored, _ = _box_sums(gray[::-1,::-1])
        np.testing.assert_array_equal(mirrored,sums[::-1,::-1])
        negative, _ = _box_sums(255-gray)
        np.testing.assert_array_equal(negative,6375-sums)
        self.assertGreaterEqual(peak,sums.nbytes)

    def test_local_weak_content_is_protected_in_every_column(self):
        result = _measure(_source())
        self.assertEqual(result.availability,ExteriorRegionAvailability.AVAILABLE)
        index = 440-2
        self.assertGreater(result.sides[0].color_prefix_px[index],60.)
        self.assertLess(result.sides[0].weak_prefix_px[index],60.)
        self.assertIsNone(result.sides[0].color_prefix_px[0])
        self.assertFalse(hasattr(result,"role_authorized"))
        self.assertFalse(hasattr(result,"canonical_direction_degrees"))
        self.assertEqual(result.work.completed_trace_count,1496)
        self.assertLess(result.work.pixel_query_count,128*600*1500)
        self.assertLess(result.work.peak_temporary_bytes,10*600*1500+32*1024**2)

    def test_orientation_polarity_and_cross_reflection_preserve_prefix_geometry(self):
        source = _source()
        original = _measure(source)
        vertical = _measure(source,layout="vertical")
        negative = _measure(255-source)
        reflected = _measure(source[::-1].copy())
        along = _measure(source[:,::-1].copy())
        for side in range(2):
            for key in ("color_prefix_px","weak_prefix_px"):
                values = getattr(original.sides[side],key)
                self.assertEqual(getattr(vertical.sides[side],key),values)
                self.assertEqual(getattr(negative.sides[side],key),values)
                self.assertEqual(getattr(along.sides[side],key),values[::-1])
                expected = tuple(None if v is None else 599.-v for v in values)
                self.assertEqual(getattr(reflected.sides[1-side],key),expected)

    def test_nonzero_lane_origin_is_preserved(self):
        source = np.zeros((660,1600),dtype=np.uint8)
        source[30:630,50:1550] = _source()
        original = _measure(_source())
        result = _measure(source,box=Box(50,30,1550,630))
        for old, new in zip(original.sides,result.sides,strict=True):
            for key in ("color_prefix_px","weak_prefix_px"):
                self.assertEqual(getattr(new,key),tuple(None if x is None else x+30 for x in getattr(old,key)))

    def test_dense_weak_predicate_matches_scalar_registered_measurement(self):
        source = _source()
        result = _measure(source)
        query = result.query
        for side in (0,1):
            sums, _ = _box_sums((source if side == 0 else source[::-1])[:query.read_depth])
            for column in (100,430,438,550,1100):
                values = sums[:,column]/25.
                scalar = measure_trace(values,FiniteInterval(query.window+query.gap,query.coordinate_count-1),10.,SPEC)
                credible = ((scalar.gradient_z >= SPEC.gradient_z_minimum) |
                    (np.maximum(scalar.tone_z,scalar.texture_z) >= SPEC.tone_or_texture_z_minimum))
                expected = None if not credible.any() else float(scalar.coordinates[np.flatnonzero(credible)[0]])+1.5
                if side and expected is not None:
                    expected = 599.-expected
                self.assertEqual(result.sides[side].weak_prefix_px[column],expected)

    def test_seed_unavailable_remains_distinct_from_complete_measurement(self):
        result = _measure(np.full((600,1500),200,dtype=np.uint8))
        self.assertEqual(result.availability,ExteriorRegionAvailability.SEED_DEPARTURE_UNOBSERVABLE)
        self.assertEqual(result.work.completed_trace_count,result.work.registered_trace_count)
        self.assertTrue(all(v is None for side in result.sides for v in side.color_prefix_px))
        tiny = _measure(np.zeros((20,20),dtype=np.uint8))
        self.assertEqual(tiny.availability,ExteriorRegionAvailability.QUERY_UNOBSERVABLE)
        self.assertEqual(tiny.work.pixel_query_count,0)

    def test_query_coverage_and_work_cannot_be_silently_shrunk(self):
        result = _measure(_source())
        for changed in (
            replace(result.work,pixel_query_count=0),
            replace(result.work,completed_trace_count=1),
            replace(result.work,coordinate_sample_count=1),
            replace(result.work,query_id="other"),
        ):
            with self.assertRaises(ValueError):
                replace(result,work=changed)
        for side in (
            replace(result.sides[0],color_prefix_px=result.sides[0].color_prefix_px[:-1]),
            replace(result.sides[0],seed_departure_count_by_third=(1000,1,1)),
            replace(result.sides[0],weak_prefix_px=(0.,)+result.sides[0].weak_prefix_px[1:]),
        ):
            with self.assertRaises(ValueError):
                replace(result,sides=(side,result.sides[1]))
        with self.assertRaises(ValueError):
            replace(result,availability=ExteriorRegionAvailability.QUERY_UNOBSERVABLE)
        with self.assertRaises(ValueError):
            replace(result.query,work_box=Box(0.,0,1500,600))
        query = replace(result.query,work_box=Box(0,0,1600,600))
        with self.assertRaises(ValueError):
            measure_exterior_region(PhotoBoundaryMeasurementField(_source(),"horizontal"),query)


if __name__ == "__main__":
    unittest.main()
