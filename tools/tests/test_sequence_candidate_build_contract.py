from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from tools.tests.photo_aperture_solver_support import (
    dimensions,
    plan,
    scope,
    separator,
)
from x5crop.cache import MeasurementCache
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.build.sequence_candidate import (
    build_sequence_candidate,
)
from x5crop.detection.candidate.plan.count_hypotheses import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.detection.context import DetectionRequest
from x5crop.detection.physical.separator.observations import (
    SeparatorSupportSet,
)
from x5crop.detection.physical.sequence_solver import (
    PhotoSequenceSolveResult,
    solve_photo_sequence,
)
from x5crop.image.statistics import (
    ImageMeasurementStatisticsParameters,
    image_measurement_statistics,
)


class SequenceCandidateBuildContractTest(unittest.TestCase):
    def test_separator_observation_exhaustion_reaches_candidate_geometry(self) -> None:
        search_scope = scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
        )
        cross_axis_plan = plan(search_scope)
        frame_dimensions = dimensions(100.0, 100.0)
        observation = separator(
            100.0,
            110.0,
            supported=True,
            cross_axis=cross_axis_plan.hypotheses[0],
        )
        solved = solve_photo_sequence(
            (observation,),
            search_scope,
            cross_axis_plan,
            2,
            frame_dimensions,
            maximum_assignment_evaluations=1_000,
            maximum_solution_alternatives=16,
        )
        self.assertIsInstance(solved, PhotoSequenceSolveResult)
        assert isinstance(solved, PhotoSequenceSolveResult)
        self.assertFalse(solved.search_budget_exhausted)

        gray = np.zeros((120, 210), dtype=np.uint8)
        cache = MeasurementCache(
            "horizontal",
            gray,
            gray,
            gray.astype(np.float32),
            image_measurement_statistics(
                gray,
                ImageMeasurementStatisticsParameters(),
            ),
        )
        configuration = get_detection_configuration("135", "full")
        with (
            patch(
                "x5crop.detection.candidate.build.sequence_candidate.cached_separator_profile",
                return_value=np.zeros(210, dtype=np.float32),
            ),
            patch(
                "x5crop.detection.candidate.build.sequence_candidate.propose_separator_bands",
                return_value=(),
            ),
            patch(
                "x5crop.detection.candidate.build.sequence_candidate.photo_aperture_cross_axis_plan",
                return_value=cross_axis_plan,
            ),
            patch(
                "x5crop.detection.candidate.build.sequence_candidate.measure_separator_cross_axis_support",
                return_value=SeparatorSupportSet((observation,), True),
            ),
            patch(
                "x5crop.detection.candidate.build.sequence_candidate.solve_photo_sequence",
                return_value=solved,
            ),
        ):
            outcome = build_sequence_candidate(
                DetectionRequest("horizontal", "full", 2),
                configuration.physical_spec,
                CountHypothesis(
                    2,
                    "full",
                    CountHypothesisSource.REQUESTED,
                ),
                search_scope,
                frame_dimensions,
                cache=cache,
                separator_configuration=configuration.separator,
                solver_parameters=configuration.candidate_plan.sequence_solver,
            )

        self.assertIsNotNone(outcome.candidate)
        assert outcome.candidate is not None
        self.assertTrue(outcome.candidate.geometry.search_budget_exhausted)
        self.assertTrue(outcome.search_budget_exhausted)


if __name__ == "__main__":
    unittest.main()
