from __future__ import annotations

from dataclasses import replace
import unittest

from tools.tests.physical_gate_support import (
    candidate_fixture,
    candidate_gate_fixture,
    decide_candidate,
    final_detection_fixture,
    frame_bleed_fixture,
    review_only_candidate_fixture,
    selection_fixture,
    transform_geometry_fixture,
)
from x5crop.detection.decision.decision_gate import apply_decision_gate
from x5crop.detection.decision.vocabulary import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_GEOMETRY_RESOLUTION_UNAVAILABLE,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)
from x5crop.domain import EvidenceState
from x5crop.detection.decision.model import DecisionGateAssessment


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

    def test_missing_boundary_proof_has_one_reason(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                failed_candidate_check="boundary_proof",
            )
        )
        self.assertEqual(
            decided.final_review_reasons,
            (FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,),
        )

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
                assignment_geometry_resolved=False,
            ),
            replace(
                base.geometry_resolution,
                search_budget_exhausted=True,
            ),
        )
        for resolution in unresolved:
            with self.subTest(reasons=resolution.reasons):
                decided = apply_decision_gate(
                    replace(base, geometry_resolution=resolution),
                    frame_bleed_fixture(),
                    transform_geometry_fixture(),
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

    def test_review_only_mode_blocks_automatic_processing(self) -> None:
        decided = decide_candidate(
            review_only_candidate_fixture()
        )
        self.assertIn(
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
