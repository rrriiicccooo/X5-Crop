from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import inspect
import unittest

from x5crop.debug.status import debug_status_parts
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from x5crop.detection.geometry import CandidateGeometry
from x5crop.detection.candidate.selection.model import SelectionResult
from x5crop.detection.decision.model import DecisionGateAssessment, FinalDetection
from x5crop.detection.candidate.assessment.candidate_gate import (
    CandidateGateAssessment,
)
from x5crop.detection.final import finalize
from x5crop.detection.pipeline import choose_detection
from x5crop.export.actions import copy_for_review_if_needed, write_crops_if_allowed
from x5crop.report.result_builder import result_from_detection
from x5crop.report.record import report_record_for_final_detection


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DetectionStageTypeContractTests(unittest.TestCase):
    def test_candidate_stages_are_immutable_and_separate(self) -> None:
        geometry_fields = {field.name for field in fields(CandidateGeometry)}
        built_fields = {field.name for field in fields(BuiltCandidate)}
        assessed_fields = {field.name for field in fields(AssessedCandidate)}
        final_fields = {field.name for field in fields(FinalDetection)}

        self.assertNotIn("detail", geometry_fields)
        self.assertEqual(
            built_fields,
            {"geometry", "count_hypothesis", "build_diagnostics"},
        )
        self.assertEqual(
            assessed_fields,
            {"geometry", "count_hypothesis", "assessment"},
        )
        self.assertIn("evidence", CandidateAssessment.__dataclass_fields__)
        self.assertIn("frame_coverage", CandidateEvidence.__dataclass_fields__)
        self.assertTrue(CandidateGeometry.__dataclass_params__.frozen)
        self.assertTrue(BuiltCandidate.__dataclass_params__.frozen)
        self.assertTrue(AssessedCandidate.__dataclass_params__.frozen)
        self.assertNotIn("status", final_fields)
        self.assertNotIn("final_review_reasons", final_fields)
        self.assertIn("trace", final_fields)
        self.assertIn("work_film_span", final_fields)
        self.assertIn("pitch", final_fields)

    def test_gate_outcomes_are_derived_from_canonical_checks(self) -> None:
        candidate_fields = set(CandidateGateAssessment.__dataclass_fields__)
        decision_fields = set(DecisionGateAssessment.__dataclass_fields__)

        self.assertNotIn("passed", candidate_fields)
        self.assertNotIn("failed_checks", candidate_fields)
        self.assertNotIn("passed", decision_fields)
        self.assertNotIn("final_review_reasons", decision_fields)
        self.assertNotIn("reason_inputs", decision_fields)

    def test_final_detection_has_no_output_alias_properties(self) -> None:
        self.assertNotIn("outer", FinalDetection.__dict__)
        self.assertNotIn("frames", FinalDetection.__dict__)
        self.assertNotIn("gaps", FinalDetection.__dict__)
        self.assertNotIn("restore_current_schema", FinalDetection.__dict__)

    def test_pipeline_returns_selection_without_pass_through_wrapper(self) -> None:
        import x5crop.detection.pipeline as pipeline

        self.assertFalse(hasattr(pipeline, "CandidatePipelineResult"))
        self.assertEqual(inspect.signature(choose_detection).return_annotation, "SelectionResult")

    def test_count_hypothesis_flows_without_identity_translation(self) -> None:
        import x5crop.detection.candidate.model as candidate_model

        self.assertFalse(hasattr(candidate_model, "CountHypothesisIdentity"))
        source = (
            PROJECT_ROOT
            / "x5crop"
            / "detection"
            / "candidate"
            / "execution"
            / "count_hypothesis.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("_count_hypothesis_identity", source)

    def test_gap_and_guidance_flows_have_no_single_field_wrappers(self) -> None:
        from x5crop.detection.candidate.build import separator_sources
        from x5crop.detection.guidance import content_separator
        from x5crop.detection.physical.separator import proposal
        from x5crop.geometry import separator_width_profile
        from x5crop.geometry import gap_search

        for module, class_name in (
            (separator_sources, "InitialSeparatorGapResult"),
            (proposal, "SeparatorGapSearchResult"),
            (content_separator, "ContentSeparatorGuidance"),
            (
                separator_width_profile,
                "SeparatorWidthGapCandidateSearchResult",
            ),
            (gap_search, "GapRankingWeights"),
        ):
            self.assertFalse(hasattr(module, class_name), class_name)

    def test_output_surfaces_require_final_detection(self) -> None:
        functions = (
            debug_status_parts,
            copy_for_review_if_needed,
            write_crops_if_allowed,
            result_from_detection,
            report_record_for_final_detection,
            finalize.finalize_detection,
        )
        for function in functions:
            with self.subTest(function=function.__name__):
                annotation = inspect.signature(function).parameters["detection"].annotation
                self.assertEqual(annotation, "FinalDetection")

    def test_candidate_layers_do_not_import_final_detection(self) -> None:
        checked_roots = (
            PROJECT_ROOT / "x5crop" / "detection" / "candidate",
            PROJECT_ROOT / "x5crop" / "detection" / "physical",
            PROJECT_ROOT / "x5crop" / "detection" / "guidance",
            PROJECT_ROOT / "x5crop" / "detection" / "evidence",
        )
        offenders = [
            str(path.relative_to(PROJECT_ROOT))
            for root in checked_roots
            for path in root.rglob("*.py")
            if "FinalDetection" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_domain_does_not_own_detection_lifecycle_types(self) -> None:
        import x5crop.domain as domain

        self.assertFalse(hasattr(domain, "DetectionCandidate"))
        self.assertFalse(hasattr(domain, "FinalDetection"))
        self.assertFalse((PROJECT_ROOT / "x5crop" / "detection" / "detail.py").exists())

    def test_old_decision_and_finalization_wrappers_are_absent(self) -> None:
        self.assertFalse(
            (PROJECT_ROOT / "x5crop" / "detection" / "decision" / "final_decision.py").exists()
        )
        finalization_text = (
            PROJECT_ROOT / "x5crop" / "detection" / "final" / "finalize.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("DetectionFinalizationResult", finalization_text)


if __name__ == "__main__":
    unittest.main()
