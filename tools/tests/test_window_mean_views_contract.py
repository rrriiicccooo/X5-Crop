"""Window views preserve the original complete gathers, bounds and ordering."""
import unittest
import numpy as np

from x5crop.detection.photo_geometry.registered_transition_measurement import _window_means, _window_prefix


def _gather(values, coordinates, window, gap):
    prefix = _window_prefix(values)
    left_stop = coordinates-gap
    left_start = left_stop-window
    right_start = coordinates+gap
    right_stop = right_start+window
    return ((prefix[..., left_stop]-prefix[..., left_start])/float(window),
            (prefix[..., right_stop]-prefix[..., right_start])/float(window))


class WindowMeanViewsContractTest(unittest.TestCase):
    def test_full_integer_ranges_preserve_values_and_make_row_contiguous_results(self):
        rng = np.random.default_rng(52013)
        original = rng.normal(size=(5, 401))
        for values in (original, np.asfortranarray(original), original[::-1, ::-1], original[0]):
            before = values.copy()
            values.flags.writeable = False
            coordinates = np.arange(20, 380, dtype=np.int32)
            expected = _gather(values, coordinates, 9, 3)
            actual = _window_means(values, coordinates, 9, 3)
            for result, reference in zip(actual, expected):
                np.testing.assert_array_equal(result, reference)
                self.assertTrue(result.flags.c_contiguous)
            np.testing.assert_array_equal(values, before)

    def test_permutations_clipping_duplicates_and_integer_wrap_keep_original_gathers(self):
        values = np.arange(513, dtype=float)**.5
        for coordinates in (np.array([20, 22, 21, 23]), np.array([20, 20, 21, 22]),
                            np.array([0, 1, 2]), np.array([], dtype=int),
                            np.arange(250, 255, dtype=np.uint8)):
            with self.subTest(coordinates=coordinates):
                for actual, expected in zip(_window_means(values, coordinates, 2, 1),
                                            _gather(values, coordinates, 2, 1)):
                    np.testing.assert_array_equal(actual, expected)
