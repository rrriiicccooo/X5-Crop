from unittest import TestCase
from unittest.mock import patch
import numpy as np

from x5crop.domain import FiniteInterval
from x5crop.detection.photo_geometry import registered_transition_measurement as owner
from x5crop.detection.photo_geometry.model import PHOTO_BOUNDARY_MEASUREMENT_SPEC as SPEC


def original_noise(values, group, _statistics=None):
    outside = np.ones(values.size, dtype=bool)
    outside[group] = False
    return float(np.median(values[outside]) if np.any(outside) else np.min(values[group]))


class TransitionNoiseExactnessTest(TestCase):
    def test_full_peak_records_equal_original_median_path(self):
        rng = np.random.default_rng(81025)
        count = 0
        for index in range(32):
            values = rng.integers(0, 256, 2048, dtype=np.uint8)
            if index % 2:
                values = np.repeat(rng.integers(0, 256, 64, dtype=np.uint8), 32)
            measured = owner.measure_trace(values, FiniteInterval(0, 2047), 20.0, SPEC, include_broad_material=True)
            for split in (False, True):
                actual = owner.measured_transition_peaks(measured, SPEC, split_gradient_reversals=split)
                with patch.object(owner, '_group_local_noise', side_effect=original_noise):
                    expected = owner.measured_transition_peaks(measured, SPEC, split_gradient_reversals=split)
                self.assertEqual(actual, expected)
                count += len(actual)
            actual = owner.measured_broad_material_peaks(measured, SPEC)
            with patch.object(owner, '_group_local_noise', side_effect=original_noise):
                expected = owner.measured_broad_material_peaks(measured, SPEC)
            self.assertEqual(actual, expected)
            count += len(actual)
        self.assertGreater(count, 100)

    def test_finite_arrays_parity_zero_removal_and_empty_outside_are_exact(self):
        rng = np.random.default_rng(23902)
        for size in range(1, 81):
            for _ in range(20):
                values = rng.integers(-5, 6, size).astype(float)
                values[rng.random(size) < 0.7] = 0
                group = np.sort(rng.choice(size, size=rng.integers(1, size+1), replace=False))
                self.assertEqual(owner._group_local_noise(values, group, owner._zero_median_statistics(values)),
                                 original_noise(values, group))
        values = np.array([0., 0., 3., 5., 9.])
        group = np.array([4])
        self.assertEqual(owner._group_local_noise(values, group, owner._zero_median_statistics(values)), 1.5)

    def test_nonfinite_arrays_preserve_original_path(self):
        for special in (np.nan, np.inf, -np.inf):
            values = np.array([0., 0., 0., special, 7.])
            group = np.array([4])
            with patch.object(owner.np, 'median', wraps=np.median) as median:
                actual = owner._group_local_noise(values, group, owner._zero_median_statistics(values))
                self.assertEqual(median.call_count, 1)
            np.testing.assert_equal(actual, original_noise(values, group))
