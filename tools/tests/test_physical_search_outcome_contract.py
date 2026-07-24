from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.support.frame_sequence import (
    dimensions,
    scope,
    sequence_search_index,
)
from tools.tests.support.physical_gates import candidate_fixture
from x5crop.detection.candidate.execution.model import CountHypothesisEvaluation
from x5crop.detection.candidate.plan.model import (
    CountHypothesis,
    CountHypothesisSource,
)
from x5crop.detection.candidate.selection.choose import select_candidates
from x5crop.detection.physical.model import (
    AssignmentConsensusOutcome,
    DualLaneFrameSolution,
    FrameSequenceSolution,
    ReviewOnlyContainment,
)
from x5crop.detection.physical.frame_sequence_solver import (
    solve_frame_sequence,
)
from x5crop.detection.physical.frame_sequence_result import FrameSequenceSolveFailure
from tools.tests.support.photo_edges import shared_short_axis_fixture
from x5crop.domain import (
    BoundaryAxis,
    EvidenceState,
    HolderSafetyEnvelope,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
    combined_physical_search_outcome,
)
from x5crop.image.content import ContentRegionObservation


def search_outcome(
    *facts: PhysicalSearchFact,
) -> PhysicalSearchOutcome:
    return PhysicalSearchOutcome(facts)


class PhysicalSearchOutcomeContractTest(unittest.TestCase):
    def test_search_facts_have_one_typed_physical_state(self) -> None:
        self.assertEqual(
            search_outcome(PhysicalSearchFact.SOLUTION_FOUND).state,
            EvidenceState.SUPPORTED,
        )
        self.assertEqual(
            search_outcome(
                PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
            ).state,
            EvidenceState.CONTRADICTED,
        )
        for unavailable_fact in (
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
        ):
            with self.subTest(fact=unavailable_fact):
                self.assertEqual(
                    search_outcome(unavailable_fact).state,
                    EvidenceState.UNAVAILABLE,
                )

    def test_dimension_option_outcomes_preserve_unavailable_search(self) -> None:
        combined = combined_physical_search_outcome(
            (
                search_outcome(
                    PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
                ),
                search_outcome(
                    PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
                ),
            )
        )

        self.assertEqual(combined.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            set(combined.facts),
            {
                PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            },
        )

    def test_physical_search_does_not_own_execution_statistics(self) -> None:
        self.assertNotIn(
            "assignment_evaluations",
            PhysicalSearchOutcome.__dataclass_fields__,
        )

    def test_search_fact_order_has_one_canonical_identity(self) -> None:
        left = search_outcome(
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            PhysicalSearchFact.SOLUTION_FOUND,
        )
        right = search_outcome(
            PhysicalSearchFact.SOLUTION_FOUND,
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
        )

        self.assertEqual(left, right)
        self.assertEqual(left.facts, right.facts)

    def test_complete_solution_and_contradicted_option_remain_supported(self) -> None:
        combined = combined_physical_search_outcome(
            (
                search_outcome(PhysicalSearchFact.SOLUTION_FOUND),
                search_outcome(PhysicalSearchFact.CONSTRAINTS_CONTRADICTED),
            )
        )

        self.assertEqual(combined.state, EvidenceState.SUPPORTED)
        self.assertEqual(
            combined.facts,
            (PhysicalSearchFact.SOLUTION_FOUND,),
        )

    def test_global_contradiction_cannot_coexist_with_other_search_facts(
        self,
    ) -> None:
        for other in (
            PhysicalSearchFact.SOLUTION_FOUND,
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
        ):
            with self.subTest(other=other):
                with self.assertRaises(ValueError):
                    search_outcome(
                        PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
                        other,
                    )

    def test_missing_cross_axis_measurement_is_not_count_contradiction(self) -> None:
        search_scope = scope(
            width=210,
            height=120,
            leading=0.0,
            trailing=210.0,
            top=10.0,
            bottom=110.0,
        )
        long_paths = tuple(
            path
            for path in search_scope.raw_boundary_paths
            if path.axis == BoundaryAxis.LONG
        )
        search_scope = replace(
            search_scope,
            raw_boundary_paths=long_paths,
            holder_safety=HolderSafetyEnvelope(
                tuple(
                    boundary
                    for boundary in search_scope.holder_safety.boundaries
                    if all(path in long_paths for path in boundary.supporting_paths)
                ),
                search_scope.holder_safety.containment_fallback,
            ),
        )
        frame_dimensions = dimensions(100.0, 100.0)
        visible_content = ContentRegionObservation(
            search_scope.holder_safety.box,
            (),
            0,
        )
        cross_axis_plan = shared_short_axis_fixture(search_scope)
        solved = solve_frame_sequence(
            sequence_search_index(search_scope),
            search_scope,
            cross_axis_plan,
            2,
            frame_dimensions,
            visible_content,
            maximum_assignment_evaluations=1_000,
            strip_mode="full",
            nominal_count=2,
        )

        self.assertIsInstance(solved, FrameSequenceSolveFailure)
        assert isinstance(solved, FrameSequenceSolveFailure)
        self.assertEqual(solved.search_outcome.state, EvidenceState.UNAVAILABLE)
        self.assertIn(
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
            solved.search_outcome.facts,
        )

    def test_count_resolution_consumes_physical_search_outcome(self) -> None:
        candidate = candidate_fixture()
        physical_search = search_outcome(
            PhysicalSearchFact.SOLUTION_FOUND,
            PhysicalSearchFact.MEASUREMENTS_UNAVAILABLE,
        )
        selection = select_candidates(
            (candidate,),
            larger_count_search_complete=True,
            physical_search=physical_search,
        )
        evaluation = CountHypothesisEvaluation(
            hypothesis=candidate.count_hypothesis,
            candidates=(candidate,),
            selection=selection,
            physical_search=physical_search,
        )

        self.assertFalse(selection.geometry_resolution.supported)
        self.assertFalse(evaluation.geometry_resolved)
        self.assertEqual(evaluation.physical_search.state, EvidenceState.UNAVAILABLE)

    def test_exhaustive_empty_count_hypothesis_is_contradicted(self) -> None:
        physical_search = search_outcome(
            PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
        )
        evaluation = CountHypothesisEvaluation(
            hypothesis=CountHypothesis(
                5,
                "partial",
                CountHypothesisSource.AUTOMATIC,
            ),
            candidates=(),
            selection=None,
            physical_search=physical_search,
        )

        self.assertEqual(
            evaluation.physical_search.state,
            EvidenceState.CONTRADICTED,
        )

    def test_physical_geometry_does_not_own_execution_search_state(self) -> None:
        for geometry_type in (
            FrameSequenceSolution,
            DualLaneFrameSolution,
            ReviewOnlyContainment,
        ):
            with self.subTest(geometry_type=geometry_type.__name__):
                self.assertNotIn(
                    "search_budget_exhausted",
                    geometry_type.__dataclass_fields__,
                )
        self.assertNotIn(
            "budget_exhausted",
            {outcome.value for outcome in AssignmentConsensusOutcome},
        )


if __name__ == "__main__":
    unittest.main()
