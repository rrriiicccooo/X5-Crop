from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from x5crop.configuration.separator import SeparatorObservationParameters
from x5crop.detection.physical.separator import observations as separator_observations
from x5crop.detection.physical.separator.observations import (
    measure_separator_cross_axis_support,
    propose_separator_bands,
)
from x5crop.domain import Box, EvidenceState, PixelInterval
from x5crop.domain import (
    BoundaryAxis,
    BoundaryKind,
    GrayAppearanceObservation,
    GrayBoundaryPathObservation,
    GrayIntensityTail,
    MeasurementIdentity,
    MeasurementProvenance,
    PhotoApertureCrossAxisHypothesis,
)
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)


def _textured_workspace(height: int = 120, width: int = 240) -> np.ndarray:
    y, x = np.indices((height, width), dtype=np.int32)
    return ((3 * x + 5 * y + ((x * y) % 37)) % 256).astype(np.uint8)


def _cross_axis(height: int) -> PhotoApertureCrossAxisHypothesis:
    provenance = MeasurementProvenance(
        MeasurementIdentity.BOUNDARY_PATHS,
        "synthetic_short_axis",
        (MeasurementIdentity.GRAY_WORK,),
    )
    appearance = GrayAppearanceObservation(
        intensity_median=128.0,
        intensity_mad=1.0,
        texture_median=1.0,
        gradient_median=1.0,
        spatial_continuity=1.0,
        intensity_tail=GrayIntensityTail.MIDRANGE,
        provenance=provenance,
    )

    def path(position: float) -> GrayBoundaryPathObservation:
        interval = PixelInterval.exact(position)
        return GrayBoundaryPathObservation(
            BoundaryAxis.SHORT,
            interval,
            BoundaryKind.TONAL_TRANSITION,
            (interval,),
            appearance,
            appearance,
            provenance,
        )

    return PhotoApertureCrossAxisHypothesis(path(0.0), path(float(height)))


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
        profile,
        gray_work=gray,
        corridor=corridor,
        statistics=statistics,
        parameters=parameters,
    )
    measured = measure_separator_cross_axis_support(
        proposed,
        gray_work=gray,
        corridor=corridor,
        statistics=statistics,
        parameters=parameters,
        cross_axis_hypotheses=(_cross_axis(gray.shape[0]),),
    )
    return measured.observations[0] if measured.observations else None


class SeparatorCrossAxisContractTest(unittest.TestCase):
    def test_row_continuity_uses_the_exact_maximum_break_invariant(self) -> None:
        continuity = getattr(
            separator_observations,
            "_cross_axis_support_is_continuous",
            None,
        )
        self.assertIsNotNone(continuity)

        self.assertFalse(continuity(np.zeros(8, dtype=bool), 2))
        self.assertTrue(continuity(np.ones(8, dtype=bool), 0))
        self.assertTrue(
            continuity(
                np.array([False, False, True, True, False, False, True]),
                2,
            )
        )
        self.assertFalse(
            continuity(
                np.array([True, False, False, False, True]),
                2,
            )
        )

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
            states.append(observation.cross_axis_measurements[0].state)

        self.assertEqual(states, [EvidenceState.SUPPORTED] * 3)

    def test_local_content_patch_is_not_a_cross_axis_separator(self) -> None:
        gray = _textured_workspace()
        gray[15:45, 112:120] = 128

        observation = _measure(gray, 112, 120)

        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(
            observation.cross_axis_measurements[0].state,
            EvidenceState.CONTRADICTED,
        )


if __name__ == "__main__":
    unittest.main()
