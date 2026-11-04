"""Dense bridges preserve registered gray semantics and make no crop claim."""

from dataclasses import FrozenInstanceError, fields, replace
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.domain import FiniteInterval, WorkspaceExtent
from x5crop.detection.photo_geometry import native_trace_bridge_measurement as owner
from x5crop.detection.photo_geometry.measurement_model import PhotoBoundaryMeasurementField
from x5crop.detection.photo_geometry.model import BoundaryAxis, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.registered_measurement import _slice_trace_measurement
from x5crop.detection.photo_geometry.registered_transition_measurement import measure_trace, measured_transition_peaks


def _field(gray):
    rgb = np.repeat(gray[:, :, None].astype(np.uint16) * 257, 3, axis=2)
    return PhotoBoundaryMeasurementField(gray, "horizontal", source_rgb=rgb)


def _steps(rows=31, columns=97):
    gray = np.full((rows, columns), 30, dtype=np.uint8)
    gray[:, 24:45] = 230
    gray[:, 65:] = 180
    gray[7:13, 51:55] = 250
    return gray


def _plan(field, **changes):
    values = dict(source_id=field.source_id, source_extent=field.source_extent,
        boundary_axis=BoundaryAxis.X, original_query_id="top:original", baseline_query_id="cross:baseline",
        normalization_interval_px=FiniteInterval(0., float(field.source_extent.width - 1)),
        coordinate_interval_px=FiniteInterval(15.2, 78.8), trace_intervals_px=((2, 10), (15, 18)),
        coordinate_scale_px_per_mm=10., original_trace_coordinates_px=(2, 5, 17, 25))
    values.update(changes)
    return owner.NativeTraceBridgePlan(**values)


def _measure(field, plans, **changes):
    return owner.measure_native_trace_bridges(field, plans,
        **({"maximum_pixel_queries": 1_000_000_000, "maximum_temporary_bytes": 128 * 1024 * 1024} | changes))


class NativeTraceBridgeMeasurementContractTest(unittest.TestCase):
    def assert_scalar_rows(self, field, batch):
        self.assertFalse(batch.bound_exceeded)
        for strip in batch.strips:
            plan = batch.plans[strip.plan_index]
            positive = owner.decode_mask(strip, 1)
            negative = owner.decode_mask(strip, -1)
            for index, trace in enumerate(range(strip.trace_start_px, strip.trace_stop_px)):
                values = (field.source_gray[trace] if plan.boundary_axis == BoundaryAxis.X
                          else field.source_gray[:, trace])
                scalar = measure_trace(values, plan.normalization_interval_px, plan.coordinate_scale_px_per_mm, SPEC,
                    peak_source_context=(field.source_id, field.source_extent, plan.boundary_axis, trace))
                view = _slice_trace_measurement(scalar, plan.coordinate_interval_px)
                strong = ((view.gradient_z >= SPEC.gradient_z_minimum)
                    & (np.maximum(view.tone_z, view.texture_z) >= SPEC.tone_or_texture_z_minimum))
                np.testing.assert_array_equal(positive[index], strong & (view.signed_gradient > 0))
                np.testing.assert_array_equal(negative[index], strong & (view.signed_gradient < 0))
                expected = tuple(owner.NativeTraceBridgePeak(int(view.coordinates[p.coordinate_index]),
                    p.canonical_coordinate, p.physical_position_interval, p.polarity,
                    p.gradient_z, p.tone_z, p.texture_z) for p in measured_transition_peaks(
                        view, SPEC, split_gradient_reversals=True))
                self.assertEqual(owner.peaks_at_row(strip, index), expected)
                for source in strip.original_trace_sources:
                    if source.trace_coordinate_px == trace:
                        self.assertEqual(source, scalar.peak_source)

    def test_both_polarities_all_peaks_and_original_source_hashes_match_scalar_owner(self):
        field = _field(_steps())
        before = field.source_gray.copy()
        plan = _plan(field)
        batch = _measure(field, (plan,))
        self.assert_scalar_rows(field, batch)
        self.assertTrue(any(np.any(owner.decode_mask(strip, 1)) for strip in batch.strips))
        self.assertTrue(any(np.any(owner.decode_mask(strip, -1)) for strip in batch.strips))
        self.assertEqual({s.trace_coordinate_px for strip in batch.strips for s in strip.original_trace_sources}, {2, 5, 17})
        self.assertGreaterEqual(max(b-a for strip in batch.strips
                                    for a, b in zip(strip.peak_row_offsets, strip.peak_row_offsets[1:])), 3)
        np.testing.assert_array_equal(field.source_gray, before)
        self.assertFalse(field.source_gray.flags.writeable)
        self.assertLessEqual(batch.retained_bytes, batch.peak_temporary_bytes)
        self.assertEqual(batch.preflight_value_visit_bound, owner.native_trace_bridge_preflight_value_visit_bound((plan,)))
        self.assertFalse(any("authority" in f.name for f in fields(batch)))
        with self.assertRaises(FrozenInstanceError):
            plan.source_id = "other"

    def test_overlapping_corridors_share_each_full_normalization_row_once(self):
        field = _field(_steps())
        first = _plan(field, trace_intervals_px=((2, 10),))
        second = _plan(field, original_query_id="bottom:original", coordinate_interval_px=FiniteInterval(40., 72.),
            trace_intervals_px=((5, 13),), original_trace_coordinates_px=(5, 8, 20))
        with patch.object(owner, "measure_trace_rows", wraps=owner.measure_trace_rows) as measured:
            batch = _measure(field, (first, second))
        self.assertEqual(sum(call.args[0].shape[0] for call in measured.call_args_list), 11)
        self.assertTrue(all(call.args[0].shape[1] == field.source_extent.width for call in measured.call_args_list))
        self.assert_scalar_rows(field, batch)
        halo = SPEC.measurement_halo_px(first.coordinate_scale_px_per_mm)
        coordinates = field.source_extent.width - 2 * halo
        radius = SPEC.local_measurement_work_radius_px(first.coordinate_scale_px_per_mm)
        self.assertEqual(batch.pixel_query_count,
                         11 * (field.source_extent.width + coordinates * (2 * radius + 2)))

    def test_tiny_normalization_on_long_source_row_reserves_the_full_gray_read(self):
        field = _field(_steps(rows=3, columns=20_001))
        plan = _plan(field, normalization_interval_px=FiniteInterval.exact(10_000.),
            coordinate_interval_px=FiniteInterval.exact(10_000.), trace_intervals_px=((1, 2),),
            original_trace_coordinates_px=(1,))
        with patch.object(owner, "measure_trace_rows", side_effect=AssertionError("whole row read was not reserved")), \
                patch.object(owner.np, "empty", side_effect=AssertionError("no arrays before complete reservation")):
            rejected = _measure(field, (plan,), maximum_pixel_queries=field.source_extent.width - 1)
        self.assertTrue(rejected.bound_exceeded)
        self.assertEqual(rejected.strips, ())
        self.assertEqual(rejected.pixel_query_count, 0)
        self.assertGreater(rejected.required_pixel_query_count, field.source_extent.width)
        accepted = _measure(field, (plan,))
        self.assert_scalar_rows(field, accepted)
        radius = SPEC.local_measurement_work_radius_px(plan.coordinate_scale_px_per_mm)
        old_kernel_work = 2 * radius + 2
        self.assertEqual(accepted.pixel_query_count, field.source_extent.width + old_kernel_work)
        owner.validate_native_trace_bridge_batch(accepted)
        forged = replace(accepted, pixel_query_count=old_kernel_work, required_pixel_query_count=old_kernel_work)
        with self.assertRaises(ValueError):
            owner.validate_native_trace_bridge_batch(forged)

    def test_different_original_baselines_do_not_recompute_local_normalization(self):
        field = _field(_steps())
        full = _plan(field, trace_intervals_px=((2, 4),), coordinate_interval_px=FiniteInterval(20., 46.))
        other = replace(full, original_query_id="other:original", baseline_query_id="other:baseline",
                        normalization_interval_px=FiniteInterval(0., 51.))
        with patch.object(owner, "measure_trace_rows", wraps=owner.measure_trace_rows) as measured:
            batch = _measure(field, (full, other))
        self.assertEqual(sum(call.args[0].shape[0] for call in measured.call_args_list), 4)
        self.assert_scalar_rows(field, batch)
        self.assertEqual(batch.plans, (full, other))

    def test_nonsquare_axis_transpose_preserves_masks_peaks_and_source_semantics(self):
        gray = _steps()
        horizontal, vertical = _field(gray), _field(gray.T.copy())
        first = _plan(horizontal)
        second = _plan(vertical, boundary_axis=BoundaryAxis.Y,
                       normalization_interval_px=first.normalization_interval_px)
        a, b = _measure(horizontal, (first,)), _measure(vertical, (second,))
        self.assert_scalar_rows(vertical, b)
        self.assertEqual([(s.positive_mask_hex, s.negative_mask_hex, s.peak_records_hex, s.peak_row_offsets) for s in a.strips],
                         [(s.positive_mask_hex, s.negative_mask_hex, s.peak_records_hex, s.peak_row_offsets) for s in b.strips])
        self.assertEqual([s.signal_sha256 for strip in a.strips for s in strip.original_trace_sources],
                         [s.signal_sha256 for strip in b.strips for s in strip.original_trace_sources])

    def test_streaming_blocks_are_reserved_before_arrays_and_keep_complete_trace_coverage(self):
        field = _field(_steps())
        plan = _plan(field)
        limited = replace(SPEC, maximum_streaming_block_pixels=2 * field.source_extent.width)
        with patch.object(owner, "SPEC", limited), patch.object(owner, "measure_trace_rows", wraps=owner.measure_trace_rows) as measured:
            batch = _measure(field, (plan,))
        self.assertTrue(all(call.args[0].size <= limited.maximum_streaming_block_pixels for call in measured.call_args_list))
        self.assertEqual(sum(s.trace_stop_px-s.trace_start_px for s in batch.strips), 11)
        self.assert_scalar_rows(field, batch)
        self.assertTrue(all(s.trace_stop_px-s.trace_start_px <= 2 for s in batch.strips))

    def test_work_and_memory_exhaustion_return_no_arrays_or_completed_prefix(self):
        field = _field(_steps())
        plans = (_plan(field), replace(_plan(field), original_query_id="second"))
        for changes in ({"maximum_pixel_queries": 0}, {"maximum_temporary_bytes": 0}):
            with self.subTest(changes=changes), patch.object(owner, "measure_trace_rows", side_effect=AssertionError("no source read")), \
                    patch.object(owner.np, "empty", side_effect=AssertionError("no arrays")), \
                    patch.object(owner.np, "arange", side_effect=AssertionError("no arrays")):
                batch = _measure(field, plans, **changes)
            self.assertTrue(batch.bound_exceeded)
            self.assertEqual(batch.plans, plans)
            self.assertEqual(batch.strips, ())
            self.assertEqual((batch.pixel_query_count, batch.value_visit_bound, batch.mask_site_work_bound,
                              batch.retained_bytes, batch.peak_temporary_bytes), (0, 0, 0, 0, 0))
            self.assertGreater(batch.required_pixel_query_count, 0)
            self.assertGreater(batch.required_value_visit_bound, 0)
            self.assertGreater(batch.required_peak_temporary_bytes, 0)
            self.assertGreater(batch.preflight_value_visit_bound, 0)

    def test_visit_budget_is_combined_with_pixels_and_not_just_pixel_work(self):
        field = _field(_steps())
        plans = (_plan(field),)
        accepted = _measure(field, plans)
        with patch.object(owner, "measure_trace_rows", side_effect=AssertionError("must reserve all visits")):
            rejected = _measure(field, plans, maximum_pixel_queries=accepted.pixel_query_count)
        self.assertTrue(rejected.bound_exceeded)
        self.assertEqual(accepted.value_visit_bound, rejected.required_value_visit_bound)
        self.assertGreater(accepted.value_visit_bound, accepted.mask_site_work_bound)
        complete_work = accepted.pixel_query_count + accepted.value_visit_bound + accepted.preflight_value_visit_bound
        with patch.object(owner, "measure_trace_rows", side_effect=AssertionError("must include preflight work")):
            self.assertTrue(_measure(field, plans, maximum_pixel_queries=complete_work - 1).bound_exceeded)
        self.assertFalse(_measure(field, plans, maximum_pixel_queries=complete_work,
                                  maximum_temporary_bytes=accepted.peak_temporary_bytes).bound_exceeded)

    def test_nonqueried_original_trace_does_not_create_an_unused_hash_via_another_plan(self):
        field = _field(_steps())
        first = _plan(field, trace_intervals_px=((2, 4),), original_trace_coordinates_px=(2, 12))
        second = _plan(field, original_query_id="second", trace_intervals_px=((11, 14),), original_trace_coordinates_px=())
        with patch.object(owner, "_source", wraps=owner._source) as sources:
            batch = _measure(field, (first, second))
        self.assertEqual(sources.call_count, 1)
        self.assertEqual([s.trace_coordinate_px for strip in batch.strips for s in strip.original_trace_sources], [2])

    def test_mask_shape_hex_padding_and_polarity_are_strict(self):
        strip = owner.NativeTraceBridgeStrip(0, 1, 2, 5, 10, "11", "02", "", (0, 0), ())
        np.testing.assert_array_equal(owner.decode_mask(strip, 1), [[1, 0, 0, 0, 1]])
        np.testing.assert_array_equal(owner.decode_mask(strip, -1), [[0, 1, 0, 0, 0]])
        for encoded in ("20", "0g", "0A", " 1", "0011", ""):
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                replace(strip, positive_mask_hex=encoded)
        with self.assertRaises(ValueError):
            replace(strip, negative_mask_hex="01")
        with self.assertRaises(ValueError):
            replace(strip, peak_row_offsets=())
        for polarity in (0, 2, True):
            with self.subTest(polarity=polarity), self.assertRaises(ValueError):
                owner.decode_mask(strip, polarity)

    def test_packed_peak_rows_reject_forged_records_offsets_and_reserved_bytes(self):
        record = owner._PEAK_RECORD.pack(7, 7., 6.5, 7.5, 4., 3., 0., 1).hex()
        strip = owner.NativeTraceBridgeStrip(0, 1, 2, 5, 10, "01", "02", record, (0, 1), ())
        self.assertEqual(owner.peaks_at_row(strip, 0),
            (owner.NativeTraceBridgePeak(7, 7., FiniteInterval(6.5, 7.5), 1, 4., 3., 0.),))
        self.assertEqual(owner._PEAK_RECORD.size, 64)
        for changes in ({"peak_records_hex": record[:-2] + "01"},
                        {"peak_records_hex": record[:-2] + "zz"},
                        {"peak_row_offsets": (0, 2)},
                        {"peak_row_offsets": (0, 1, 1)},
                        {"peak_records_hex": record + record, "peak_row_offsets": (0, 2)},
                        {"peak_records_hex": owner._PEAK_RECORD.pack(7, float("nan"), 6.5, 7.5, 4., 3., 0., 1).hex()},
                        {"peak_records_hex": owner._PEAK_RECORD.pack(7, 7., 6.5, 7.5, 4., 3., 0., 2).hex()}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(strip, **changes)
        for row in (True, -1, 1):
            with self.subTest(row=row), self.assertRaises(ValueError):
                owner.peaks_at_row(strip, row)

    def test_large_tail_preflight_fits_packed_storage_without_reading_a_large_source(self):
        plan = owner.NativeTraceBridgePlan("metadata-only", WorkspaceExtent(28772, 3996), BoundaryAxis.Y,
            "original", "baseline", FiniteInterval(0., 3995.), FiniteInterval(100., 619.),
            ((0, 5405),), 128., (0, 1000, 5404))
        with patch.object(owner, "measure_trace_rows", side_effect=AssertionError("metadata only")), \
                patch.object(owner.np, "empty", side_effect=AssertionError("no arrays")):
            groups, _, _, _, peak, _, fits = owner._prepare((plan,), 1_000_000_000)
        self.assertTrue(fits)
        self.assertLess(peak, 1_000_000_000)
        self.assertEqual(groups[0].batch_rows, SPEC.maximum_streaming_block_pixels // 3996)

    def test_batch_cannot_omit_duplicate_or_relabel_an_original_trace_source(self):
        field = _field(_steps())
        batch = _measure(field, (_plan(field),))
        with self.assertRaises(ValueError):
            replace(batch, strips=())
        with self.assertRaises(ValueError):
            replace(batch, strips=batch.strips + batch.strips[:1])
        first = batch.strips[0]
        bad_source = replace(first.original_trace_sources[0], source_id="another-original-field")
        bad_strip = replace(first, original_trace_sources=(bad_source, *first.original_trace_sources[1:]))
        with self.assertRaises(ValueError):
            replace(batch, strips=(bad_strip, *batch.strips[1:]))

    def test_invalid_source_domains_intervals_and_types_fail_before_pixel_reads(self):
        field = _field(_steps())
        plan = _plan(field)
        for changes in ({"trace_intervals_px": ((2, 9), (8, 12))},
                        {"trace_intervals_px": ((3, 3),)},
                        {"trace_intervals_px": ((2, 32),)},
                        {"coordinate_interval_px": FiniteInterval(0., 10.)},
                        {"normalization_interval_px": FiniteInterval(40., 60.)},
                        {"coordinate_scale_px_per_mm": True},
                        {"original_trace_coordinates_px": (2, 2)},
                        {"original_trace_coordinates_px": [2, 5]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(plan, **changes)
        with patch.object(owner, "measure_trace_rows", side_effect=AssertionError("no source read")):
            with self.assertRaises(ValueError):
                _measure(field, (replace(plan, source_id="other"),))
            for changes in ({"maximum_pixel_queries": True}, {"maximum_temporary_bytes": -1}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    _measure(field, (plan,), **changes)

    def test_empty_batch_is_completed_without_pixel_work(self):
        field = _field(_steps())
        with patch.object(owner, "measure_trace_rows", side_effect=AssertionError("no source read")):
            batch = _measure(field, (), maximum_pixel_queries=owner.native_trace_bridge_preflight_value_visit_bound(()),
                             maximum_temporary_bytes=0)
            self.assertTrue(_measure(field, (), maximum_pixel_queries=0, maximum_temporary_bytes=0).bound_exceeded)
        self.assertFalse(batch.bound_exceeded)
        self.assertEqual(batch.strips, ())
        self.assertEqual(batch.pixel_query_count + batch.value_visit_bound, 0)

    def test_metadata_validator_accepts_success_failure_and_empty_without_array_or_field_reads(self):
        field = _field(_steps())
        first = _plan(field)
        second = _plan(field, original_query_id="other", baseline_query_id="other:baseline",
            normalization_interval_px=FiniteInterval(0., 51.), coordinate_interval_px=FiniteInterval(20., 46.),
            trace_intervals_px=((5, 13),))
        third = _plan(field, original_query_id="short:original", boundary_axis=BoundaryAxis.Y,
            normalization_interval_px=FiniteInterval(0., 30.), coordinate_interval_px=FiniteInterval(5., 25.),
            trace_intervals_px=((4, 17),), original_trace_coordinates_px=(4, 6, 16))
        batches = (_measure(field, (first, second, third)),
            _measure(field, (first,), maximum_pixel_queries=0),
            _measure(field, (first,), maximum_temporary_bytes=0),
            _measure(field, ()), _measure(field, (), maximum_pixel_queries=0))
        with patch.object(owner, "measure_trace_rows", side_effect=AssertionError("metadata must not remeasure")), \
                patch.object(owner, "_source", side_effect=AssertionError("metadata must not hash pixels")), \
                patch.object(owner, "decode_mask", side_effect=AssertionError("metadata must not decode arrays")), \
                patch.object(owner, "peaks_at_row", side_effect=AssertionError("metadata must not decode peaks")), \
                patch.object(owner.np, "empty", side_effect=AssertionError("metadata must not allocate arrays")), \
                patch.object(owner.np, "arange", side_effect=AssertionError("metadata must not allocate arrays")):
            for batch in batches:
                owner.validate_native_trace_bridge_batch(batch)

    def test_metadata_validator_rejects_coordinated_counter_and_storage_forgery(self):
        field = _field(_steps())
        batch = _measure(field, (_plan(field),))
        for changes in (
            {"pixel_query_count": batch.pixel_query_count + 1,
             "required_pixel_query_count": batch.required_pixel_query_count + 1},
            {"value_visit_bound": batch.value_visit_bound + 1,
             "required_value_visit_bound": batch.required_value_visit_bound + 1},
            {"mask_site_work_bound": batch.mask_site_work_bound + 1},
            {"preflight_value_visit_bound": batch.preflight_value_visit_bound + 1},
            {"retained_bytes": batch.retained_bytes + 1},
            {"peak_temporary_bytes": batch.peak_temporary_bytes + 1,
             "required_peak_temporary_bytes": batch.required_peak_temporary_bytes + 1,
             "retained_bytes": batch.retained_bytes + 1},
        ):
            with self.subTest(changes=changes):
                forged = replace(batch, **changes)  # Construction alone permits these consistent claims.
                with self.assertRaises(ValueError):
                    owner.validate_native_trace_bridge_batch(forged)

    def test_metadata_validator_rejects_oversized_block_even_with_consistent_memory_numbers(self):
        field = _field(_steps())
        batch = _measure(field, (_plan(field),))
        _, _, _, _, minimum_peak, _, _ = owner._prepare(batch.plans, 0)
        groups, _, _, _, replay_peak, _, fits = owner._prepare(batch.plans, minimum_peak)
        self.assertTrue(fits)
        self.assertEqual(replay_peak, minimum_peak)
        self.assertEqual(groups[0].batch_rows, 1)
        self.assertTrue(any(strip.trace_stop_px-strip.trace_start_px > 1 for strip in batch.strips))
        forged = replace(batch, peak_temporary_bytes=minimum_peak, required_peak_temporary_bytes=minimum_peak)
        with self.assertRaisesRegex(ValueError, "streaming row block"):
            owner.validate_native_trace_bridge_batch(forged)

    def test_metadata_validator_checks_failed_requirements_without_treating_memory_as_success(self):
        field = _field(_steps())
        failed = _measure(field, (_plan(field),), maximum_temporary_bytes=0)
        owner.validate_native_trace_bridge_batch(replace(failed, required_peak_temporary_bytes=1))
        for name in ("required_pixel_query_count", "required_value_visit_bound", "preflight_value_visit_bound"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                owner.validate_native_trace_bridge_batch(replace(failed, **{name: getattr(failed, name) + 1}))
        empty = _measure(field, ())
        invented = replace(empty, retained_bytes=1, peak_temporary_bytes=1, required_peak_temporary_bytes=1)
        with self.assertRaises(ValueError):
            owner.validate_native_trace_bridge_batch(invented)


if __name__ == "__main__":
    unittest.main()
