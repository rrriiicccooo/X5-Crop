from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
import inspect
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
from x5crop.detection.physical.model import (
    FrameSequenceSolution,
    FrameBoundarySource,
    ResolvedFrameBoundary,
    SequenceResiduals,
)
import x5crop.detection.physical.model as physical_model
from x5crop.detection.decision.model import DecisionGateAssessment
from x5crop.detection.final.model import FinalDetection
from x5crop.detection.context import (
    DetectionContext,
    DetectionExecutionStatistics,
    DetectionRequest,
)
from x5crop.detection.candidate.assessment.model import (
    CandidateGateAssessment,
)
from x5crop.detection.final import finalize
from x5crop.detection.pipeline import choose_detection
from x5crop.export.actions import copy_for_review_if_needed, write_crops_if_allowed
from x5crop.report.result_builder import result_from_detection
from x5crop.report.record import report_record_for_final_detection
from x5crop.domain import Box, FrameCropEnvelope
from x5crop.output.model import OutputGeometry
from tools.tests.support.physical_gates import (
    detection_workspace_fixture,
    selection_fixture,
)
from x5crop.detection.evidence.scan_canvas import (
    CanvasPixelScale,
    ScanCanvasOutcome,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DetectionStageTypeContractTests(unittest.TestCase):
    def test_sequence_residuals_do_not_duplicate_conservation_evidence(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(SequenceResiduals)),
            ("dimension", "boundary_uncertainty"),
        )

    def test_detection_request_and_context_reject_identity_drift(self) -> None:
        from x5crop.configuration.registry import get_detection_configuration

        with self.assertRaises(ValueError):
            DetectionRequest("diagonal", "full", None)
        with self.assertRaises(ValueError):
            DetectionRequest("horizontal", "unknown", None)
        with self.assertRaises(ValueError):
            DetectionRequest("horizontal", "partial", 0)

        full = get_detection_configuration("135", "full")
        dual = get_detection_configuration("135-dual", "full")
        lane = get_detection_configuration("135", "full")
        horizontal_workspace = detection_workspace_fixture()
        vertical_workspace = detection_workspace_fixture()
        vertical_workspace.measurement_cache.layout = "horizontal"
        invalid_contexts = (
            lambda: DetectionContext(
                DetectionRequest("horizontal", "partial", None),
                full,
                None,
                horizontal_workspace,
                DetectionExecutionStatistics(),
            ),
            lambda: DetectionContext(
                DetectionRequest("vertical", "full", None),
                full,
                None,
                vertical_workspace,
                DetectionExecutionStatistics(),
            ),
            lambda: DetectionContext(
                DetectionRequest("horizontal", "full", None),
                full,
                lane,
                horizontal_workspace,
                DetectionExecutionStatistics(),
            ),
            lambda: DetectionContext(
                DetectionRequest("horizontal", "full", None),
                dual,
                None,
                horizontal_workspace,
                DetectionExecutionStatistics(),
            ),
        )
        for factory in invalid_contexts:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_detection_context_contains_no_tiff_io_profile(self) -> None:
        self.assertNotIn("image_profile", DetectionContext.__dataclass_fields__)

    def test_resolution_metadata_stays_outside_detection_context(self) -> None:
        context_fields = DetectionContext.__dataclass_fields__
        self.assertNotIn("scan_calibration", context_fields)
        self.assertNotIn("resolution_metadata", context_fields)

    def test_physical_authority_discriminators_are_typed(self) -> None:
        from x5crop.detection.candidate.plan.model import (
            CountHypothesis,
            CountHypothesisSource,
        )
        from x5crop.domain import (
            MeasurementIdentity,
            MeasurementProvenance,
            ObservationId,
        )
        self.assertIs(
            get_type_hints(CountHypothesis)["source"],
            CountHypothesisSource,
        )
        self.assertIs(
            get_type_hints(ResolvedFrameBoundary)["source"],
            FrameBoundarySource,
        )
        self.assertIs(
            get_type_hints(CanvasPixelScale)["source_long_axis"],
            str,
        )
        self.assertTrue(issubclass(ScanCanvasOutcome, str))
        provenance_hints = get_type_hints(MeasurementProvenance)
        self.assertIs(provenance_hints["root_measurement"], MeasurementIdentity)
        self.assertIs(provenance_hints["observation_id"], ObservationId)
        self.assertEqual(
            provenance_hints["dependencies"],
            tuple[MeasurementIdentity, ...],
        )
        self.assertEqual(
            provenance_hints["boundary_anchors"],
            tuple[ObservationId, ...],
        )

    def test_measurement_provenance_rejects_cyclic_root_dependency(self) -> None:
        from x5crop.domain import (
            MeasurementIdentity,
            MeasurementProvenance,
            ObservationId,
        )

        with self.assertRaises(ValueError):
            MeasurementProvenance(
                root_measurement=MeasurementIdentity.FRAME_GEOMETRY,
                observation_id=ObservationId("cyclic_geometry_provenance"),
                dependencies=(MeasurementIdentity.FRAME_GEOMETRY,),
                description="invalid cyclic geometry provenance",
            )

    def test_candidate_stages_are_immutable_and_separate(self) -> None:
        geometry_fields = {field.name for field in fields(FrameSequenceSolution)}
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
        self.assertIn(
            "frame_coverage",
            CandidateEvidence.__dataclass_fields__,
        )
        self.assertNotIn("frame_topology", CandidateEvidence.__dataclass_fields__)
        self.assertTrue(FrameSequenceSolution.__dataclass_params__.frozen)
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
            {
                "decision",
                "frame_bleed_plan",
                "finalization_plan",
                "output_geometry",
            },
        )

    def test_typed_results_do_not_store_report_only_identity_copies(self) -> None:
        from x5crop.detection.evidence.content.frame_content import (
            FrameContentEvidence,
        )
        from x5crop.detection.physical.model import (
            DualLaneFrameSolution,
            ReviewOnlyContainment,
        )
        for model in (
            FrameSequenceSolution,
            DualLaneFrameSolution,
            ReviewOnlyContainment,
        ):
            model_fields = set(model.__dataclass_fields__)
            self.assertNotIn("name", model_fields)
            self.assertNotIn("strategy", model_fields)
            self.assertNotIn("sequence_hypothesis_name", model_fields)
            self.assertNotIn("sequence_hypothesis_strategy", model_fields)
        self.assertNotIn("composite", FrameContentEvidence.__dataclass_fields__)

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
            {
                "decision",
                "frame_bleed_plan",
                "finalization_plan",
                "output_geometry",
            },
        )
        self.assertNotEqual(decision_model.DecisionGateAssessment, FinalDetection)

    def test_standard_dual_lane_and_review_only_geometry_have_distinct_types(self) -> None:
        sequence_fields = {field.name for field in fields(FrameSequenceSolution)}
        self.assertNotIn("lane_boxes", sequence_fields)
        self.assertNotIn("lane_crop_envelopes", sequence_fields)
        self.assertTrue(hasattr(physical_model, "DualLaneFrameSolution"))
        self.assertTrue(hasattr(physical_model, "ReviewOnlyContainment"))
        self.assertFalse(hasattr(physical_model, "UnavailableGeometry"))

    def test_sequence_solution_rejects_incomplete_frame_structure(self) -> None:
        from dataclasses import replace
        from tools.tests.support.physical_gates import candidate_fixture

        with self.assertRaises(ValueError):
            replace(candidate_fixture().geometry, frame_slots=())

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

    def test_external_content_preservation_has_only_measured_fields(self) -> None:
        from x5crop.detection.evidence.content.external_frame_boundaries import (
            ExternalFramePreservationEvidence,
        )

        preservation_fields = set(
            ExternalFramePreservationEvidence.__dataclass_fields__
        )
        self.assertIn("frame_count", preservation_fields)
        self.assertIn("observations", preservation_fields)
        self.assertIn("workspace_extent", preservation_fields)
        self.assertIn("frame_sequence_envelope", preservation_fields)
        for removed in (
            "content_span",
            "content_outside_sides",
            "overcontains_long_axis",
            "overcontains_short_axis",
        ):
            self.assertNotIn(removed, preservation_fields)

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
        self.assertEqual(
            output_hints["frame_crop_envelopes"],
            tuple[FrameCropEnvelope, ...],
        )

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

    def test_candidate_build_consumes_canonical_frame_sequence_search_inputs(self) -> None:
        from x5crop.detection.candidate.build.sequence_candidate import (
            build_sequence_candidate,
        )

        parameters = inspect.signature(build_sequence_candidate).parameters
        self.assertIn("search_scope", parameters)
        self.assertIn("dimensions", parameters)
        self.assertIn("count_hypothesis", parameters)
        self.assertIn("solver_parameters", parameters)
        for duplicated_field in (
            "count",
            "strip_mode",
            "frames",
            "outer",
            "gaps",
        ):
            self.assertNotIn(duplicated_field, parameters)

    def test_candidate_build_outcome_carries_solver_budget_state(self) -> None:
        from x5crop.detection.candidate.build.sequence_candidate import (
            SequenceCandidateBuildOutcome,
        )

        self.assertEqual(
            set(SequenceCandidateBuildOutcome.__dataclass_fields__),
            {
                "candidate",
                "physical_search",
                "assignment_evaluations",
            },
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
            {
                "decision",
                "frame_bleed_plan",
                "finalization_plan",
                "output_geometry",
            },
        )
        self.assertEqual(
            {field.name for field in fields(FinalizationPlan)},
            {
                "layout",
                "image_width",
                "image_height",
                "base_geometry",
            },
        )

    def test_unresolved_geometry_has_no_finalization_plan(self) -> None:
        from x5crop.detection.final.finalize import (
            finalization_plan_for_selection,
        )
        from x5crop.domain import WorkspaceExtent

        selection = selection_fixture()
        unresolved = replace(
            selection,
            geometry_resolution=replace(
                selection.geometry_resolution,
                count_resolved=False,
            ),
        )
        self.assertIsNone(
            finalization_plan_for_selection(
                unresolved,
                workspace_extent=WorkspaceExtent(310, 100),
            )
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
