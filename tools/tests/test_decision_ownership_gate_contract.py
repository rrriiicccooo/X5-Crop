from __future__ import annotations

from copy import deepcopy
import unittest

from tools.tests.physical_gate_support import candidate_fixture, decide_candidate
from x5crop.constants import (
    FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
    FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
    FINAL_REASON_FRAME_TOPOLOGY_INVALID,
    FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
    FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
    FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
)


class DecisionOwnershipGateContractTest(unittest.TestCase):
    def test_decision_requires_a_complete_candidate_gate_result(self) -> None:
        candidate = candidate_fixture()
        del candidate.detail["candidate_assessment"]["candidate_gate"]

        with self.assertRaisesRegex(ValueError, "candidate gate"):
            decide_candidate(candidate)

    def test_confidence_never_blocks_automatic_processing(self) -> None:
        decided = decide_candidate(candidate_fixture(confidence=0.01))

        self.assertEqual(decided.status, "approved_auto")
        self.assertEqual(decided.final_review_reasons, [])

    def test_candidate_failure_projects_the_specific_physical_reason(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                candidate_gate_passed=False,
                failed_check="frame_topology_integrity",
            )
        )

        self.assertEqual(decided.status, "needs_review")
        self.assertEqual(
            decided.final_review_reasons,
            [FINAL_REASON_FRAME_TOPOLOGY_INVALID],
        )
        self.assertNotIn("candidate_gate_failed", decided.final_review_reasons)

    def test_content_only_candidate_has_one_boundary_reason(self) -> None:
        decided = decide_candidate(
            candidate_fixture(
                candidate_gate_passed=False,
                failed_check="boundary_proof",
            )
        )

        self.assertEqual(
            decided.final_review_reasons,
            [FINAL_REASON_BOUNDARY_EVIDENCE_INSUFFICIENT],
        )

    def test_global_bbox_conflict_is_diagnostic_without_direct_undercrop(self) -> None:
        decided = decide_candidate(
            content_detail={
                "used": True,
                "frame_content_support_available": True,
            },
            outer_alignment={"used": True, "ok": False},
        )

        self.assertEqual(decided.status, "approved_auto")
        preservation = decided.detail["evidence_summary"]["content_preservation"]
        self.assertEqual(preservation["state"], "unavailable")

    def test_confirmed_content_undercrop_blocks(self) -> None:
        decided = decide_candidate(
            content_detail={"used": True, "content_boundary_contact": True},
            outer_alignment={"used": True, "ok": False},
        )

        self.assertEqual(decided.status, "needs_review")
        self.assertIn(
            FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
            decided.final_review_reasons,
        )
        self.assertEqual(
            decided.detail["evidence_summary"]["content"]["state"],
            "contradicted",
        )

    def test_frame_boundary_contact_does_not_override_global_alignment_support(self) -> None:
        decided = decide_candidate(
            content_detail={"used": True, "content_boundary_contact": True},
            outer_alignment={"used": True, "ok": True},
        )

        self.assertEqual(decided.status, "approved_auto")
        self.assertEqual(decided.final_review_reasons, [])

    def test_frame_boundary_contact_and_global_mismatch_confirm_undercrop(self) -> None:
        decided = decide_candidate(
            content_detail={"used": True, "content_boundary_contact": True},
            outer_alignment={"used": True, "ok": False},
        )

        self.assertIn(
            FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED,
            decided.final_review_reasons,
        )

    def test_complete_underfilled_state_does_not_suppress_confirmed_undercrop(self) -> None:
        candidate = candidate_fixture()
        candidate.strip_mode = "partial"
        candidate.detail["candidate_assessment"]["partial_edge_safety"] = {
            "state": "supported",
            "complete_underfilled_strip": True,
            "preservation_failures": [],
        }
        decided = decide_candidate(
            candidate,
            content_detail={"used": True, "content_boundary_contact": True},
            outer_alignment={
                "used": True,
                "ok": False,
                "confirmed_undercrop": True,
            },
        )

        self.assertEqual(decided.status, "needs_review")
        self.assertEqual(
            decided.final_review_reasons,
            [FINAL_REASON_CONTENT_PRESERVATION_UNRESOLVED],
        )

    def test_only_substantive_geometry_disagreement_blocks_selection(self) -> None:
        decided = decide_candidate(
            candidate_fixture(geometry_disagreement=True),
        )

        self.assertIn(
            FINAL_REASON_SELECTION_GEOMETRY_DISAGREEMENT,
            decided.final_review_reasons,
        )

    def test_feasible_overlap_protection_does_not_block(self) -> None:
        decided = decide_candidate(output_protection_feasible=True)
        self.assertEqual(decided.status, "approved_auto")

    def test_unresolved_overlap_protection_blocks(self) -> None:
        decided = decide_candidate(output_protection_feasible=False)
        self.assertIn(
            FINAL_REASON_OUTPUT_PROTECTION_UNRESOLVED,
            decided.final_review_reasons,
        )

    def test_transform_geometry_uncertainty_blocks(self) -> None:
        decided = decide_candidate(
            deskew_detail={"skipped": "angle_out_of_range"},
        )
        self.assertIn(
            FINAL_REASON_TRANSFORM_GEOMETRY_UNCERTAIN,
            decided.final_review_reasons,
        )

    def test_explicit_review_only_mode_blocks_automatic_processing(self) -> None:
        decided = decide_candidate(
            candidate_fixture(automatic_processing_supported=False),
        )
        self.assertIn(
            FINAL_REASON_AUTOMATIC_PROCESSING_NOT_SUPPORTED,
            decided.final_review_reasons,
        )

    def test_decision_conversion_does_not_mutate_candidate(self) -> None:
        candidate = candidate_fixture()
        before = deepcopy(candidate)

        decided = decide_candidate(candidate)

        self.assertEqual(candidate, before)
        self.assertIsNot(decided.detail, candidate.detail)


if __name__ == "__main__":
    unittest.main()
