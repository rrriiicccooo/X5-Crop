from __future__ import annotations

import unittest

from tools.tests.physical_gate_support import candidate_fixture, decide_candidate
from x5crop.constants import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    FINAL_REASON_OUTPUT_BLEED_UNRESOLVED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)
from x5crop.domain import EvidenceState


class DecisionOwnershipGateContractTest(unittest.TestCase):
    def test_confidence_never_blocks_automatic_processing(self) -> None:
        decided = decide_candidate(candidate_fixture(confidence=0.01))
        self.assertEqual(decided.status, "approved_auto")
        self.assertEqual(decided.final_review_reasons, ())

    def test_candidate_failure_projects_specific_reason(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                failed_candidate_check="frame_topology_integrity",
            )
        )
        self.assertEqual(
            decided.final_review_reasons,
            (FINAL_REASON_FRAME_TOPOLOGY_INVALID,),
        )

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
            for check in decided.decision_gate.checks
            if check.final_review_reason
            == FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED
        )
        self.assertEqual(len(content_checks), 1)

    def test_only_substantive_geometry_disagreement_blocks_selection(self) -> None:
        decided = decide_candidate(geometry_disagreement=True)
        self.assertIn(
            FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
            decided.final_review_reasons,
        )

    def test_feasible_overlap_protection_does_not_block(self) -> None:
        self.assertEqual(
            decide_candidate(overlap_bleed_feasible=True).status,
            "approved_auto",
        )

    def test_unresolved_overlap_protection_blocks(self) -> None:
        decided = decide_candidate(overlap_bleed_feasible=False)
        self.assertIn(
            FINAL_REASON_OUTPUT_BLEED_UNRESOLVED,
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
            candidate_fixture(automatic_processing_supported=False)
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
