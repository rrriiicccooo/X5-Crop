"""Call-local prefix reuse preserves the original scalar and native formulas."""

from dataclasses import fields, is_dataclass
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.domain import FiniteInterval, WorkspaceExtent
from x5crop.image.gray import BaseGrayParameters, _luma_u16
from x5crop.detection.photo_geometry import registered_transition_measurement as owner
from x5crop.detection.photo_geometry.model import BoundaryAxis, PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.detection.photo_geometry.transition_peak_capture import TransitionPeakCapture


def _original_window_means(values, coordinates, window, gap, *, preparation=None):
    """The previous formula, deliberately rebuilding its prefix on each call."""
    left_stop = coordinates - gap
    left_start = left_stop - window
    right_start = coordinates + gap
    right_stop = right_start + window
    if values.ndim == 1:
        prefix = np.empty(values.size + 1, dtype=np.float64)
        prefix[0] = 0.0
        np.cumsum(values, dtype=np.float64, out=prefix[1:])
        return ((prefix[left_stop] - prefix[left_start]) / float(window),
                (prefix[right_stop] - prefix[right_start]) / float(window))
    if values.ndim == 2:
        prefix = np.empty((values.shape[0], values.shape[1] + 1), dtype=np.float64)
        prefix[:, 0] = 0.0
        np.cumsum(values, axis=1, dtype=np.float64, out=prefix[:, 1:])
        return ((prefix[:, left_stop] - prefix[:, left_start]) / float(window),
                (prefix[:, right_stop] - prefix[:, right_start]) / float(window))
    raise ValueError("window means require a one- or two-dimensional array")


class RegisteredPrefixReuseContractTest(unittest.TestCase):
    def assert_exact(self, actual, expected):
        if isinstance(expected, np.ndarray):
            self.assertEqual(actual.shape, expected.shape)
            self.assertEqual(actual.dtype, expected.dtype)
            self.assertEqual(actual.tobytes(order="C"), expected.tobytes(order="C"))
        elif is_dataclass(expected):
            self.assertIs(type(actual), type(expected))
            for field in fields(expected):
                if field.name != "temporary_bytes":
                    with self.subTest(field=field.name):
                        self.assert_exact(getattr(actual, field.name), getattr(expected, field.name))
        elif isinstance(expected, tuple):
            self.assertEqual(len(actual), len(expected))
            for left, right in zip(actual, expected, strict=True):
                self.assert_exact(left, right)
        else:
            self.assertEqual(actual, expected)

    def scalar_pair(self, values, interval, scale, *, axis=BoundaryAxis.X, broad=True, capacity=None):
        before = values.tobytes()
        extent = WorkspaceExtent(values.size, 7) if axis == BoundaryAxis.X else WorkspaceExtent(7, values.size)
        kwargs = dict(include_broad_material=broad,
                      peak_source_context=("fixed-original-source", extent, axis, 3),
                      prefix_cache_capacity_bytes=capacity)
        with patch.object(owner, "_window_means", side_effect=_original_window_means):
            expected = owner.measure_trace(values, interval, scale, SPEC, **kwargs)
        actual = owner.measure_trace(values, interval, scale, SPEC, **kwargs)
        self.assert_exact(actual, expected)
        self.assertEqual(values.tobytes(), before)
        self.assertEqual(owner.trace_storage_bytes(actual), owner.trace_storage_bytes(expected))
        for split in (False, True):
            a_capture, e_capture = TransitionPeakCapture(32 * 1024 * 1024), TransitionPeakCapture(32 * 1024 * 1024)
            self.assert_exact(owner.measured_transition_peaks(actual, SPEC, split_gradient_reversals=split,
                peak_source_capture=a_capture), owner.measured_transition_peaks(expected, SPEC,
                    split_gradient_reversals=split, peak_source_capture=e_capture))
        if broad:
            self.assert_exact(owner.measured_broad_material_peaks(actual, SPEC),
                              owner.measured_broad_material_peaks(expected, SPEC))
        return actual, expected

    def test_scalar_broad_six_prefix_constructions_become_two_and_nonbroad_stays_two(self):
        values = np.full(257, 20, dtype=np.uint8)
        values[60:150] = 220
        with patch.object(owner, "_window_means", side_effect=_original_window_means), \
                patch.object(owner.np, "cumsum", wraps=np.cumsum) as original:
            owner.measure_trace(values, FiniteInterval(0., 256.), 20., SPEC, include_broad_material=True)
        self.assertEqual(original.call_count, 6)
        for broad in (False, True):
            with self.subTest(broad=broad), patch.object(owner.np, "cumsum", wraps=np.cumsum) as measured:
                owner.measure_trace(values, FiniteInterval(0., 256.), 20., SPEC, include_broad_material=broad)
            self.assertEqual(measured.call_count, 2)

    def test_full_gray_steps_alternating_noise_transposes_and_narrow_domains_are_bit_exact(self):
        rng = np.random.default_rng(20261105)
        gray = rng.integers(0, 256, (5, 257), dtype=np.uint8)
        gray[0] = 20
        gray[1, 60:150] = 240
        gray[2] = np.where(np.arange(257) % 2, 127, 128)
        transposed = gray.T.copy()
        for axis in (BoundaryAxis.X, BoundaryAxis.Y):
            for index in range(gray.shape[0]):
                values = gray[index] if axis == BoundaryAxis.X else transposed[:, index]
                values.flags.writeable = False
                for interval in (FiniteInterval(0., 256.), FiniteInterval(60.2, 64.8), FiniteInterval.exact(128.)):
                    with self.subTest(axis=axis, row=index, interval=interval):
                        self.scalar_pair(values, interval, 20., axis=axis)

    def test_native_luma_two_scales_share_two_prefixes_without_changing_native_units(self):
        rng = np.random.default_rng(20261105)
        rgb = rng.integers(0, 65536, (5, 257, 3), dtype=np.uint16)
        luma = np.empty(rgb.shape[:2], dtype=np.float32)
        _luma_u16(rgb, luma, np.empty_like(luma), BaseGrayParameters())
        numeric = luma.astype(np.float64)
        transposed = numeric.T.copy()
        for values in (numeric[2], transposed[:, 2]):
            differences = np.abs(np.diff(values))
            halo = SPEC.measurement_halo_px(20.)
            for coordinates in (np.arange(halo, values.size-halo, dtype=np.int32),
                                np.arange(60, 64, dtype=np.int32)):
                with patch.object(owner, "_window_means", side_effect=_original_window_means), \
                        patch.object(owner.np, "cumsum", wraps=np.cumsum) as old_calls:
                    expected = owner.broad_material_trace_measurement(values, differences, coordinates, 20., SPEC,
                                                                      intensity_quantum=1.0)
                with patch.object(owner.np, "cumsum", wraps=np.cumsum) as new_calls:
                    actual = owner.broad_material_trace_measurement(values, differences, coordinates, 20., SPEC,
                                                                    intensity_quantum=1.0)
                self.assertEqual(old_calls.call_count, 4)
                self.assertEqual(new_calls.call_count, 2)
                self.assert_exact(actual, expected)
                self.assertEqual(actual.temporary_bytes-expected.temporary_bytes, 16 * values.size + 8)

    def test_scalar_temporary_reservation_includes_prefixes_but_returned_storage_does_not(self):
        values = np.full(257, 20, dtype=np.uint8)
        values[70:150] = 230
        actual, expected = self.scalar_pair(values, FiniteInterval(0., 256.), 20.)
        extra = 16 * values.size + 8
        self.assertEqual(actual.temporary_bytes - expected.temporary_bytes, extra)
        self.assertEqual(actual.broad_material.temporary_bytes - expected.broad_material.temporary_bytes, extra)
        plain, old_plain = self.scalar_pair(values, FiniteInterval(0., 256.), 20., broad=False)
        self.assertEqual(plain.temporary_bytes, old_plain.temporary_bytes)

    def test_batch_float_native_and_uint8_formulas_and_temporary_bounds_do_not_change(self):
        rng = np.random.default_rng(20261105)
        gray = rng.integers(0, 256, (5, 129), dtype=np.uint8)
        for values, quantum in ((gray, None), (gray.T, None),
                                (gray.astype(np.float32) * 257.0, 1.0)):
            for interval in (FiniteInterval(0., float(values.shape[1] - 1)), FiniteInterval.exact(6.)):
                with self.subTest(shape=values.shape, quantum=quantum, interval=interval):
                    with patch.object(owner, "_window_means", side_effect=_original_window_means):
                        expected = owner.measure_trace_rows(values, interval, 4., SPEC, intensity_quantum=quantum)
                    with patch.object(owner.np, "cumsum", wraps=np.cumsum) as calls:
                        actual = owner.measure_trace_rows(values, interval, 4., SPEC, intensity_quantum=quantum)
                    self.assert_exact(actual, expected)
                    self.assertEqual(actual.temporary_bytes, expected.temporary_bytes)
                    self.assertEqual(calls.call_count, 2 if actual.coordinates.size else 0)

    def test_empty_or_unobservable_domains_do_not_eagerly_build_unused_prefixes(self):
        values = np.arange(32, dtype=np.uint8)
        with patch.object(owner.np, "cumsum", side_effect=AssertionError("empty domain has no prefix")):
            empty = owner.measure_trace(values, FiniteInterval(0., 0.), 20., SPEC, include_broad_material=True)
        self.assertEqual(empty.coordinates.size, 0)
        numeric = values.astype(np.float64)
        differences = np.abs(np.diff(numeric))
        with patch.object(owner.np, "cumsum", side_effect=AssertionError("unobservable broad domain has no prefix")):
            broad = owner.broad_material_trace_measurement(numeric, differences, np.array([0], dtype=np.int32),
                                                          20., SPEC, intensity_quantum=1.0)
        self.assertFalse(np.any(broad.observable))
        with patch.object(owner, "_window_means", side_effect=_original_window_means):
            expected = owner.broad_material_trace_measurement(numeric, differences, np.array([0], dtype=np.int32),
                                                             20., SPEC, intensity_quantum=1.0)
        self.assert_exact(broad, expected)
        self.assertEqual(broad.temporary_bytes, expected.temporary_bytes)

    def test_prefix_rejects_another_input_and_is_not_reused_across_calls(self):
        values = np.arange(129, dtype=np.uint8)
        prepared = owner._WindowPrefix(values)
        with self.assertRaises(ValueError):
            prepared.for_values(values.copy())
        with patch.object(owner.np, "cumsum", wraps=np.cumsum) as calls:
            for _ in range(2):
                owner.measure_trace(values, FiniteInterval(0., 128.), 20., SPEC, include_broad_material=True)
        self.assertEqual(calls.call_count, 4)

    def test_capacity_zero_or_one_byte_short_uses_original_scalar_work_without_cache_creation(self):
        values = np.full(257, 20, dtype=np.uint8)
        values[60:150] = 220
        capacity = owner.window_prefix_cache_bytes(values.size)
        for offered in (0, capacity - 1):
            with self.subTest(offered=offered), \
                    patch.object(owner, "_WindowPrefix", side_effect=AssertionError("cache capacity was not reserved")), \
                    patch.object(owner.np, "cumsum", wraps=np.cumsum) as calls:
                actual = owner.measure_trace(values, FiniteInterval(0., 256.), 20., SPEC,
                    include_broad_material=True, prefix_cache_capacity_bytes=offered)
            self.assertEqual(calls.call_count, 6)
            with patch.object(owner, "_window_means", side_effect=_original_window_means):
                expected = owner.measure_trace(values, FiniteInterval(0., 256.), 20., SPEC,
                    include_broad_material=True, prefix_cache_capacity_bytes=0)
            self.assert_exact(actual, expected)
            self.assertEqual(actual.temporary_bytes, expected.temporary_bytes)
            self.scalar_pair(values, FiniteInterval(0., 256.), 20., capacity=offered)
        for offered in (capacity, capacity + 100):
            with self.subTest(offered=offered), patch.object(owner.np, "cumsum", wraps=np.cumsum) as calls:
                actual = owner.measure_trace(values, FiniteInterval(0., 256.), 20., SPEC,
                    include_broad_material=True, prefix_cache_capacity_bytes=offered)
            self.assertEqual(calls.call_count, 2)
            self.assertEqual(actual.temporary_bytes-expected.temporary_bytes, capacity)
            self.scalar_pair(values, FiniteInterval(0., 256.), 20., capacity=offered)

    def test_capacity_fallback_keeps_native_luma_broad_formula_and_original_four_prefixes(self):
        values = np.linspace(0., 65535., 257, dtype=np.float64)
        values[60:150] += 0.125
        differences = np.abs(np.diff(values))
        coordinates = np.arange(6, 251, dtype=np.int32)
        required = owner.window_prefix_cache_bytes(values.size)
        with patch.object(owner, "_window_means", side_effect=_original_window_means):
            expected = owner.broad_material_trace_measurement(values, differences, coordinates, 20., SPEC,
                intensity_quantum=1.0, prefix_cache_capacity_bytes=0)
        for offered, count in ((0, 4), (required - 1, 4), (required, 2)):
            with self.subTest(offered=offered), patch.object(owner.np, "cumsum", wraps=np.cumsum) as calls:
                if offered < required:
                    with patch.object(owner, "_WindowPrefix", side_effect=AssertionError("no cached prefix may be allocated")):
                        actual = owner.broad_material_trace_measurement(values, differences, coordinates, 20., SPEC,
                            intensity_quantum=1.0, prefix_cache_capacity_bytes=offered)
                else:
                    actual = owner.broad_material_trace_measurement(values, differences, coordinates, 20., SPEC,
                        intensity_quantum=1.0, prefix_cache_capacity_bytes=offered)
            self.assertEqual(calls.call_count, count)
            self.assert_exact(actual, expected)
            self.assertEqual(actual.temporary_bytes-expected.temporary_bytes, required if count == 2 else 0)
            arrays = [array for f in fields(actual)
                      for array in (getattr(actual, f.name) if isinstance(getattr(actual, f.name), tuple)
                                    else (getattr(actual, f.name),)) if isinstance(array, np.ndarray)]
            # Counting even the returned aliases is conservative for this
            # standalone broad call; the metadata bound still covers both.
            reserve = owner.scalar_trace_buffer_reservation(values.size, coordinates.size,
                                                             prefix_cache_capacity_bytes=offered)
            self.assertGreaterEqual(reserve, sum(a.nbytes for a in arrays) + actual.temporary_bytes)

    def test_metadata_reservation_covers_returned_trace_storage_plus_construction_peak(self):
        for length in (16, 65, 257):
            values = np.arange(length, dtype=np.uint8)
            for interval in (FiniteInterval(0., float(length-1)), FiniteInterval.exact(length//2)):
                for broad in (False, True):
                    for capacity in (0, owner.window_prefix_cache_bytes(length)):
                        with self.subTest(length=length, interval=interval, broad=broad, capacity=capacity):
                            measured, _ = self.scalar_pair(values, interval, 4., broad=broad, capacity=capacity)
                            reserve = owner.scalar_trace_buffer_reservation(length, measured.coordinates.size,
                                include_broad_material=broad, prefix_cache_capacity_bytes=capacity)
                            self.assertGreaterEqual(reserve, owner.trace_storage_bytes(measured)+measured.temporary_bytes)
        with patch.object(owner.np, "empty", side_effect=AssertionError("metadata cannot allocate arrays")), \
                patch.object(owner.np, "cumsum", side_effect=AssertionError("metadata cannot read numeric values")):
            cached = owner.scalar_trace_buffer_reservation(10_000, 1)
            uncached = owner.scalar_trace_buffer_reservation(10_000, 1, prefix_cache_capacity_bytes=0)
            self.assertEqual(cached-uncached, owner.window_prefix_cache_bytes(10_000))
            self.assertEqual(owner.scalar_trace_buffer_reservation(10_000, 0), 0)

    def test_metadata_row_composition_preserves_existing_batch_numeric_reservation(self):
        values = np.tile(np.arange(129, dtype=np.uint8), (3, 1))
        measured = owner.measure_trace_rows(values, FiniteInterval(0., 128.), 20., SPEC)
        rows, length = values.shape
        q = measured.coordinates.size
        # The original composition: input + coordinates + differences + 11
        # float64 response matrices + two prefixes + arithmetic/MAD scratch.
        differences = 8 * rows * (length-1)
        expected = (8*rows*length + measured.coordinates.nbytes + differences + 11*8*rows*q
                    + 8*rows*((length+1)+length) + differences + 10*8*rows*q + 8*rows*8)
        self.assertEqual(measured.temporary_bytes, expected)

    def test_invalid_cache_capacities_are_rejected_without_constructing_prefixes(self):
        values = np.arange(129, dtype=np.uint8)
        for capacity in (True, -1, 0.5):
            with self.subTest(capacity=capacity), patch.object(owner, "_WindowPrefix", side_effect=AssertionError("no cache")):
                with self.assertRaises(ValueError):
                    owner.measure_trace(values, FiniteInterval(0., 128.), 20., SPEC,
                        include_broad_material=True, prefix_cache_capacity_bytes=capacity)
                with self.assertRaises(ValueError):
                    owner.scalar_trace_buffer_reservation(129, 100, prefix_cache_capacity_bytes=capacity)


if __name__ == "__main__":
    unittest.main()
