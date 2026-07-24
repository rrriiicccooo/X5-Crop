from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.support.physical_gates import (
    candidate_fixture,
    candidate_gate_fixture,
    decide_candidate,
    detection_workspace_fixture,
    final_detection_fixture,
    frame_bleed_fixture,
    review_only_candidate_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from x5crop.configuration.registry import get_detection_configuration
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.vocabulary import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_COUNT_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_SEQUENCE_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    FINAL_REASON_SCAN_CANVAS_PROFILE_UNRESOLVED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)
from x5crop.domain import (
    EvidenceState,
    PhysicalSearchFact,
    PhysicalSearchOutcome,
)
from x5crop.detection.decision.model import DecisionGateAssessment
from x5crop.detection.evidence.scan_canvas import observe_scan_canvas


class DecisionOwnershipGateContractTest(unittest.TestCase):
    def test_decision_gate_rejects_unowned_final_reason(self) -> None:
        gate = decide_candidate()
        forged = tuple(
            replace(check, final_review_reason="unowned_final_reason")
            if check.code == "count_resolution"
            else check
            for check in gate.checks
        )
        with self.assertRaises(ValueError):
            DecisionGateAssessment(forged)

    def test_decision_gate_rejects_candidate_stage_checks(self) -> None:
        with self.assertRaises(ValueError):
            DecisionGateAssessment(candidate_gate_fixture().checks)

    def test_final_detection_rejects_inconsistent_final_identity(self) -> None:
        detection = final_detection_fixture()
        invalid_factories = (
            lambda: replace(
                detection,
                finalization_plan=replace(
                    detection.finalization_plan,
                    image_width=0,
                ),
            ),
            lambda: replace(
                detection,
                frame_bleed_plan=replace(
                    detection.frame_bleed_plan,
                    frame_sides=(),
                ),
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_decision_has_no_scalar_confidence_input(self) -> None:
        decided = decide_candidate(candidate_fixture())
        self.assertFalse(hasattr(decided, "confidence"))
        self.assertEqual(decided.status, "approved_auto")
        self.assertEqual(decided.final_review_reasons, ())

    def test_missing_sequence_proof_has_one_reason(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                failed_candidate_check="sequence_proof",
            )
        )
        self.assertEqual(
            decided.final_review_reasons,
            (FINAL_REASON_SEQUENCE_EVIDENCE_INSUFFICIENT,),
        )

    def test_decision_preserves_unavailable_required_candidate_evidence(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                failed_candidate_check="sequence_proof",
            )
        )
        check = next(
            item
            for item in decided.checks
            if item.code == "candidate_sequence_proof"
        )
        self.assertEqual(check.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(check.requirement.value, "supported_required")
        self.assertTrue(check.blocks)

    def test_confirmed_undercrop_blocks(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                failed_candidate_check="content_preservation",
                content_preservation=EvidenceState.CONTRADICTED,
            )
        )
        self.assertIn(
            FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
            decided.final_review_reasons,
        )

    def test_candidate_content_preservation_is_judged_once(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                failed_candidate_check="content_preservation",
                content_preservation=EvidenceState.CONTRADICTED,
            )
        )
        content_checks = tuple(
            check
            for check in decided.checks
            if check.final_review_reason
            == FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED
        )
        self.assertEqual(len(content_checks), 1)
        self.assertEqual(
            decided.final_review_reasons,
            (FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,),
        )

    def test_only_substantive_geometry_disagreement_blocks_selection(self) -> None:
        decided = decide_candidate(geometry_disagreement=True)
        self.assertIn(
            FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
            decided.final_review_reasons,
        )

    def test_decision_consumes_complete_geometry_resolution(self) -> None:
        base = selection_fixture()
        unresolved = (
            replace(
                base.geometry_resolution,
                assignment_consensus_resolved=False,
            ),
            replace(
                base.geometry_resolution,
                physical_search=PhysicalSearchOutcome(
                    (
                        PhysicalSearchFact.SOLUTION_FOUND,
                        PhysicalSearchFact.EXECUTION_BUDGET_EXHAUSTED,
                    ),
                ),
            ),
        )
        for resolution in unresolved:
            with self.subTest(reasons=resolution.reasons):
                decided = apply_decision_gate(
                    replace(base, geometry_resolution=resolution),
                    frame_bleed_fixture(),
                    detection_workspace_fixture().scan_canvas_evidence,
                    transform_geometry_fixture(),
                    automatic_processing_eligibility=EvidenceState.SUPPORTED,
                )
                self.assertEqual(decided.status, "needs_review")
                self.assertIn(
                    FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
                    decided.final_review_reasons,
                )

    def test_feasible_overlap_protection_does_not_block(self) -> None:
        self.assertEqual(
            decide_candidate(output_protection_feasible=True).status,
            "approved_auto",
        )

    def test_unresolved_overlap_protection_blocks(self) -> None:
        decided = decide_candidate(output_protection_feasible=False)
        self.assertIn(
            FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
            decided.final_review_reasons,
        )

    def test_transform_geometry_uncertainty_blocks(self) -> None:
        decided = decide_candidate(transform_state=EvidenceState.CONTRADICTED)
        self.assertIn(
            FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
            decided.final_review_reasons,
        )

    def test_transform_uncertainty_remains_blocking_before_count_resolution(
        self,
    ) -> None:
        selection = selection_fixture()
        selection = replace(
            selection,
            geometry_resolution=replace(
                selection.geometry_resolution,
                larger_count_search_complete=False,
            ),
        )

        decided = apply_decision_gate(
            selection,
            frame_bleed_fixture(),
            detection_workspace_fixture().scan_canvas_evidence,
            transform_geometry_fixture(EvidenceState.UNAVAILABLE),
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        )
        check = next(
            item
            for item in decided.checks
            if item.code == "transform_geometry_integrity"
        )

        self.assertEqual(check.state, EvidenceState.UNAVAILABLE)
        self.assertEqual(
            check.requirement.value,
            "supported_required",
        )
        self.assertTrue(check.blocks)
        self.assertIn(
            FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
            decided.final_review_reasons,
        )

    def test_unresolved_known_scan_canvas_blocks_with_owned_reason(self) -> None:
        canvas = observe_scan_canvas(
            1_000,
            1_000,
            "horizontal",
            get_detection_configuration("135", "full").scan_canvas,
        )
        decided = apply_decision_gate(
            selection_fixture(),
            frame_bleed_fixture(),
            canvas,
            transform_geometry_fixture(),
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        )

        self.assertEqual(decided.status, "needs_review")
        self.assertIn(
            FINAL_REASON_SCAN_CANVAS_PROFILE_UNRESOLVED,
            decided.final_review_reasons,
        )

    def test_review_only_mode_blocks_automatic_processing(self) -> None:
        decided = decide_candidate(
            review_only_candidate_fixture(),
            automatic_processing_eligible=False,
        )
        self.assertIn(
            FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
            decided.final_review_reasons,
        )

    def test_standard_mode_unresolved_geometry_is_not_review_only(self) -> None:
        selection = selection_fixture(review_only_candidate_fixture())
        decided = apply_decision_gate(
            selection,
            frame_bleed_fixture(),
            detection_workspace_fixture().scan_canvas_evidence,
            transform_geometry_fixture(),
            automatic_processing_eligibility=EvidenceState.SUPPORTED,
        )
        self.assertIn(
            FINAL_REASON_COUNT_RESOLUTION_UNAVAILABLE,
            decided.final_review_reasons,
        )
        self.assertNotIn(
            FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
            decided.final_review_reasons,
        )

    def test_decision_does_not_mutate_selected_candidate(self) -> None:
        candidate = candidate_fixture()
        before = repr(candidate)
        decide_candidate(candidate)
        self.assertEqual(repr(candidate), before)


if __name__ == "__main__":
    unittest.main()
