"""Integer histograms preserve full-domain robust scores and source meaning."""
import math
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.detection.robust_statistics import (
    positive_mad_z, positive_mad_z_rows, positive_mad_z_uint8_rows,
    UINT8_MAD_HISTOGRAM_MINIMUM_COLUMNS,
)
from x5crop.detection.photo_geometry import registered_transition_measurement as owner
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC
from x5crop.domain import FiniteInterval


class Uint8RobustStatisticsContractTest(unittest.TestCase):
    def test_integer_inventory_matches_both_original_statistics_owners_exactly(self):
        rng = np.random.default_rng(71953)
        for columns in (0, 1, 2, 2047, 2048, 2049, 8193):
            values = rng.integers(0, 256, size=(6, columns), dtype=np.uint8)
            values[0] = 0
            values[1] = 255
            values[2] = np.arange(columns) % 256
            values[3] = (np.arange(columns) % 2)*255
            for data in (values, np.asfortranarray(values), values[::-1, ::-1]):
                before = data.copy()
                data.flags.writeable = False
                for minimum in (0., .25, 1., 9.25):
                    with self.subTest(columns=columns, minimum=minimum):
                        actual = positive_mad_z_uint8_rows(data, minimum_scale=minimum)
                        self.assertTrue(actual.flags.c_contiguous)
                        np.testing.assert_array_equal(actual, positive_mad_z_rows(data, minimum_scale=minimum))
                        expected = np.vstack([positive_mad_z(row, minimum_scale=minimum) for row in data])
                        np.testing.assert_array_equal(actual, expected)
                        np.testing.assert_array_equal(data, before)
                        self.assertFalse(np.shares_memory(actual, data))

    def test_native_luma_never_enters_integer_normalization(self):
        values = np.tile(np.arange(4096, dtype=np.float64) % 256, (2, 1))*257+.125
        with patch.object(owner, 'positive_mad_z_uint8_rows',
                          side_effect=AssertionError('native luma retains its original floating statistics')):
            measured = owner.measure_trace_rows(values, FiniteInterval(0., 4095.), 10., SPEC,
                                                intensity_quantum=1.)
        self.assertTrue(np.all(np.isfinite(measured.gradient_z)))
        for bad in (values, values.astype(np.uint16), values[0]):
            with self.assertRaises(ValueError):
                positive_mad_z_uint8_rows(bad)
        for minimum in (-1., math.inf, math.nan):
            with self.assertRaises(ValueError):
                positive_mad_z_uint8_rows(values.astype(np.uint8), minimum_scale=minimum)

    def test_histogram_constant_and_row_scratch_fit_the_existing_four_workspaces(self):
        # Input cast + result, one row's bincount conversion, <=16 KiB of
        # 256/511-bin integer arrays and <=128 bytes of reductions per row.
        for rows in (1, 2, 17, 64):
            for columns in (UINT8_MAD_HISTOGRAM_MINIMUM_COLUMNS, 8193, 20084):
                histogram = (9*rows+8)*columns+16384+128*rows
                self.assertLessEqual(histogram, 4*8*rows*columns)
