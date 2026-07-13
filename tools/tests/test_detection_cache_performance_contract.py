from __future__ import annotations

from dataclasses import fields
from typing import get_type_hints
import unittest
from unittest.mock import patch
from dataclasses import replace

import numpy as np

from x5crop.cache import MeasurementCache, MeasurementRegionKey
from x5crop.cache.separator import cached_separator_profile
from x5crop.domain import Box
from x5crop.image.separator_profile import SeparatorProfileParameters
from x5crop.geometry.layout import work_gray
from x5crop.image.statistics import ImageMeasurementStatisticsParameters, image_measurement_statistics
from x5crop.configuration.bundle import DetectionConfigurationBundle
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.evidence.content.frame_support import frame_content_evidence
from tools.tests.physical_gate_support import candidate_fixture
from x5crop.runtime.analysis_reuse import analysis_configuration_fingerprint
from x5crop.configuration.boundary import BoundaryPathParameters
from x5crop.detection.candidate.proposal.sequence import (
    cached_boundary_path_groups,
)


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
    def test_workspace_and_measurement_cache_reject_coordinate_drift(self) -> None:
        gray = np.zeros((80, 240), dtype=np.uint8)
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        with self.assertRaises(ValueError):
            work_gray(gray, "diagonal")
        with self.assertRaises(ValueError):
            MeasurementCache(
                "diagonal",
                gray,
                gray,
                gray.astype(np.float32),
                statistics,
            )
        with self.assertRaises(ValueError):
            MeasurementCache(
                "horizontal",
                gray,
                gray[:, :-1],
                gray.astype(np.float32),
                statistics,
            )

    def test_cached_output_does_not_rebuild_detection_gray(self) -> None:
        from tools.tests.architecture_contracts import PROJECT_ROOT

        source = (
            PROJECT_ROOT / "x5crop/runtime/analysis_reuse.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("make_base_gray_u8", source)

    def test_measurement_cache_uses_explicit_typed_keys(self) -> None:
        self.assertFalse(
            any(
                "Any" in str(annotation)
                for annotation in get_type_hints(MeasurementCache).values()
            )
        )

    def test_unavailable_content_threshold_is_cached_exactly_once(self) -> None:
        cache = _cache()
        geometry = candidate_fixture().geometry
        configuration = get_detection_configuration("135", "full").content
        with patch(
            "x5crop.detection.evidence.content.frame_support.content_evidence_threshold",
            return_value=None,
        ) as measurement:
            frame_content_evidence(geometry, cache, configuration)
            frame_content_evidence(geometry, cache, configuration)
        measurement.assert_called_once()

    def test_diagnostics_do_not_invalidate_detection_analysis(self) -> None:
        bundle = DetectionConfigurationBundle.for_format_mode("135", "full")
        configuration = bundle.initial_configuration
        changed_configuration = replace(
            configuration,
            diagnostics=replace(
                configuration.diagnostics,
                separator_overlay=replace(
                    configuration.diagnostics.separator_overlay,
                    tick_length_min=99,
                ),
            ),
        )
        changed = replace(
            bundle,
            resolved_configurations=(changed_configuration,),
        )
        self.assertEqual(
            analysis_configuration_fingerprint(bundle),
            analysis_configuration_fingerprint(changed),
        )

    def test_reuse_fingerprint_includes_every_resolved_configuration(self) -> None:
        bundle = DetectionConfigurationBundle.for_format_mode("135-dual", "full")
        lane_configuration = bundle.resolved_configurations[1]
        changed_lane = replace(
            lane_configuration,
            separator=replace(
                lane_configuration.separator,
                observation=replace(
                    lane_configuration.separator.observation,
                    maximum_observations=(
                        lane_configuration.separator.observation.maximum_observations
                        + 1
                    ),
                ),
            ),
        )
        changed = replace(
            bundle,
            resolved_configurations=(
                bundle.initial_configuration,
                changed_lane,
            ),
        )
        self.assertNotEqual(
            analysis_configuration_fingerprint(bundle),
            analysis_configuration_fingerprint(changed),
        )

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

    def test_measurement_cache_reports_exact_lookup_hits_and_misses(self) -> None:
        cache = _cache()
        corridor = Box(0, 10, 240, 70)
        parameters = SeparatorProfileParameters()

        cached_separator_profile(cache, corridor, parameters)
        cached_separator_profile(cache, corridor, parameters)

        self.assertEqual(cache.lookup_statistics.hits, 1)
        self.assertEqual(cache.lookup_statistics.misses, 1)

    def test_boundary_paths_are_measured_once_across_count_hypotheses(self) -> None:
        cache = _cache()
        parameters = BoundaryPathParameters()
        with patch(
            "x5crop.detection.candidate.proposal.sequence.boundary_path_groups",
            return_value=(),
        ) as measurement:
            first = cached_boundary_path_groups(cache, parameters)
            second = cached_boundary_path_groups(cache, parameters)
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

    def test_profile_cache_uses_the_canonical_measured_corridor(self) -> None:
        cache = _cache()
        parameters = SeparatorProfileParameters()
        with patch(
            "x5crop.cache.separator.separator_profile",
            side_effect=lambda crop, _statistics, _params: np.zeros(
                crop.shape[1],
                dtype=np.float32,
            ),
        ) as measurement:
            cached_separator_profile(cache, Box(-20, 0, 120, 80), parameters)

        key = next(iter(cache.separator_profiles))
        self.assertEqual(key.region, Box(0, 0, 120, 80))
        self.assertEqual(measurement.call_args.args[0].shape, (80, 120))

    def test_profile_cache_rejects_corridor_outside_the_workspace(self) -> None:
        cache = _cache()
        with self.assertRaises(ValueError):
            cached_separator_profile(
                cache,
                Box(300, 0, 400, 80),
                SeparatorProfileParameters(),
            )
        self.assertEqual(cache.separator_profiles, {})

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
        self.assertFalse(hasattr(cache, "separator_profiles_full"))
        key = next(iter(cache.separator_profiles))
        self.assertEqual(
            key,
            MeasurementRegionKey(parameters, Box(0, 0, 240, 80)),
        )


if __name__ == "__main__":
    unittest.main()
