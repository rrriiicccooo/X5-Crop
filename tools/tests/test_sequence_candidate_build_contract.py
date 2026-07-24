from __future__ import annotations

from inspect import signature
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.tests.support.frame_sequence import (
    dimensions,
    scope,
    separator,
    sequence_search_index,
)
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.candidate.build.sequence_candidate import (
    build_sequence_candidate,
)
from x5crop.detection.candidate.plan.model import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.detection.candidate.proposal.sequence import (
    FrameSequenceObservations,
)
from x5crop.detection.context import DetectionRequest
from x5crop.detection.physical.separator.observations import (
    SeparatorObservationSet,
)
from x5crop.detection.physical.frame_sequence_solver import (
    solve_frame_sequence,
)
from x5crop.detection.physical.frame_sequence_result import FrameSequenceSolveResult
from tools.tests.support.photo_edges import shared_short_axis_fixture
from x5crop.domain import EvidenceState
from x5crop.domain import BoundarySide
from x5crop.image.content import ContentRegionObservation


class SequenceCandidateBuildContractTest(unittest.TestCase):
    def test_candidate_build_consumes_resolved_shared_short_axis(self) -> None:
        parameters = signature(build_sequence_candidate).parameters
        source = (
            Path(__file__).resolve().parents[2]
            / "x5crop/detection/candidate/build/sequence_candidate.py"
        ).read_text(encoding="utf-8")

        self.assertIn("short_axis_plan", parameters)
        self.assertIn("sequence_observations", parameters)
        self.assertNotIn("shared_short_axis_fixture(", source)
        self.assertNotIn("cached_separator_profile", source)
        self.assertNotIn("propose_separator_bands", source)
        self.assertNotIn("measure_separator_cross_axis_support", source)

    def test_separator_observation_exhaustion_reaches_candidate_geometry(self) -> None:
        search_scope = scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
            holder_sides=(BoundarySide.TOP, BoundarySide.BOTTOM),
        )
        cross_axis_plan = shared_short_axis_fixture(search_scope)
        frame_dimensions = dimensions(100.0, 100.0)
        observation = separator(
            100.0,
            110.0,
            supported=True,
            short_axis=cross_axis_plan,
        )
        search_index = sequence_search_index(
            search_scope,
            (observation,),
            support_budget_exhausted=True,
        )
        solved = solve_frame_sequence(
            search_index,
            search_scope,
            cross_axis_plan,
            2,
            frame_dimensions,
            ContentRegionObservation(search_scope.holder_safety.box, (), 0),
            maximum_assignment_evaluations=1_000,
            strip_mode="full",
            nominal_count=2,
        )
        self.assertIsInstance(solved, FrameSequenceSolveResult)
        assert isinstance(solved, FrameSequenceSolveResult)
        self.assertEqual(solved.search_outcome.state, EvidenceState.SUPPORTED)

        sequence_observations = FrameSequenceObservations(
            SeparatorObservationSet(
                (observation.observation,),
            ),
            search_index,
        )
        configuration = get_detection_configuration("135", "full")
        with patch(
                "x5crop.detection.candidate.build.sequence_candidate.solve_frame_sequence",
                return_value=solved,
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
                cross_axis_plan,
                sequence_observations,
                frame_dimensions,
                ContentRegionObservation(search_scope.holder_safety.box, (), 0),
                solver_parameters=configuration.candidate_plan.sequence_solver,
            )

        self.assertIsNotNone(outcome.candidate)
        assert outcome.candidate is not None
        self.assertNotIn(
            "search_budget_exhausted",
            outcome.candidate.geometry.__dataclass_fields__,
        )
        self.assertTrue(outcome.physical_search.budget_exhausted)


if __name__ == "__main__":
    unittest.main()
