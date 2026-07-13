from __future__ import annotations

from dataclasses import replace
from inspect import signature
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
from x5crop.detection.candidate.plan.count_hypotheses import (
    CountHypothesis,
    CountHypothesisPlan,
    CountHypothesisSource,
    count_hypothesis_plan,
)
from x5crop.detection.candidate.selection.choose import (
    candidate_rank,
    select_candidates,
)
from x5crop.detection.geometry_resolution import GeometryResolution
from x5crop.detection.evidence.partial_edge import partial_edge_safety_evidence
from x5crop.formats import format_spec


class AutoCountContractTest(unittest.TestCase):
    def test_unresolved_rank_protects_content_before_preferring_larger_count(
        self,
    ) -> None:
        def candidate(
            count: int,
            *,
            covered: int = 100,
            contradicted: tuple[str, ...] = (),
        ) -> SimpleNamespace:
            return SimpleNamespace(
                evidence_quality=EvidenceQuality(
                    supported=(),
                    contradicted=contradicted,
                    unavailable=(),
                    covered_content_px=covered,
                    uncovered_content_px=0,
                    supported_proof_paths=(),
                    physical_residuals=None,
                ),
                geometry=SimpleNamespace(
                    count=count,
                    strip_mode="partial",
                    automatic_processing_supported=False,
                ),
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
        )
        resolved = CountHypothesisEvaluation(
            candidate.count_hypothesis,
            (candidate,),
            selection_fixture(candidate),
        )
        self.assertFalse(unresolved.geometry_resolved)
        self.assertTrue(resolved.geometry_resolved)

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
            completed, stopped_after_count = evaluate(object(), plan)

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

        def evaluate_one(
            _context,
            hypothesis,
            *,
            larger_count_hypotheses_resolved,
        ):
            larger_count_states.append(larger_count_hypotheses_resolved)
            return SimpleNamespace(
                hypothesis=hypothesis,
                geometry_resolved=hypothesis.count == 2,
            )

        evaluate = getattr(detection_pipeline, "_evaluate_count_hypotheses")
        with patch.object(
            detection_pipeline,
            "evaluate_count_hypothesis",
            side_effect=evaluate_one,
        ):
            completed, stopped_after_count = evaluate(object(), plan)

        self.assertEqual(completed, tuple(
            SimpleNamespace(
                hypothesis=hypothesis,
                geometry_resolved=hypothesis.count == 2,
            )
            for hypothesis in hypotheses
        ))
        self.assertEqual(larger_count_states, [True, False, False])
        self.assertIsNone(stopped_after_count)

    def test_geometry_resolution_names_larger_count_resolution(self) -> None:
        fields = GeometryResolution.__dataclass_fields__
        self.assertIn("larger_count_hypotheses_resolved", fields)
        self.assertNotIn("larger_counts_evaluated", fields)

    def test_geometry_resolution_names_resolved_alternatives(self) -> None:
        fields = GeometryResolution.__dataclass_fields__
        self.assertIn("alternative_geometries_resolved", fields)

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
                candidate.assessment.evidence.photo_sequence_coverage,
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
        ).geometry_resolution
        self.assertTrue(resolution.count_resolved)
        self.assertFalse(resolution.placement_resolved)


if __name__ == "__main__":
    unittest.main()
