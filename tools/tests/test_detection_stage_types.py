from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import inspect
from types import SimpleNamespace
import unittest
from typing import get_type_hints

import numpy as np

from x5crop.debug.status import debug_status_parts
from x5crop.detection.candidate.model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
)
from x5crop.detection.physical.model import SequenceSolution
import x5crop.detection.physical.model as physical_model
from x5crop.detection.decision.model import DecisionGateAssessment
from x5crop.detection.final.model import FinalDetection
from x5crop.detection.context import DetectionContext, DetectionRequest
from x5crop.detection.candidate.assessment.candidate_gate import (
    CandidateGateAssessment,
)
from x5crop.detection.final import finalize
from x5crop.detection.pipeline import choose_detection
from x5crop.export.actions import copy_for_review_if_needed, write_crops_if_allowed
from x5crop.report.result_builder import result_from_detection
from x5crop.report.record import report_record_for_final_detection
from x5crop.domain import Box, CropEnvelope
from x5crop.output.model import OutputGeometry
from x5crop.units import ScanCalibration


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DetectionStageTypeContractTests(unittest.TestCase):
    def test_detection_request_and_context_reject_identity_drift(self) -> None:
        from x5crop.configuration.registry import get_detection_configuration

        with self.assertRaises(ValueError):
            DetectionRequest("diagonal", "full", None)
        with self.assertRaises(ValueError):
            DetectionRequest("horizontal", "unknown", None)
        with self.assertRaises(ValueError):
            DetectionRequest("horizontal", "partial", 0)

        calibration = ScanCalibration(None, None, "unavailable", False)
        full = get_detection_configuration("135", "full")
        dual = get_detection_configuration("135-dual", "full")
        lane = get_detection_configuration("135", "full")
        invalid_contexts = (
            lambda: DetectionContext(
                calibration,
                DetectionRequest("horizontal", "partial", None),
                full,
                None,
                SimpleNamespace(layout="horizontal"),
            ),
            lambda: DetectionContext(
                calibration,
                DetectionRequest("vertical", "full", None),
                full,
                None,
                SimpleNamespace(layout="horizontal"),
            ),
            lambda: DetectionContext(
                calibration,
                DetectionRequest("horizontal", "full", None),
                full,
                lane,
                SimpleNamespace(layout="horizontal"),
            ),
            lambda: DetectionContext(
                calibration,
                DetectionRequest("horizontal", "full", None),
                dual,
                None,
                SimpleNamespace(layout="horizontal"),
            ),
        )
        for factory in invalid_contexts:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_detection_context_contains_no_tiff_io_profile(self) -> None:
        self.assertNotIn("image_profile", DetectionContext.__dataclass_fields__)

    def test_candidate_stages_are_immutable_and_separate(self) -> None:
        geometry_fields = {field.name for field in fields(SequenceSolution)}
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
        self.assertTrue(SequenceSolution.__dataclass_params__.frozen)
        self.assertTrue(BuiltCandidate.__dataclass_params__.frozen)
        self.assertTrue(AssessedCandidate.__dataclass_params__.frozen)
        self.assertNotIn("status", final_fields)
        self.assertNotIn("final_review_reasons", final_fields)
        for candidate_stage_field in (
            "selection",
            "visible_sequence_span",
            "crop_envelope",
            "separator_observations",
            "separator_assignments",
            "frame_boundaries",
        ):
            self.assertNotIn(candidate_stage_field, final_fields)
        self.assertEqual(
            final_fields,
            {"decision", "finalization_plan"},
        )

    def test_decision_and_finalization_have_distinct_lifecycle_types(self) -> None:
        import x5crop.detection.decision.model as decision_model
        from x5crop.detection.decision.decision_gate import apply_decision_gate

        self.assertFalse(hasattr(decision_model, "DecisionResult"))
        self.assertFalse(hasattr(decision_model, "FinalDetection"))
        self.assertTrue(
            (PROJECT_ROOT / "x5crop/detection/final/model.py").is_file()
        )
        self.assertEqual(
            inspect.signature(apply_decision_gate).return_annotation,
            "DecisionGateAssessment",
        )
        self.assertEqual(
            inspect.signature(finalize.finalize_detection).parameters[
                "decision"
            ].annotation,
            "DecisionGateAssessment",
        )
        self.assertEqual(
            inspect.signature(finalize.finalize_detection).return_annotation,
            "FinalDetection",
        )
        self.assertEqual(
            {field.name for field in fields(FinalDetection)},
            {"decision", "finalization_plan"},
        )
        self.assertNotEqual(decision_model.DecisionGateAssessment, FinalDetection)

    def test_standard_dual_lane_and_review_only_geometry_have_distinct_types(self) -> None:
        sequence_fields = {field.name for field in fields(SequenceSolution)}
        self.assertNotIn("lane_boxes", sequence_fields)
        self.assertNotIn("lane_crop_envelopes", sequence_fields)
        self.assertTrue(hasattr(physical_model, "DualLaneSolution"))
        self.assertTrue(hasattr(physical_model, "ReviewOnlyGeometry"))
        self.assertFalse(hasattr(physical_model, "UnavailableGeometry"))

    def test_sequence_solution_rejects_incomplete_frame_structure(self) -> None:
        from dataclasses import replace
        from tools.tests.physical_gate_support import candidate_fixture

        with self.assertRaises(ValueError):
            replace(candidate_fixture().geometry, frames=())

    def test_review_only_geometry_uses_a_dedicated_assessment_path(self) -> None:
        from x5crop.detection.candidate.assessment.review_only import (
            assess_review_only_candidate,
        )
        import x5crop.detection.pipeline as pipeline

        self.assertTrue(callable(assess_review_only_candidate))
        source = inspect.getsource(pipeline.choose_detection)
        self.assertIn("assess_review_only_candidate", source)
        self.assertNotIn(
            "assess_candidate(review_only_candidate(context), context)",
            source,
        )

    def test_content_alignment_has_no_write_only_confirmation_fields(self) -> None:
        from x5crop.detection.evidence.content.preservation import (
            ContentPreservationEvidence,
        )
        from x5crop.detection.evidence.sequence_content_alignment import (
            SequenceContentAlignmentEvidence,
        )

        alignment_fields = set(
            SequenceContentAlignmentEvidence.__dataclass_fields__
        )
        self.assertIn("content_outside_sides", alignment_fields)
        for removed in (
            "content_measurement_sources",
            "confirmed_undercrop_sides",
            "unconfirmed_undercrop_sides",
            "border_tonal_fraction",
        ):
            self.assertNotIn(removed, alignment_fields)
        self.assertNotIn(
            "confirmed_visible_undercrop_sides",
            ContentPreservationEvidence.__dataclass_fields__,
        )

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
        self.assertNotIn("require_selection", FinalDetection.__dict__)

    def test_sequence_and_envelope_types_remain_canonical_through_output(self) -> None:
        output_hints = get_type_hints(OutputGeometry)
        self.assertIs(output_hints["crop_envelope"], CropEnvelope)

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

    def test_candidate_build_consumes_canonical_sequence_hypothesis(self) -> None:
        from x5crop.detection.candidate.build.sequence_candidate import (
            build_sequence_candidate,
        )

        parameters = inspect.signature(build_sequence_candidate).parameters
        self.assertIn("sequence_hypothesis", parameters)
        self.assertIn("count_hypothesis", parameters)
        self.assertIn("planning_budget_exhausted", parameters)
        for duplicated_field in (
            "count",
            "strip_mode",
            "visible_sequence_span",
            "crop_envelope",
            "sequence_hypothesis_name",
            "sequence_hypothesis_strategy",
            "sequence_provenance",
            "boundary_observations",
        ):
            self.assertNotIn(duplicated_field, parameters)

    def test_frame_sequence_plan_carries_search_budget_state(self) -> None:
        from x5crop.detection.candidate.execution.source_candidates import (
            FrameSequencePlan,
        )

        self.assertIn(
            "search_budget_exhausted",
            FrameSequencePlan.__dataclass_fields__,
        )

    def test_removed_gap_and_outer_modules_do_not_exist(self) -> None:
        for relative in (
            "x5crop/gap_methods.py",
            "x5crop/geometry/gap_search.py",
            "x5crop/geometry/model_gaps.py",
            "x5crop/geometry/separator_width_profile.py",
            "x5crop/detection/physical/outer",
            "x5crop/detection/candidate/build/separator_sources.py",
        ):
            self.assertFalse((PROJECT_ROOT / relative).exists(), relative)

    def test_output_surfaces_require_final_detection(self) -> None:
        functions = (
            debug_status_parts,
            copy_for_review_if_needed,
            write_crops_if_allowed,
            result_from_detection,
            report_record_for_final_detection,
        )
        for function in functions:
            with self.subTest(function=function.__name__):
                annotation = inspect.signature(function).parameters["detection"].annotation
                self.assertEqual(annotation, "FinalDetection")

    def test_final_detection_owns_one_typed_finalization_plan(self) -> None:
        from x5crop.detection.final.model import FinalizationPlan

        self.assertEqual(
            {field.name for field in fields(FinalDetection)},
            {"decision", "finalization_plan"},
        )
        self.assertIsInstance(FinalDetection.output_geometry, property)
        self.assertEqual(
            {field.name for field in fields(FinalizationPlan)},
            {
                "layout",
                "image_width",
                "image_height",
                "decision_geometry",
                "frame_bleed_plan",
            },
        )

    def test_export_surfaces_preserve_canonical_array_and_frame_types(self) -> None:
        from x5crop.export.crops import write_crops

        action_hints = get_type_hints(write_crops_if_allowed)
        crop_hints = get_type_hints(write_crops)
        self.assertIs(action_hints["arr"], np.ndarray)
        self.assertIs(action_hints["source_arr"], np.ndarray)
        self.assertEqual(crop_hints["frames"], tuple[Box, ...])

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
