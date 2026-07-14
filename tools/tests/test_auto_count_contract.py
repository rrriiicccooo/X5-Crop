from __future__ import annotations

from dataclasses import fields, replace
from inspect import getsource, signature
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.tests.physical_gate_support import candidate_fixture, selection_fixture
import x5crop.detection.pipeline as detection_pipeline
from x5crop.detection.candidate.assessment.candidate import (
    candidate_gate_for_evidence,
)
from x5crop.detection.candidate.execution.model import CountHypothesisEvaluation
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    EvidenceQuality,
)
from x5crop.detection.candidate.plan.counts import count_hypothesis_plan
from x5crop.detection.candidate.plan.model import (
    CountHypothesis,
    CountHypothesisPlan,
    CountHypothesisSource,
)
from x5crop.detection.candidate.selection.choose import (
    candidate_rank,
    select_candidates,
)
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.domain import (
    EvidenceState,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
)
from x5crop.formats import format_spec


class AutoCountContractTest(unittest.TestCase):
    @staticmethod
    def _physical_search(
        *facts: PhysicalSearchFact,
    ) -> PhysicalSearchOutcome:
        return PhysicalSearchOutcome(facts)

    def test_unresolved_rank_protects_content_before_preferring_larger_count(
        self,
    ) -> None:
        def candidate(
            count: int,
            *,
            covered: int = 100,
            contradicted: tuple[str, ...] = (),
            internal_boundary_contradiction_count: int = 0,
            supported_proof_paths: tuple[str, ...] = (),
        ) -> SimpleNamespace:
            return SimpleNamespace(
                evidence_quality=EvidenceQuality(
                    supported=(),
                    contradicted=contradicted,
                    unavailable=(),
                    internal_boundary_contradiction_count=(
                        internal_boundary_contradiction_count
                    ),
                    other_contradiction_count=(
                        len(contradicted)
                        - internal_boundary_contradiction_count
                    ),
                    covered_content_px=covered,
                    uncovered_content_px=0,
                    supported_proof_paths=supported_proof_paths,
                    physical_residuals=None,
                ),
                geometry=SimpleNamespace(
                    count=count,
                    strip_mode="partial",
                ),
                assessment=SimpleNamespace(gate=object()),
                count_hypothesis=CountHypothesis(
                    count,
                    "partial",
                    CountHypothesisSource.AUTOMATIC,
                ),
            )

        smaller_safe = candidate(2)
        larger_with_internal_cut = candidate(
            5,
            contradicted=("inter_photo_boundary_preservation",),
            internal_boundary_contradiction_count=1,
        )
        larger_with_less_coverage = candidate(5, covered=99)

        self.assertGreater(
            candidate_rank(smaller_safe),
            candidate_rank(larger_with_internal_cut),
        )
        self.assertGreater(
            candidate_rank(smaller_safe),
            candidate_rank(larger_with_less_coverage),
        )
        self.assertGreater(
            candidate_rank(candidate(5)),
            candidate_rank(smaller_safe),
        )

    def test_independent_physical_proof_precedes_partial_auto_count(self) -> None:
        def candidate(
            count: int,
            *,
            proof: tuple[str, ...],
        ) -> SimpleNamespace:
            return SimpleNamespace(
                evidence_quality=EvidenceQuality(
                    supported=(),
                    contradicted=(),
                    unavailable=(),
                    internal_boundary_contradiction_count=0,
                    other_contradiction_count=0,
                    covered_content_px=100,
                    uncovered_content_px=0,
                    supported_proof_paths=proof,
                    physical_residuals=None,
                ),
                geometry=SimpleNamespace(
                    count=count,
                    strip_mode="partial",
                ),
                assessment=SimpleNamespace(gate=object()),
                count_hypothesis=CountHypothesis(
                    count,
                    "partial",
                    CountHypothesisSource.AUTOMATIC,
                ),
            )

        independently_proven = candidate(
            2,
            proof=("separator_sequence_led",),
        )
        larger_unproven = candidate(
            5,
            proof=(),
        )

        self.assertGreater(
            candidate_rank(independently_proven),
            candidate_rank(larger_unproven),
        )

    def test_selection_uses_typed_contradiction_counts(self) -> None:
        quality_fields = {field.name for field in fields(EvidenceQuality)}
        self.assertIn("internal_boundary_contradiction_count", quality_fields)
        self.assertIn("other_contradiction_count", quality_fields)
        self.assertNotIn("rsplit", getsource(candidate_rank))

    def _plan(self, format_id: str, requested_count: int | None = None):
        return count_hypothesis_plan(
            strip_mode="partial",
            requested_count=requested_count,
            fmt=format_spec(format_id),
        )

    def test_partial_auto_searches_largest_count_first(self) -> None:
        self.assertEqual(
            [item.count for item in self._plan("135").hypotheses],
            [5, 4, 3, 2, 1],
        )

    def test_only_complete_underfilled_formats_include_nominal_count(self) -> None:
        for format_id in ("xpan", "120-66"):
            plan = self._plan(format_id)
            self.assertEqual(plan.hypotheses[0].count, format_spec(format_id).default_count)
        for format_id in ("135", "half", "120-645", "120-67"):
            counts = tuple(item.count for item in self._plan(format_id).hypotheses)
            self.assertNotIn(format_spec(format_id).default_count, counts)

    def test_requested_count_is_one_nonautomatic_hypothesis(self) -> None:
        plan = self._plan("135", 3)
        self.assertFalse(plan.automatic)
        self.assertEqual(tuple(item.count for item in plan.hypotheses), (3,))

    def test_invalid_requested_count_is_assembly_error(self) -> None:
        with self.assertRaises(ValueError):
            self._plan("120-66", 4)

    def test_count_plan_does_not_consume_pixel_measurements(self) -> None:
        self.assertNotIn("planning_evidence", signature(count_hypothesis_plan).parameters)

    def test_count_hypothesis_has_no_offset_grid(self) -> None:
        fields = self._plan("135").hypotheses[0].__dataclass_fields__
        self.assertNotIn("offsets", fields)
        self.assertNotIn("placement_source", fields)

    def test_early_stop_uses_geometry_resolution_only(self) -> None:
        candidate = candidate_fixture()
        self.assertTrue(candidate.assessment.gate.passed)
        unresolved = CountHypothesisEvaluation(
            candidate.count_hypothesis,
            (candidate,),
            selection_fixture(candidate, geometry_disagreement=True),
            self._physical_search(PhysicalSearchFact.SOLUTION_FOUND),
        )
        resolved = CountHypothesisEvaluation(
            candidate.count_hypothesis,
            (candidate,),
            selection_fixture(candidate),
            self._physical_search(PhysicalSearchFact.SOLUTION_FOUND),
        )
        self.assertFalse(unresolved.geometry_resolved)
        self.assertTrue(resolved.geometry_resolved)
        self.assertEqual(unresolved.hypothesis_state, EvidenceState.UNAVAILABLE)
        self.assertEqual(resolved.hypothesis_state, EvidenceState.SUPPORTED)

        hypotheses = tuple(
            CountHypothesis(count, "partial", CountHypothesisSource.AUTOMATIC)
            for count in (3, 2, 1)
        )
        plan = CountHypothesisPlan(hypotheses, True, None)
        evaluations = tuple(
            SimpleNamespace(
                hypothesis=hypothesis,
                geometry_resolved=hypothesis.count == 3,
            )
            for hypothesis in hypotheses
        )
        evaluate = getattr(detection_pipeline, "_evaluate_count_hypotheses")
        with patch.object(
            detection_pipeline,
            "evaluate_count_hypothesis",
            side_effect=evaluations,
        ) as evaluate_one:
            completed, stopped_after_count = evaluate(
                object(),
                plan,
                object(),
                object(),
            )

        self.assertEqual(completed, evaluations[:1])
        self.assertEqual(stopped_after_count, 3)
        self.assertEqual(evaluate_one.call_count, 1)

    def test_unresolved_larger_count_prevents_smaller_count_resolution(self) -> None:
        hypotheses = tuple(
            CountHypothesis(count, "partial", CountHypothesisSource.AUTOMATIC)
            for count in (3, 2, 1)
        )
        plan = CountHypothesisPlan(hypotheses, True, None)
        larger_count_states: list[bool] = []
        expected_scope = object()
        expected_content = object()

        def evaluate_one(
            _context,
            hypothesis,
            *,
            search_scope,
            visible_content,
            larger_count_hypotheses_resolved,
        ):
            self.assertIs(search_scope, expected_scope)
            self.assertIs(visible_content, expected_content)
            larger_count_states.append(larger_count_hypotheses_resolved)
            return SimpleNamespace(
                hypothesis=hypothesis,
                geometry_resolved=hypothesis.count == 2,
                hypothesis_state=EvidenceState.UNAVAILABLE,
            )

        evaluate = getattr(detection_pipeline, "_evaluate_count_hypotheses")
        with patch.object(
            detection_pipeline,
            "evaluate_count_hypothesis",
            side_effect=evaluate_one,
        ):
            completed, stopped_after_count = evaluate(
                object(),
                plan,
                expected_scope,
                expected_content,
            )

        self.assertEqual(completed, tuple(
            SimpleNamespace(
                hypothesis=hypothesis,
                geometry_resolved=hypothesis.count == 2,
                hypothesis_state=EvidenceState.UNAVAILABLE,
            )
            for hypothesis in hypotheses
        ))
        self.assertEqual(larger_count_states, [True, False, False])
        self.assertIsNone(stopped_after_count)

    def test_contradicted_larger_count_allows_smaller_count_resolution(self) -> None:
        hypotheses = tuple(
            CountHypothesis(count, "partial", CountHypothesisSource.AUTOMATIC)
            for count in (3, 2, 1)
        )
        plan = CountHypothesisPlan(hypotheses, True, None)
        larger_count_states: list[bool] = []
        expected_scope = object()
        expected_content = object()

        def evaluate_one(
            _context,
            hypothesis,
            *,
            search_scope,
            visible_content,
            larger_count_hypotheses_resolved,
        ):
            self.assertIs(search_scope, expected_scope)
            self.assertIs(visible_content, expected_content)
            larger_count_states.append(larger_count_hypotheses_resolved)
            supported = hypothesis.count == 2
            return SimpleNamespace(
                hypothesis=hypothesis,
                geometry_resolved=supported,
                hypothesis_state=(
                    EvidenceState.SUPPORTED
                    if supported
                    else EvidenceState.CONTRADICTED
                ),
            )

        evaluate = getattr(detection_pipeline, "_evaluate_count_hypotheses")
        with patch.object(
            detection_pipeline,
            "evaluate_count_hypothesis",
            side_effect=evaluate_one,
        ) as evaluate_one_mock:
            completed, stopped_after_count = evaluate(
                object(),
                plan,
                expected_scope,
                expected_content,
            )

        self.assertEqual(tuple(item.hypothesis.count for item in completed), (3, 2))
        self.assertEqual(larger_count_states, [True, True])
        self.assertEqual(stopped_after_count, 2)
        self.assertEqual(evaluate_one_mock.call_count, 2)

    def test_geometry_resolution_names_larger_count_resolution(self) -> None:
        fields = GeometryResolution.__dataclass_fields__
        self.assertIn("larger_count_hypotheses_resolved", fields)
        self.assertNotIn("larger_counts_evaluated", fields)

    def test_geometry_resolution_names_resolved_alternatives(self) -> None:
        fields = GeometryResolution.__dataclass_fields__
        self.assertIn("alternative_geometries_resolved", fields)

    def test_empty_candidate_pool_preserves_search_budget_exhaustion(self) -> None:
        hypothesis = CountHypothesis(
            5,
            "partial",
            CountHypothesisSource.AUTOMATIC,
        )
        evaluation = CountHypothesisEvaluation(
            hypothesis,
            (),
            None,
            self._physical_search(
                PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
            ),
        )

        candidates, physical_search = getattr(
            detection_pipeline,
            "_candidate_pool_for_count_resolution",
        )((evaluation,))

        self.assertEqual(candidates, ())
        self.assertTrue(physical_search.budget_exhausted)
        self.assertEqual(evaluation.hypothesis_state, EvidenceState.UNAVAILABLE)

    def test_exhaustive_empty_count_hypothesis_is_physically_contradicted(self) -> None:
        evaluation = CountHypothesisEvaluation(
            CountHypothesis(
                5,
                "partial",
                CountHypothesisSource.AUTOMATIC,
            ),
            (),
            None,
            self._physical_search(
                PhysicalSearchFact.CONSTRAINTS_CONTRADICTED,
            ),
        )

        self.assertEqual(evaluation.hypothesis_state, EvidenceState.CONTRADICTED)

    def test_count_search_exhaustion_does_not_rewrite_candidate_geometry(self) -> None:
        candidate = candidate_fixture()
        self.assertNotIn(
            "search_budget_exhausted",
            candidate.geometry.__dataclass_fields__,
        )

        selection = select_candidates(
            (candidate,),
            larger_count_hypotheses_resolved=True,
            physical_search=self._physical_search(
                PhysicalSearchFact.SOLUTION_FOUND,
                PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
            ),
        )

        self.assertTrue(
            selection.geometry_resolution.physical_search.budget_exhausted
        )
        self.assertFalse(selection.geometry_resolution.supported)

    def test_full_format_count_is_resolved_independently_of_placement(self) -> None:
        candidate = candidate_fixture(failed_candidate_check="boundary_proof")
        candidate = replace(
            candidate,
            count_hypothesis=CountHypothesis(
                2,
                "full",
                CountHypothesisSource.FORMAT_DEFAULT,
            ),
        )
        resolution = select_candidates(
            (candidate,),
            larger_count_hypotheses_resolved=True,
            physical_search=self._physical_search(
                PhysicalSearchFact.SOLUTION_FOUND,
            ),
        ).geometry_resolution
        self.assertTrue(resolution.count_resolved)
        self.assertFalse(resolution.placement_resolved)

    def test_requested_partial_count_is_resolved_independently_of_placement(self) -> None:
        candidate = candidate_fixture(failed_candidate_check="boundary_proof")
        geometry = replace(candidate.geometry, strip_mode="partial")
        hypothesis = CountHypothesis(
            2,
            "partial",
            CountHypothesisSource.REQUESTED,
        )
        built = BuiltCandidate(geometry, hypothesis, ())
        evidence = replace(
            candidate.assessment.evidence,
            partial_edge_safety=partial_edge_safety_evidence(
                geometry,
                candidate.assessment.evidence.photo_aperture_coverage,
                candidate.assessment.evidence.frame_dimensions,
                candidate.assessment.evidence.photo_content,
            ),
        )
        candidate = AssessedCandidate(
            geometry,
            hypothesis,
            CandidateAssessment(
                evidence,
                candidate_gate_for_evidence(
                    built,
                    evidence,
                ),
            ),
        )
        resolution = select_candidates(
            (candidate,),
            larger_count_hypotheses_resolved=True,
            physical_search=self._physical_search(
                PhysicalSearchFact.SOLUTION_FOUND,
            ),
        ).geometry_resolution
        self.assertTrue(resolution.count_resolved)
        self.assertFalse(resolution.placement_resolved)


if __name__ == "__main__":
    unittest.main()
