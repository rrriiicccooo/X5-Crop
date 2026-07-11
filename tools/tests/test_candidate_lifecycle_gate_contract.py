from __future__ import annotations

import unittest

import numpy as np

from x5crop.detection.candidate.assessment.candidate_gate import (
    BoundaryProofPath,
    CandidateGateInput,
    candidate_gate_assessment,
)
from x5crop.detection.candidate.assessment.candidate import (
    candidate_content_preservation_state,
)
from x5crop.detection.evidence.state import EvidenceState
from x5crop.detection.evidence.content.frame_support import content_frame_support_detail
from x5crop.domain import Box
from x5crop.policies.parameters.content import ContentEvidenceParameters


def _gate(
    *,
    frame_topology: EvidenceState = EvidenceState.SUPPORTED,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
    photo_geometry: EvidenceState = EvidenceState.SUPPORTED,
    evidence_independence: EvidenceState = EvidenceState.SUPPORTED,
    proof_paths: tuple[BoundaryProofPath, ...] | None = None,
    diagnostics: tuple[str, ...] = (),
):
    return candidate_gate_assessment(
        CandidateGateInput(
            frame_topology=frame_topology,
            content_preservation=content_preservation,
            photo_geometry=photo_geometry,
            evidence_independence=evidence_independence,
            proof_paths=(
                proof_paths
                if proof_paths is not None
                else (
                    BoundaryProofPath(
                        "separator_led",
                        EvidenceState.SUPPORTED,
                    ),
                )
            ),
            diagnostics=diagnostics,
        )
    )


class CandidateLifecycleGateContractTest(unittest.TestCase):
    def test_candidate_gate_has_exact_physical_checks(self) -> None:
        assessment = _gate()
        self.assertEqual(
            [check.code for check in assessment.checks],
            [
                "frame_topology_integrity",
                "content_preservation",
                "photo_geometry_consistency",
                "evidence_independence",
                "boundary_proof",
            ],
        )

    def test_supported_independent_proof_path_passes(self) -> None:
        assessment = _gate(
            content_preservation=EvidenceState.UNAVAILABLE,
            photo_geometry=EvidenceState.UNAVAILABLE,
        )
        self.assertTrue(assessment.passed)
        self.assertEqual(assessment.failed_checks, ())

    def test_frame_topology_contradiction_blocks(self) -> None:
        assessment = _gate(frame_topology=EvidenceState.CONTRADICTED)
        self.assertFalse(assessment.passed)
        self.assertEqual(assessment.failed_checks, ("frame_topology_integrity",))

    def test_confirmed_content_undercrop_blocks(self) -> None:
        assessment = _gate(content_preservation=EvidenceState.CONTRADICTED)
        self.assertFalse(assessment.passed)
        self.assertIn("content_preservation", assessment.failed_checks)

    def test_reliable_photo_geometry_contradiction_blocks(self) -> None:
        assessment = _gate(photo_geometry=EvidenceState.CONTRADICTED)
        self.assertFalse(assessment.passed)
        self.assertIn("photo_geometry_consistency", assessment.failed_checks)

    def test_evidence_dependency_cycle_blocks(self) -> None:
        assessment = _gate(evidence_independence=EvidenceState.CONTRADICTED)
        self.assertFalse(assessment.passed)
        self.assertIn("evidence_independence", assessment.failed_checks)

    def test_all_boundary_paths_unavailable_blocks_once(self) -> None:
        assessment = _gate(
            proof_paths=(
                BoundaryProofPath("separator_led", EvidenceState.UNAVAILABLE),
                BoundaryProofPath("geometry_led", EvidenceState.UNAVAILABLE),
                BoundaryProofPath("partial_occupancy_led", EvidenceState.NOT_APPLICABLE),
            )
        )
        self.assertFalse(assessment.passed)
        self.assertEqual(assessment.failed_checks, ("boundary_proof",))

    def test_partial_occupancy_path_is_a_first_class_proof(self) -> None:
        assessment = _gate(
            proof_paths=(
                BoundaryProofPath("separator_led", EvidenceState.UNAVAILABLE),
                BoundaryProofPath("geometry_led", EvidenceState.UNAVAILABLE),
                BoundaryProofPath(
                    "partial_occupancy_led",
                    EvidenceState.SUPPORTED,
                    {"complete_underfilled_strip": True},
                ),
            )
        )
        self.assertTrue(assessment.passed)

    def test_unknown_boundary_proof_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "boundary proof path"):
            _gate(
                proof_paths=(
                    BoundaryProofPath("unowned_path", EvidenceState.SUPPORTED),
                )
            )

    def test_diagnostics_never_become_blockers(self) -> None:
        assessment = _gate(
            diagnostics=(
                "separator_width_varies",
                "outer_overcontains_holder_area",
                "low_content_measurement",
            )
        )
        self.assertTrue(assessment.passed)
        self.assertEqual(
            assessment.diagnostics,
            (
                "low_content_measurement",
                "outer_overcontains_holder_area",
                "separator_width_varies",
            ),
        )

    def test_not_applicable_is_not_a_failure(self) -> None:
        assessment = _gate(
            photo_geometry=EvidenceState.NOT_APPLICABLE,
            content_preservation=EvidenceState.NOT_APPLICABLE,
        )
        self.assertTrue(assessment.passed)

    def test_partial_preservation_failure_is_a_content_contradiction(self) -> None:
        state = candidate_content_preservation_state(
            {
                "frame_content_support_available": True,
            },
            {
                "state": "contradicted",
                "preservation_failures": ["partial_edge_content_present"],
            },
        )
        self.assertEqual(state, EvidenceState.CONTRADICTED)

        boundary_state = candidate_content_preservation_state(
            {
                "frame_content_support_available": True,
                "content_boundary_contact": True,
            },
            {"state": "not_applicable"},
        )
        self.assertEqual(boundary_state, EvidenceState.SUPPORTED)

    def test_frame_content_touching_crop_boundary_is_measured(self) -> None:
        evidence = np.zeros((100, 100), dtype=np.float32)
        evidence[:, :4] = 1.0

        detail = content_frame_support_detail(
            evidence,
            Box(0, 0, 100, 100),
            [Box(0, 0, 100, 100)],
            (100, 100),
            threshold=0.5,
            expected_aspect=1.0,
            evidence_params=ContentEvidenceParameters(),
            composite="synthetic",
        )

        self.assertTrue(detail["content_boundary_contact"])
        self.assertEqual(detail["boundary_contact_frame_indexes"], [1])
        self.assertIn("left", detail["frame_scores"][0]["boundary_contact_sides"])


if __name__ == "__main__":
    unittest.main()
