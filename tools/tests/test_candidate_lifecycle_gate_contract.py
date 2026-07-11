from __future__ import annotations

import unittest

from x5crop.detection.candidate.assessment.candidate_gate import (
    BoundaryProofPath,
    CandidateGateInput,
    candidate_gate_assessment,
)
from x5crop.detection.evidence.state import EvidenceState


def _path(code: str, state: EvidenceState) -> BoundaryProofPath:
    return BoundaryProofPath(code, state, ("synthetic",))


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
            frame_topology,
            content_preservation,
            photo_geometry,
            evidence_independence,
            proof_paths or (_path("separator_led", EvidenceState.SUPPORTED),),
            diagnostics,
        )
    )


class CandidateLifecycleGateContractTest(unittest.TestCase):
    def test_candidate_gate_has_only_physical_checks(self) -> None:
        self.assertEqual(
            tuple(check.code for check in _gate().checks),
            (
                "frame_topology_integrity",
                "content_preservation",
                "photo_geometry_consistency",
                "evidence_independence",
                "boundary_proof",
            ),
        )

    def test_each_physical_contradiction_blocks_its_own_check(self) -> None:
        cases = (
            ("frame_topology", "frame_topology_integrity"),
            ("content_preservation", "content_preservation"),
            ("photo_geometry", "photo_geometry_consistency"),
            ("evidence_independence", "evidence_independence"),
        )
        for argument, expected in cases:
            with self.subTest(argument=argument):
                gate = _gate(**{argument: EvidenceState.CONTRADICTED})
                self.assertFalse(gate.passed)
                self.assertIn(expected, gate.failed_checks)

    def test_unavailable_measurement_is_not_a_contradiction(self) -> None:
        gate = _gate(
            photo_geometry=EvidenceState.UNAVAILABLE,
            content_preservation=EvidenceState.UNAVAILABLE,
        )
        self.assertTrue(gate.passed)

    def test_one_supported_boundary_path_is_sufficient(self) -> None:
        gate = _gate(
            proof_paths=(
                _path("separator_led", EvidenceState.UNAVAILABLE),
                _path("geometry_led", EvidenceState.SUPPORTED),
                _path("partial_occupancy_led", EvidenceState.NOT_APPLICABLE),
            )
        )
        self.assertTrue(gate.passed)

    def test_no_supported_boundary_path_blocks_once(self) -> None:
        gate = _gate(
            proof_paths=(
                _path("separator_led", EvidenceState.UNAVAILABLE),
                _path("geometry_led", EvidenceState.UNAVAILABLE),
                _path("partial_occupancy_led", EvidenceState.NOT_APPLICABLE),
            )
        )
        self.assertEqual(gate.failed_checks, ("boundary_proof",))

    def test_unknown_boundary_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "boundary proof path"):
            _gate(proof_paths=(_path("unknown", EvidenceState.SUPPORTED),))

    def test_diagnostics_never_become_blockers(self) -> None:
        gate = _gate(
            diagnostics=(
                "separator_width_varies",
                "film_span_overcontains_holder_area",
            )
        )
        self.assertTrue(gate.passed)
        self.assertEqual(
            gate.diagnostics,
            ("film_span_overcontains_holder_area", "separator_width_varies"),
        )


if __name__ == "__main__":
    unittest.main()
