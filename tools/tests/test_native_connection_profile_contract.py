from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import numpy as np

from x5crop.detection.photo_geometry import registered_transition_measurement as owner
from x5crop.detection.photo_geometry.model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC,
)
from x5crop.detection.robust_statistics import (
    positive_mad_z,
    positive_mad_z_rows,
)
from x5crop.domain import FiniteInterval


FIELDS = (
    "gradient_z",
    "tone_z",
    "texture_z",
    "signed_gradient",
    "left_tone",
    "right_tone",
    "left_texture",
    "right_texture",
)


class NativeConnectionProfileContractTest(TestCase):
    def assert_exact_batch(
        self,
        values: np.ndarray,
        interval: FiniteInterval,
        scale_px_per_mm: float,
    ) -> owner.TraceRowsMeasurement:
        before = values.copy()
        values.flags.writeable = False
        with patch.object(
            owner,
            "measure_trace",
            side_effect=AssertionError("batch path must not call measure_trace per row"),
        ):
            measured = owner.measure_trace_rows(values, interval, scale_px_per_mm, SPEC)

        self.assertTrue(np.array_equal(values, before))
        self.assertEqual(measured.coordinates.dtype, np.int32)
        self.assertGreaterEqual(
            measured.temporary_bytes,
            measured.coordinates.nbytes
            + sum(getattr(measured, field).nbytes for field in FIELDS),
        )
        for row_index in range(values.shape[0]):
            expected = owner.measure_trace(
                values[row_index], interval, scale_px_per_mm, SPEC,
            )
            self.assertTrue(np.array_equal(measured.coordinates, expected.coordinates))
            for field in FIELDS:
                actual_values = getattr(measured, field)
                self.assertTrue(
                    np.array_equal(actual_values[row_index], getattr(expected, field)),
                    msg=f"{field} row {row_index} differs from measure_trace",
                )
        self.assertEqual(measured.coordinates.size, measured.gradient_z.shape[1])
        self.assertEqual(values.shape[0], measured.gradient_z.shape[0])
        return measured

    def test_flat_steps_alternating_and_seeded_random_match_exactly(self) -> None:
        rng = np.random.default_rng(20261022)
        values = np.full((8, 129), 128, dtype=np.uint8)
        values[1, 64:] = 255
        values[2, 64:] = 1
        values[3] = np.where(np.arange(129) % 2, 127, 128).astype(np.uint8)
        values[4] = rng.integers(0, 256, size=129, dtype=np.uint8)
        values[5] = rng.integers(0, 256, size=129, dtype=np.uint8)
        values[6, 6:] = 129
        values[7, :-6] = 127
        measured = self.assert_exact_batch(
            values,
            FiniteInterval(0.0, 128.0),
            20.0,
        )
        self.assertTrue(
            all(np.all(np.isfinite(getattr(measured, field))) for field in FIELDS)
        )

    def test_even_and_odd_trace_lengths_and_source_edge_kernel(self) -> None:
        window = SPEC.local_window_px(20.0)
        gap = SPEC.transition_gap_px(20.0)
        legal_length = 2 * (window + gap) + 1
        for trace_length in (legal_length, legal_length + 1, 64, 65):
            values = np.full((3, trace_length), 32, dtype=np.uint8)
            edge = min(window + gap, trace_length - 1)
            values[0, edge:] = 224
            values[1, :edge] = 224
            values[2, edge:] = 33
            with self.subTest(trace_length=trace_length):
                measured = self.assert_exact_batch(
                    values,
                    FiniteInterval(0.0, float(trace_length - 1)),
                    20.0,
                )
                self.assertTrue(np.all(measured.coordinates >= window + gap))

    def test_empty_coordinate_domain_keeps_batch_shape_and_zero_work(self) -> None:
        values = np.full((4, 12), 128, dtype=np.uint8)
        measured = self.assert_exact_batch(
            values,
            FiniteInterval(0.0, 11.0),
            20.0,
        )
        self.assertEqual(measured.coordinates.size, 0)
        self.assertEqual(measured.temporary_bytes, 0)
        self.assertEqual(measured.gradient_z.shape, (4, 0))

    def test_noncontiguous_transposed_readonly_input_is_exact_and_unchanged(self) -> None:
        rng = np.random.default_rng(9001)
        base = rng.integers(0, 256, size=(131, 5), dtype=np.uint8)
        values = base.T
        self.assertFalse(values.flags.c_contiguous)
        self.assert_exact_batch(values, FiniteInterval(2.25, 127.75), 13.37)

    def test_quantization_floor_is_applied_per_row(self) -> None:
        values = np.full((4, 97), 100, dtype=np.uint8)
        values[1, 48:] = 101
        values[2, 48:] = 99
        values[3] = np.where(np.arange(97) % 2, 100, 101).astype(np.uint8)
        measured = self.assert_exact_batch(
            values,
            FiniteInterval(0.0, 96.0),
            20.0,
        )
        self.assertTrue(
            all(np.all(np.isfinite(getattr(measured, field))) for field in FIELDS)
        )

    def test_zero_mad_rows_match_scalar_owner_without_fp_warnings(self) -> None:
        values = np.array(
            (
                (0.0,) * 9,
                (5.0,) * 9,
                (0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0),
                (-2.0, -1.0, 0.0, 1.0, 2.0, -2.0, -1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0),
            ),
            dtype=np.float64,
        )
        with np.errstate(all="raise"):
            actual = positive_mad_z_rows(values, minimum_scale=0.0)
            expected = np.vstack(
                tuple(positive_mad_z(row, minimum_scale=0.0) for row in values)
            )
        np.testing.assert_array_equal(actual, expected)

    def test_input_contract_rejects_non_uint8_or_non_matrix_values(self) -> None:
        with self.assertRaises(ValueError):
            owner.measure_trace_rows(
                np.zeros((2, 32), dtype=np.float64),
                FiniteInterval(0.0, 31.0),
                20.0,
                SPEC,
            )
        with self.assertRaises(ValueError):
            owner.measure_trace_rows(
                np.zeros(32, dtype=np.uint8),
                FiniteInterval(0.0, 31.0),
                20.0,
                SPEC,
            )

    def test_explicit_native_quantum_preserves_unclipped_uint16_and_luma_rows(self) -> None:
        rng = np.random.default_rng(7758)
        original = rng.integers(0, 65536, size=(4, 129), dtype=np.uint16)
        for values in (original, original.astype(np.float32) * np.float32(.7152)):
            values.flags.writeable = False
            interval = FiniteInterval(0., 128.)
            measured = owner.measure_trace_rows(values, interval, 20., SPEC, intensity_quantum=1.)
            for index, row in enumerate(values):
                expected = owner.measure_trace(row, interval, 20., SPEC)
                for field in FIELDS:
                    np.testing.assert_array_equal(getattr(measured, field)[index], getattr(expected, field))
        with self.assertRaises(ValueError):
            owner.measure_trace_rows(original, FiniteInterval(0., 128.), 20., SPEC, intensity_quantum=0.)
        with self.assertRaises(ValueError):
            owner.measure_trace_rows(original, FiniteInterval(0., 128.), 20., SPEC, intensity_quantum=True)


if __name__ == "__main__":
    import unittest

    unittest.main()
