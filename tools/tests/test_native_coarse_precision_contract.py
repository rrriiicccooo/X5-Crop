from __future__ import annotations

import unittest
import numpy as np

from tools.tests.cross_fixture_support import _lane, aspect_input, binding, native_coarse_fixture, template
from x5crop.image.gray import BaseGrayParameters, make_base_gray_u8
from x5crop.detection.photo_geometry.coarse_strip_support import (
    _measure_coarse_short_trace_lattice,
    registered_coarse_support_queries,
)
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC
from x5crop.detection.photo_geometry.registered_transition_measurement import (
    measured_broad_material_peaks,
    measure_trace,
)


class NativeCoarsePrecisionContractTest(unittest.TestCase):
    def test_native_material_survives_uint8_collapse_without_changing_sharp(self):
        lane, plan = _lane()
        query = registered_coarse_support_queries(
            lane, layout="horizontal", measurement_plan=plan,
        )[1]
        rgb = np.zeros((322, 2320, 3), dtype=np.uint16)
        rgb[:, 1160:] = 65535
        values = np.full(322, 128 * 257 + 20, dtype=np.uint16)
        values[161:] += 100
        values[162::2] += 16
        for column in query.trace_positions_px:
            rgb[:, column] = values[:, None]
        gray = make_base_gray_u8(rgb, BaseGrayParameters())
        samples = np.stack([gray[:, column] for column in query.trace_positions_px])
        self.assertTrue(np.all(samples == 128))
        before = rgb.copy()
        measured, peak = _measure_coarse_short_trace_lattice(
            samples, query, source_rgb=rgb,
        )
        np.testing.assert_array_equal(rgb, before)
        self.assertGreater(peak, samples.nbytes)
        for ordinal, trace in enumerate(measured):
            sharp = measure_trace(
                samples[ordinal], query.search_intervals_px[ordinal],
                query.boundary_axis_scale_px_per_mm.maximum,
                PHOTO_BOUNDARY_MEASUREMENT_SPEC,
            )
            for name in ("coordinates", "gradient_z", "tone_z", "texture_z",
                         "signed_gradient", "left_tone", "right_tone"):
                np.testing.assert_array_equal(getattr(trace, name), getattr(sharp, name))
            peaks = measured_broad_material_peaks(trace, PHOTO_BOUNDARY_MEASUREMENT_SPEC)
            self.assertTrue(any(140 < p.canonical_coordinate < 180 for p in peaks))


class NativeCoarseOwnerContractTest(unittest.TestCase):
    def test_same_physical_sharp_and_native_pair_keeps_both_raw_proofs(self):
        from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus
        from tools.regression.report_validation import _validate_native_coarse_side_support
        coarse, inputs, result, lane, queries, registered, sources = native_coarse_fixture()
        self.assertEqual((inputs.registered_top_run_count, inputs.registered_bottom_run_count), (0, 0))
        self.assertEqual(result.status, CrossFitStatus.RESOLVED)
        self.assertEqual(len(result.support_pair_bindings), 2)
        self.assertIsNone(result.best.direct_bindings[0].coarse_side_fact)
        self.assertEqual(len(_validate_native_coarse_side_support(lane, queries, registered, sources)), 2)

    def test_report_rejects_omitted_raw_path_and_omitted_competitor(self):
        from copy import deepcopy
        from tools.regression.report_validation import _validate_native_coarse_side_support
        _, _, _, lane, queries, registered, sources = native_coarse_fixture()
        for key in ("raw_path", "candidate", "work", "budget", "height"):
            changed = deepcopy(lane)
            if key == "raw_path":
                changed["search"]["coarse_strip_support"]["enclosing_side_facts"].pop()
            elif key == "candidate":
                changed["cross_competition"]["support_pair_bindings"].pop()
            elif key == "budget":
                changed["cross_input"]["maximum_evaluated_fits"] = 8192
                changed["cross_competition"]["receipt"]["evaluated_fit_bound"] = 8192
            elif key == "height":
                changed["cross_input"]["fixed_height_px"]["minimum"] -= 1
            else:
                changed["cross_competition"]["receipt"]["evaluated_fit_count"] -= 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                _validate_native_coarse_side_support(changed, queries, registered, sources)

    def test_report_rejects_window_forgery_that_consistently_hides_native_competition(self):
        from copy import deepcopy
        from dataclasses import replace
        from x5crop.domain import FiniteInterval
        from x5crop.detection.photo_geometry.coarse_enclosing_model import CoarseSideRegistrationReceipt
        from x5crop.detection.photo_geometry.template_cross import fit_template_cross
        from x5crop.report.read_models import typed_read_model
        from tools.regression.report_validation import _validate_native_coarse_side_support
        coarse, inputs, _, lane, queries, registered, sources = native_coarse_fixture()
        changed = deepcopy(lane)
        top = tuple(item for item in inputs.top_bindings if item.coarse_side_fact is None)
        bottom = tuple(item for item in inputs.bottom_bindings if item.coarse_side_fact is None)
        narrowed = replace(coarse, enclosing_side_facts=(),
            short_axis=replace(coarse.short_axis, direct_interval_px=FiniteInterval(160.0, 161.0)))
        forged = replace(inputs, top_bindings=top, bottom_bindings=bottom,
            fitted_observation_count=len(top)+len(bottom),
            coarse_side_registration=CoarseSideRegistrationReceipt(0, 0, 0, 512-len(top)-len(bottom)))
        changed['search']['coarse_strip_support'] = typed_read_model(narrowed)
        changed['cross_input'] = typed_read_model(forged)
        changed['cross_competition'] = typed_read_model(fit_template_cross(forged))
        surviving = {key:value for key,value in registered.items() if value['coarse_side_fact'] is None}
        # All altered downstream ledgers agree; the unchanged complete aggregate
        # peak measurement is what must disprove the forged selection window.
        with self.assertRaisesRegex(ValueError, 'aggregate endpoint reduction'):
            _validate_native_coarse_side_support(changed, queries, surviving, sources)

    def test_report_binds_review_context_to_phase_without_promoting_authority(self):
        from copy import deepcopy
        from tools.regression.report_validation import _validate_native_coarse_side_support
        _, inputs, _, lane, queries, registered, sources = native_coarse_fixture()
        lane["phase_competition"] = {"best": None, "runner_up": None, "status": "unresolved"}
        _validate_native_coarse_side_support(lane, queries, registered, sources)
        changed = deepcopy(lane)
        changed["cross_input"]["review_support_domain_groups_px"] = [[
            {"minimum": 100.0 * ordinal, "maximum": 100.0 * ordinal + 50.0}
            for ordinal in range(inputs.template.count)
        ]]
        with self.assertRaisesRegex(ValueError, "retained Review context"):
            _validate_native_coarse_side_support(changed, queries, registered, sources)

    def test_retained_singleton_fits_are_reused_within_the_actual_work_bound(self):
        from unittest.mock import patch
        import importlib
        from x5crop.domain import FiniteInterval
        from x5crop.detection.photo_geometry.model import BoundaryRole
        from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus, CrossFailureKind
        cross = importlib.import_module('x5crop.detection.photo_geometry.template_cross')
        support = importlib.import_module('x5crop.detection.photo_geometry.template_cross_support')
        inputs = aspect_input(template=template(), fixed_height_px=FiniteInterval(239.0, 241.0),
            top_bindings=(binding(BoundaryRole.TOP, 'outer-top', 100.0, source_spanning=False),),
            bottom_bindings=(binding(BoundaryRole.BOTTOM, 'nearest-bottom', 340.0, source_spanning=False),
                             binding(BoundaryRole.BOTTOM, 'runner-bottom', 341.0, source_spanning=False)),
            maximum_evaluated_fits=4)
        with patch.object(cross, '_fit_from_group', wraps=cross._fit_from_group) as fits, \
             patch.object(support, '_candidate', wraps=support._candidate) as proofs:
            result = cross.fit_template_cross(inputs)
        self.assertEqual(result.status, CrossFitStatus.UNRESOLVED)
        self.assertEqual(result.failure_kind, CrossFailureKind.NON_EQUIVALENT_FITS)
        self.assertEqual(fits.call_count, 2)
        self.assertEqual(proofs.call_count, 2)
        self.assertEqual(result.receipt.evaluated_fit_count, fits.call_count + proofs.call_count)

    def test_aggregate_peaks_cannot_leave_or_exceed_the_single_registered_profile(self):
        from dataclasses import replace
        from x5crop.domain import FiniteInterval
        from x5crop.detection.photo_geometry.measurement_model import (
            CoarseAggregatePeak, PhotoBoundaryMeasurementSet,
        )
        from tools.regression.report_validation import _read_common_proof
        _, _, _, _, queries, *_ = native_coarse_fixture()
        measurement = _read_common_proof(queries[1], PhotoBoundaryMeasurementSet)
        aggregate = measurement.coarse_aggregate
        search = measurement.query.search_intervals_px[0]
        outside = search.maximum + 1.0
        with self.assertRaisesRegex(ValueError, 'single registered profile'):
            replace(measurement, coarse_aggregate=replace(aggregate,
                peaks=(CoarseAggregatePeak(outside, FiniteInterval.exact(outside)),)))
        count = int(search.maximum-search.minimum)+2
        peak = CoarseAggregatePeak(search.minimum, FiniteInterval.exact(search.minimum))
        with self.assertRaisesRegex(ValueError, 'single registered profile'):
            replace(measurement, coarse_aggregate=replace(aggregate, peaks=(peak,)*count))

    def test_side_registration_overflow_performs_no_partial_fits(self):
        from unittest.mock import patch
        from x5crop.detection.photo_geometry.template_coarse_sides import register_coarse_side_facts
        coarse, *_ = native_coarse_fixture()
        with patch("x5crop.detection.photo_geometry.template_coarse_sides._fit_track") as fit:
            top, bottom, work = register_coarse_side_facts(coarse.enclosing_side_facts, remaining_bound=1)
        fit.assert_not_called()
        self.assertEqual((top, bottom, work.attempted_count), ((), (), 0))
        self.assertTrue(work.bound_exceeded)

    def test_native_prefit_encloses_physical_states_outside_statistical_band(self):
        from dataclasses import replace
        from tools.tests.photo_geometry_support import make_side_measurement_set
        from x5crop.domain import FiniteInterval, PositiveInterval
        from x5crop.detection.photo_geometry.coarse_enclosing_support import _fit_track
        from x5crop.detection.photo_geometry.coarse_enclosing_model import (
            CoarseSupportSide, CoarseEnclosingMeasurementBasis,
        )
        measured = make_side_measurement_set(tuple((40.0,) for _ in range(9)))
        query = replace(measured.query, boundary_axis_scale_px_per_mm=PositiveInterval(25.0, 25.0))
        transitions = tuple(replace(raw,
            localization_interval_px=FiniteInterval.exact(40.0),
            physical_position_interval_px=FiniteInterval(30.0, 50.0))
            for raw in measured.transitions)
        track = _fit_track(query, side=CoarseSupportSide.MINIMUM,
            measurement_basis=CoarseEnclosingMeasurementBasis.BROAD_MATERIAL,
            transitions=transitions, reference_trace_px=40.0)
        self.assertIsNotNone(track)
        self.assertGreater(track.fit_position_interval_px.minimum, 30.0)
        self.assertLess(track.fit_position_interval_px.maximum, 50.0)
        # Both flat lines satisfy every original raw interval. Neither may be
        # pruned by the later Cross interval sweep's representative line band.
        self.assertLessEqual(track.full_position_interval_px.minimum, 30.0)
        self.assertGreaterEqual(track.full_position_interval_px.maximum, 50.0)

    def test_unpaired_native_side_cannot_become_an_aperture_review_hypothesis(self):
        from dataclasses import replace
        from x5crop.detection.photo_geometry.template_cross import fit_template_cross
        from x5crop.detection.photo_geometry.coarse_enclosing_model import CoarseSideRegistrationReceipt
        _, inputs, *_ = native_coarse_fixture()
        top = tuple(b for b in inputs.top_bindings if b.coarse_side_fact is not None)
        result = fit_template_cross(replace(inputs, top_bindings=top, bottom_bindings=(),
            fitted_observation_count=len(top),
            coarse_side_registration=CoarseSideRegistrationReceipt(len(top), len(top), len(top), 512)))
        self.assertIsNone(result.best)
        self.assertEqual(result.support_pair_bindings, ())

    def test_complete_support_pool_is_order_invariant_and_bound_discards_partial_results(self):
        from dataclasses import replace
        from x5crop.detection.photo_geometry.template_cross import fit_template_cross
        from x5crop.detection.photo_geometry.template_cross_model import CrossFitStatus
        _, inputs, result, *_ = native_coarse_fixture()
        permuted = fit_template_cross(replace(inputs, top_bindings=tuple(reversed(inputs.top_bindings)),
            bottom_bindings=tuple(reversed(inputs.bottom_bindings))))
        self.assertEqual(permuted, result)
        for bound in (1, 2):
            limited = fit_template_cross(replace(inputs, maximum_evaluated_fits=bound))
            self.assertEqual(limited.status, CrossFitStatus.BOUND_EXCEEDED)
            self.assertEqual(limited.support_pair_bindings, ())
            self.assertLessEqual(limited.receipt.evaluated_fit_count, bound)


if __name__ == "__main__":
    unittest.main()
