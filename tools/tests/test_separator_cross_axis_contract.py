from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from x5crop.configuration.separator import SeparatorObservationParameters
from x5crop.detection.physical.separator import observations as separator_observations
from x5crop.detection.physical.separator.observations import (
    measure_separator_cross_axis_support,
    propose_separator_bands,
)
from x5crop.domain import BoundarySide, Box, EvidenceState, PixelInterval
from x5crop.domain import ObservationId
from x5crop.detection.physical.short_axis import SharedShortAxisPlan
from tools.tests.support.photo_edges import shared_short_axis_fixture_from_edges
from tools.tests.support.frame_sequence import photo_edge_path
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)
from x5crop.image.separator_profile import (
    SeparatorProfileMeasurement,
    SeparatorProfileParameters,
    measure_separator_profile,
)


def _textured_workspace(height: int = 120, width: int = 240) -> np.ndarray:
    y, x = np.indices((height, width), dtype=np.int32)
    return ((3 * x + 5 * y + ((x * y) % 37)) % 256).astype(np.uint8)


def _cross_axis(height: int) -> SharedShortAxisPlan:
    return shared_short_axis_fixture_from_edges(
        photo_edge_path(
            BoundarySide.TOP,
            0.0,
            "synthetic_top_photo_edge",
        ),
        photo_edge_path(
            BoundarySide.BOTTOM,
            float(height),
            "synthetic_bottom_photo_edge",
        ),
    )


def _profile_measurement(
    profile: np.ndarray,
    smoothing_window_px: int,
) -> SeparatorProfileMeasurement:
    return SeparatorProfileMeasurement(
        raw_score=profile.copy(),
        smoothed_score=profile.copy(),
        smoothing_window_px=smoothing_window_px,
        local_baseline_window_px=64,
    )


def _measure(gray: np.ndarray, start: int, end: int):
    profile = np.zeros(gray.shape[1], dtype=np.float32)
    profile[start:end] = 1.0
    parameters = SeparatorObservationParameters(
        activation_percentile=99.0,
        minimum_run_px=1,
        maximum_observations=8,
    )
    statistics = image_measurement_statistics(
        gray,
        ImageMeasurementStatisticsParameters(),
    )
    corridor = Box(0, 0, gray.shape[1], gray.shape[0])
    proposed = propose_separator_bands(
        _profile_measurement(profile, 1),
        gray_work=gray,
        corridor=corridor,
        statistics=statistics,
        parameters=parameters,
        transform_position_uncertainty_px=0.0,
    )
    measured = measure_separator_cross_axis_support(
        proposed,
        gray_work=gray,
        corridor=corridor,
        statistics=statistics,
        parameters=parameters,
        shared_short_axis=_cross_axis(gray.shape[0]),
    )
    return (
        measured.canonical_supports[0]
        if measured.canonical_supports
        else None
    )


class SeparatorCrossAxisContractTest(unittest.TestCase):
    def test_one_sided_separator_path_preserves_only_its_measured_edge(
        self,
    ) -> None:
        height = 120
        width = 240
        corridor = Box(0, 0, width, height)
        band = np.full((height, 8), 40, dtype=np.uint8)
        row_measurements = separator_observations._SeparatorBandRowMeasurements(
            corridor=corridor,
            band=band,
            row_appearance=np.full(height, 40.0, dtype=np.float64),
            row_texture=np.zeros(height, dtype=np.float64),
            leading_flank_appearance=np.full(height, 160.0, dtype=np.float64),
            trailing_flank_appearance=np.full(height, 40.0, dtype=np.float64),
            leading_flank_texture=np.zeros(height, dtype=np.float64),
            trailing_flank_texture=np.zeros(height, dtype=np.float64),
        )
        no_profile_edges = separator_observations._SeparatorBoundaryRowSupport(
            leading=np.zeros(height, dtype=bool),
            trailing=np.zeros(height, dtype=bool),
        )
        statistics = image_measurement_statistics(
            _textured_workspace(height=height, width=width),
            ImageMeasurementStatisticsParameters(),
        )

        measurement = separator_observations._cross_axis_measurement(
            ObservationId("one_sided_separator"),
            row_measurements,
            no_profile_edges,
            _cross_axis(height),
            statistics,
            SeparatorObservationParameters(
                minimum_cross_axis_supported_ratio=0.50,
            ),
        )

        self.assertEqual(
            measurement.leading_edge_path.state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            measurement.trailing_edge_path.state,
            EvidenceState.CONTRADICTED,
        )
        self.assertEqual(measurement.supported_edge_count, 1)
        self.assertFalse(measurement.complete_separator_supported)
        self.assertTrue(measurement.has_supported_path)
        self.assertFalse(hasattr(measurement, "state"))

    def test_locally_distinct_midrange_band_remains_observable(self) -> None:
        height = 120
        width = 600
        gray = np.random.default_rng(17).integers(
            40,
            121,
            size=(height, width),
            dtype=np.uint8,
        )
        gray[:, :40] = 0
        gray[:, -40:] = 180
        gray[:, 280:320] = 80
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        profile_parameters = SeparatorProfileParameters(
            local_baseline_min_px=160,
            smooth_ratio=0.0,
            smooth_min=3,
        )
        observation_parameters = SeparatorObservationParameters(
            activation_percentile=95.0,
            prominence_activation_percentile=80.0,
            maximum_observations=16,
        )
        corridor = Box(0, 0, width, height)

        proposed = propose_separator_bands(
            measure_separator_profile(
                gray,
                statistics,
                profile_parameters,
            ),
            gray_work=gray,
            corridor=corridor,
            statistics=statistics,
            parameters=observation_parameters,
            transform_position_uncertainty_px=0.0,
        )

        self.assertTrue(
            any(
                observation.leading_edge.midpoint <= 285.0
                and observation.trailing_edge.midpoint >= 315.0
                for observation in proposed.observations
            )
        )

    def test_separator_profile_preserves_raw_score_for_edge_localization(
        self,
    ) -> None:
        gray = _textured_workspace()
        gray[:, 112:120] = 128
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )

        measurement = measure_separator_profile(
            gray,
            statistics,
            SeparatorProfileParameters(smooth_min=9),
        )

        self.assertEqual(measurement.raw_score.shape, (gray.shape[1],))
        self.assertEqual(measurement.smoothed_score.shape, (gray.shape[1],))
        self.assertEqual(measurement.smoothing_window_px, 9)
        self.assertFalse(np.shares_memory(
            measurement.raw_score,
            measurement.smoothed_score,
        ))

    def test_local_prominence_preserves_bands_below_global_activation(
        self,
    ) -> None:
        gray = _textured_workspace(height=120, width=1_000)
        gray[:, 100:300] = 128
        gray[:, 500:520] = 128
        gray[:, 800:820] = 128
        profile = np.zeros(1_000, dtype=np.float32)
        profile[100:300] = 1.0
        profile[500:520] = 0.40
        profile[800:820] = 0.35
        parameters = SeparatorObservationParameters(
            activation_percentile=90.0,
            prominence_activation_percentile=80.0,
            maximum_observations=8,
        )

        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
            statistics=image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )

        spans = tuple(observation.span for observation in proposed.observations)
        self.assertTrue(any(span.minimum <= 510.0 <= span.maximum for span in spans))
        self.assertTrue(any(span.minimum <= 810.0 <= span.maximum for span in spans))

    def test_local_feature_fragments_share_one_observation_budget_slot(
        self,
    ) -> None:
        gray = _textured_workspace(height=120, width=1_000)
        profile = np.zeros(1_000, dtype=np.float32)
        profile[100:300] = 1.0
        profile[500:510] = 0.40
        profile[515:525] = 0.35
        profile[530:540] = 0.30
        profile[800:820] = 0.35
        parameters = SeparatorObservationParameters(
            activation_percentile=90.0,
            prominence_activation_percentile=80.0,
            maximum_observations=3,
        )

        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
            statistics=image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )

        spans = tuple(observation.span for observation in proposed.observations)
        self.assertEqual(len(spans), 3)
        local_feature = next(
            span for span in spans if span.minimum <= 505.0 <= span.maximum
        )
        self.assertLess(local_feature.maximum - local_feature.minimum, 40.0)
        self.assertTrue(any(span.minimum <= 810.0 <= span.maximum for span in spans))

    def test_separator_edge_profiles_are_prepared_once_per_corridor(self) -> None:
        gray = _textured_workspace()
        gray[:, 48:56] = 128
        gray[:, 176:184] = 128
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[48:56] = 1.0
        profile[176:184] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )
        prepare_profiles = separator_observations._separator_edge_profiles

        with patch.object(
            separator_observations,
            "_separator_edge_profiles",
            wraps=prepare_profiles,
        ) as preparation:
            proposed = propose_separator_bands(
                _profile_measurement(profile, 1),
                gray_work=gray,
                corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
                statistics=image_measurement_statistics(
                    gray,
                    ImageMeasurementStatisticsParameters(),
                ),
                parameters=parameters,
                transform_position_uncertainty_px=0.0,
            )

        self.assertEqual(len(proposed.observations), 2)
        preparation.assert_called_once()

    def test_transform_uncertainty_expands_separator_edge_intervals(self) -> None:
        gray = _textured_workspace()
        gray[:, 112:120] = 128
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:120] = 1.0

        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
            statistics=image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            parameters=SeparatorObservationParameters(
                activation_percentile=99.0,
                minimum_run_px=1,
                maximum_observations=8,
            ),
            transform_position_uncertainty_px=2.0,
        )

        observation = proposed.observations[0]
        self.assertEqual(
            observation.leading_edge,
            PixelInterval(109.0, 114.0),
        )
        self.assertEqual(
            observation.trailing_edge,
            PixelInterval(117.0, 122.0),
        )
    def test_single_pixel_activation_cannot_form_two_separator_edges(self) -> None:
        gray = _textured_workspace()
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )

        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
            statistics=image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )

        self.assertEqual(proposed.observations, ())

    def test_profile_band_edges_preserve_crossing_uncertainty(self) -> None:
        gray = _textured_workspace()
        gray[:, 112:120] = 128

        support = _measure(gray, 112, 120)

        self.assertIsNotNone(support)
        assert support is not None
        self.assertEqual(support.observation.leading_edge, PixelInterval(111.0, 112.0))
        self.assertEqual(support.observation.trailing_edge, PixelInterval(119.0, 120.0))

    def test_cross_section_localization_is_not_reinflated_by_profile_smoothing(
        self,
    ) -> None:
        gray = np.zeros((120, 240), dtype=np.uint8)
        gray[:, 112:120] = 128
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:120] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )

        proposed = propose_separator_bands(
            _profile_measurement(profile, 9),
            gray_work=gray,
            corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
            statistics=statistics,
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )

        observation = proposed.observations[0]
        self.assertTrue(
            observation.leading_edge.intersects(PixelInterval(111.0, 112.0))
        )
        self.assertTrue(
            observation.trailing_edge.intersects(PixelInterval(119.0, 120.0))
        )
        self.assertLess(
            observation.leading_edge.maximum - observation.leading_edge.minimum,
            7.0,
        )
        self.assertLess(
            observation.trailing_edge.maximum - observation.trailing_edge.minimum,
            7.0,
        )

    def test_one_local_cross_section_cannot_relocate_a_strip_wide_edge(self) -> None:
        gray = np.full((90, 240), 128, dtype=np.uint8)
        gray[:10, 108:124] = 0
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:120] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
            edge_measurement_cross_sections=9,
            minimum_cross_axis_supported_ratio=0.50,
        )

        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
            statistics=image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )

        observation = proposed.observations[0]
        self.assertEqual(observation.leading_edge, PixelInterval(111.0, 112.0))
        self.assertEqual(observation.trailing_edge, PixelInterval(119.0, 120.0))

    def test_each_separator_edge_is_localized_independently(self) -> None:
        gray = _textured_workspace()
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:120] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )

        with patch.object(
            separator_observations,
            "_cross_section_band_edge_intervals",
            return_value=(PixelInterval(103.0, 104.0), None),
        ):
            proposed = propose_separator_bands(
                _profile_measurement(profile, 9),
                gray_work=gray,
                corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
                statistics=image_measurement_statistics(
                    gray,
                    ImageMeasurementStatisticsParameters(),
                ),
                parameters=parameters,
                transform_position_uncertainty_px=0.0,
            )

        observation = proposed.observations[0]
        self.assertEqual(observation.leading_edge, PixelInterval(103.0, 104.0))
        self.assertEqual(observation.trailing_edge, PixelInterval(115.0, 124.0))

    def test_raw_profile_crossings_localize_edges_when_cross_sections_are_unavailable(
        self,
    ) -> None:
        gray = _textured_workspace()
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:120] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )

        with patch.object(
            separator_observations,
            "_cross_section_band_edge_intervals",
            return_value=(None, None),
        ):
            proposed = propose_separator_bands(
                _profile_measurement(profile, 1),
                gray_work=gray,
                corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
                statistics=image_measurement_statistics(
                    gray,
                    ImageMeasurementStatisticsParameters(),
                ),
                parameters=parameters,
                transform_position_uncertainty_px=0.0,
            )

        observation = proposed.observations[0]
        self.assertEqual(observation.leading_edge, PixelInterval(111.0, 112.0))
        self.assertEqual(observation.trailing_edge, PixelInterval(119.0, 120.0))
        self.assertGreater(observation.width_px.minimum, 0.0)

    def test_raw_crossing_does_not_erase_profile_localization_uncertainty(
        self,
    ) -> None:
        gray = _textured_workspace()
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:120] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )

        with patch.object(
            separator_observations,
            "_cross_section_band_edge_intervals",
            return_value=(None, None),
        ):
            proposed = propose_separator_bands(
                _profile_measurement(profile, 9),
                gray_work=gray,
                corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
                statistics=image_measurement_statistics(
                    gray,
                    ImageMeasurementStatisticsParameters(),
                ),
                parameters=parameters,
                transform_position_uncertainty_px=0.0,
            )

        observation = proposed.observations[0]
        self.assertEqual(observation.leading_edge, PixelInterval(107.0, 116.0))
        self.assertEqual(observation.trailing_edge, PixelInterval(115.0, 124.0))

    def test_raw_profile_edges_are_translated_from_corridor_to_workspace(
        self,
    ) -> None:
        gray = _textured_workspace(width=340)
        profile = np.zeros(140, dtype=np.float32)
        profile[12:20] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )

        with patch.object(
            separator_observations,
            "_cross_section_band_edge_intervals",
            return_value=(None, None),
        ):
            proposed = propose_separator_bands(
                _profile_measurement(profile, 1),
                gray_work=gray,
                corridor=Box(100, 0, 240, gray.shape[0]),
                statistics=image_measurement_statistics(
                    gray,
                    ImageMeasurementStatisticsParameters(),
                ),
                parameters=parameters,
                transform_position_uncertainty_px=0.0,
            )

        observation = proposed.observations[0]
        self.assertEqual(observation.leading_edge, PixelInterval(111.0, 112.0))
        self.assertEqual(observation.trailing_edge, PixelInterval(119.0, 120.0))

    def test_cross_section_edge_dispersion_expands_separator_uncertainty(self) -> None:
        gray = _textured_workspace()
        gray[: gray.shape[0] // 2, 109:119] = 0
        gray[gray.shape[0] // 2 :, 115:125] = 0
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:122] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )

        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=Box(0, 0, gray.shape[1], gray.shape[0]),
            statistics=image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )

        observation = proposed.observations[0]
        self.assertLess(observation.leading_edge.minimum, 111.0)
        self.assertGreater(observation.leading_edge.maximum, 112.0)
        self.assertLess(observation.trailing_edge.minimum, 121.0)
        self.assertGreater(observation.trailing_edge.maximum, 122.0)

    def test_row_continuity_uses_the_exact_maximum_break_invariant(self) -> None:
        continuity = getattr(
            separator_observations,
            "_cross_axis_support_is_continuous",
            None,
        )
        self.assertIsNotNone(continuity)

        self.assertFalse(continuity(np.zeros(8, dtype=bool), 2, 4))
        self.assertTrue(continuity(np.ones(8, dtype=bool), 0, 4))
        self.assertTrue(
            continuity(
                np.array([False, False, True, True, False, False, True]),
                2,
                3,
            )
        )
        self.assertFalse(
            continuity(
                np.array([True, False, False, False, True]),
                2,
                2,
            )
        )

    def test_short_axis_safety_margins_are_not_internal_separator_breaks(
        self,
    ) -> None:
        continuity = separator_observations._cross_axis_support_is_continuous
        support = np.array(
            [False] * 10 + [True] * 80 + [False] * 10,
            dtype=bool,
        )

        self.assertTrue(continuity(support, 3, 50))

    def test_distant_noise_does_not_refute_a_continuous_supported_component(
        self,
    ) -> None:
        continuity = separator_observations._cross_axis_support_is_continuous
        support = np.array(
            [True] * 70 + [False] * 29 + [True],
            dtype=bool,
        )

        self.assertTrue(continuity(support, 3, 50))

    def test_isolated_short_path_cannot_prove_cross_axis_continuity(self) -> None:
        continuity = separator_observations._cross_axis_support_is_continuous
        support = np.array(
            [False] * 49 + [True] + [False] * 50,
            dtype=bool,
        )

        self.assertFalse(continuity(support, 3, 50))

    def test_cross_axis_measurement_does_not_reinflate_row_support_to_2d(self) -> None:
        source = separator_observations.__file__
        assert source is not None
        text = Path(source).read_text(encoding="utf-8")

        self.assertNotIn("row_support[:, np.newaxis]", text)
        self.assertNotIn("def _cross_axis_path_exists", text)

    def test_coherent_separator_is_independent_of_gray_polarity(self) -> None:
        states = []
        for value in (16, 128, 240):
            gray = _textured_workspace()
            gray[:, 112:120] = value
            observation = _measure(gray, 112, 120)
            self.assertIsNotNone(observation)
            assert observation is not None
            states.append(observation.measurement.complete_separator_supported)

        self.assertEqual(states, [True] * 3)

    def test_cross_axis_path_allows_gradual_gray_appearance_change(self) -> None:
        gray = _textured_workspace()
        row_values = np.linspace(
            32,
            224,
            gray.shape[0],
            dtype=np.uint8,
        )
        gray[:, 108:112] = 0
        gray[:, 112:120] = row_values[:, np.newaxis]
        gray[:, 120:124] = 255

        observation = _measure(gray, 112, 120)

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertTrue(observation.measurement.complete_separator_supported)

    def test_blurred_strip_wide_edges_use_local_contrast_not_peak_gradient(
        self,
    ) -> None:
        row_offset = ((np.arange(120) % 2) * 20).astype(np.uint8)
        gray = np.broadcast_to(
            (120 + row_offset)[:, np.newaxis],
            (120, 240),
        ).copy()
        gray[:, :72:2] = 0
        gray[:, 1:72:2] = 255
        for offset, value in enumerate((110, 100, 90, 80, 70, 60, 50, 40)):
            gray[:, 104 + offset] = value + row_offset
            gray[:, 127 - offset] = value + row_offset
        band_pattern = np.array((35, 45) * 4, dtype=np.uint8)
        gray[:, 112:120] = (
            band_pattern[np.newaxis, :] + row_offset[:, np.newaxis]
        )

        observation = _measure(gray, 112, 120)

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertTrue(observation.measurement.complete_separator_supported)

    def test_local_content_patch_is_not_a_cross_axis_separator(self) -> None:
        gray = _textured_workspace()
        gray[15:45, 112:120] = 128

        observation = _measure(gray, 112, 120)

        self.assertIsNone(observation)

    def test_cross_axis_contradictions_do_not_consume_search_budget(self) -> None:
        gray = _textured_workspace(height=120, width=400)
        false_runs = ((40, 48), (120, 128), (200, 208))
        for start, end in false_runs:
            gray[10:30, start:end] = 128
        gray[:, 320:328] = 128
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        for start, end in false_runs:
            profile[start:end] = 1.0
        profile[320:328] = 0.40
        parameters = SeparatorObservationParameters(
            activation_percentile=80.0,
            prominence_activation_percentile=80.0,
            minimum_run_px=1,
            maximum_observations=1,
        )
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        corridor = Box(0, 0, gray.shape[1], gray.shape[0])

        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=corridor,
            statistics=statistics,
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )
        measured = measure_separator_cross_axis_support(
            proposed,
            gray_work=gray,
            corridor=corridor,
            statistics=statistics,
            parameters=parameters,
            shared_short_axis=_cross_axis(gray.shape[0]),
        )

        self.assertFalse(measured.budget_exhausted)
        self.assertEqual(len(measured.canonical_supports), 1)
        support = measured.canonical_supports[0]
        self.assertTrue(support.measurement.complete_separator_supported)
        self.assertLessEqual(support.observation.leading_edge.minimum, 320.0)
        self.assertGreaterEqual(support.observation.trailing_edge.maximum, 328.0)

    def test_candidate_cross_axis_support_does_not_replace_raw_observation(self) -> None:
        gray = _textured_workspace()
        gray[:, 112:120] = 128
        profile = np.zeros(gray.shape[1], dtype=np.float32)
        profile[112:120] = 1.0
        parameters = SeparatorObservationParameters(
            activation_percentile=99.0,
            minimum_run_px=1,
            maximum_observations=8,
        )
        statistics = image_measurement_statistics(
            gray,
            ImageMeasurementStatisticsParameters(),
        )
        corridor = Box(0, 0, gray.shape[1], gray.shape[0])
        proposed = propose_separator_bands(
            _profile_measurement(profile, 1),
            gray_work=gray,
            corridor=corridor,
            statistics=statistics,
            parameters=parameters,
            transform_position_uncertainty_px=0.0,
        )
        raw = proposed.observations[0]

        measured = measure_separator_cross_axis_support(
            proposed,
            gray_work=gray,
            corridor=corridor,
            statistics=statistics,
            parameters=parameters,
            shared_short_axis=_cross_axis(gray.shape[0]),
        )

        self.assertIs(measured.canonical_supports[0].observation, raw)
        self.assertEqual(proposed.observations[0], raw)

    def test_nested_separator_supports_share_one_physical_location(self) -> None:
        canonicalize = getattr(
            separator_observations,
            "canonical_separator_supports",
            None,
        )
        self.assertIsNotNone(canonicalize)
        assert canonicalize is not None
        gray = _textured_workspace()
        gray[:, 112:128] = 128
        broad = _measure(gray, 112, 128)
        self.assertIsNotNone(broad)
        assert broad is not None
        narrow = replace(
            broad,
            observation=replace(
                broad.observation,
                leading_edge=PixelInterval(115.0, 116.0),
                trailing_edge=PixelInterval(119.0, 120.0),
            ),
        )

        canonical = canonicalize((narrow, broad))

        self.assertEqual(canonical, (broad,))


if __name__ == "__main__":
    unittest.main()
