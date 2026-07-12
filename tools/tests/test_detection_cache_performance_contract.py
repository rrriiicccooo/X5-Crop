from __future__ import annotations

from dataclasses import fields
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.cache import MeasurementCache
from x5crop.cache.separator import cached_separator_profile
from x5crop.domain import Box
from x5crop.geometry.detection_parameters import SeparatorProfileParameters
from x5crop.image.statistics import ImageMeasurementStatisticsParameters, image_measurement_statistics


def _cache() -> MeasurementCache:
    gray = np.zeros((80, 240), dtype=np.uint8)
    return MeasurementCache(
        "horizontal",
        gray,
        gray,
        gray.astype(np.float32),
        image_measurement_statistics(gray, ImageMeasurementStatisticsParameters()),
    )


class DetectionCachePerformanceContractTest(unittest.TestCase):
    def test_separator_profile_is_cached_by_exact_corridor_and_parameters(self) -> None:
        cache = _cache()
        corridor = Box(0, 10, 240, 70)
        parameters = SeparatorProfileParameters()
        measured = np.arange(240, dtype=np.float32)
        with patch(
            "x5crop.cache.separator.separator_profile",
            return_value=measured,
        ) as measurement:
            first = cached_separator_profile(cache, corridor, parameters)
            second = cached_separator_profile(cache, corridor, parameters)
        self.assertIs(first, second)
        measurement.assert_called_once()

    def test_different_corridors_do_not_share_profile_measurements(self) -> None:
        cache = _cache()
        parameters = SeparatorProfileParameters()
        with patch(
            "x5crop.cache.separator.separator_profile",
            side_effect=lambda crop, _statistics, _params: np.zeros(
                crop.shape[1],
                dtype=np.float32,
            ),
        ) as measurement:
            cached_separator_profile(cache, Box(0, 0, 240, 60), parameters)
            cached_separator_profile(cache, Box(0, 20, 240, 80), parameters)
        self.assertEqual(measurement.call_count, 2)

    def test_cache_contains_measurements_not_candidates_or_decisions(self) -> None:
        names = {field.name for field in fields(MeasurementCache)}
        for forbidden in (
            "candidates",
            "candidate_gate",
            "decision_gate",
            "final_detection",
            "final_review_reasons",
        ):
            self.assertNotIn(forbidden, names)

    def test_removed_width_and_refinement_profiles_are_not_cached(self) -> None:
        names = {field.name for field in fields(MeasurementCache)}
        self.assertNotIn("separator_width_profiles", names)
        self.assertNotIn("edge_refine_profiles", names)

    def test_profile_cache_key_is_count_and_offset_independent(self) -> None:
        cache = _cache()
        parameters = SeparatorProfileParameters()
        cached_separator_profile(cache, Box(0, 0, 240, 80), parameters)
        key = next(iter(cache.separator_profiles_full))
        self.assertEqual(key, (parameters,))


if __name__ == "__main__":
    unittest.main()
