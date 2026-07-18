from __future__ import annotations

from dataclasses import fields, replace
from enum import Enum
from typing import get_type_hints
import unittest

from x5crop.detection.candidate.assessment.candidate_gate import candidate_gate_assessment
from x5crop.detection.candidate.assessment.model import (
    SequenceProofPath,
    CandidateGateInput,
    sequence_proof_state,
)
from x5crop.domain import EvidenceState
from x5crop.detection.gate_checks import GateCheck, GateRequirement, GateStage


def _path(code: str, state: EvidenceState) -> SequenceProofPath:
    return SequenceProofPath(code, state, ("synthetic",))


def _gate(
    *,
    frame_slot_topology: EvidenceState = EvidenceState.SUPPORTED,
    content_preservation: EvidenceState = EvidenceState.SUPPORTED,
    frame_dimensions: EvidenceState = EvidenceState.SUPPORTED,
    evidence_independence: EvidenceState = EvidenceState.SUPPORTED,
    proof_paths: tuple[SequenceProofPath, ...] | None = None,
    diagnostics: tuple[str, ...] = (),
):
    return candidate_gate_assessment(
        CandidateGateInput(
            frame_slot_topology=frame_slot_topology,
            content_preservation=content_preservation,
            frame_dimensions=frame_dimensions,
            evidence_independence=evidence_independence,
            proof_paths=proof_paths
            or (
                _path("separator_sequence_led", EvidenceState.SUPPORTED),
                _path("dimension_sequence_led", EvidenceState.UNAVAILABLE),
                _path("partial_occupancy_led", EvidenceState.NOT_APPLICABLE),
            ),
            diagnostics=diagnostics,
        )
    )


class CandidateLifecycleGateContractTest(unittest.TestCase):
    def test_gate_stage_is_a_typed_authority(self) -> None:
        annotation = get_type_hints(GateCheck)["stage"]
        self.assertTrue(
            isinstance(annotation, type) and issubclass(annotation, Enum)
        )

    def test_gate_check_has_no_unused_consequence_dimension(self) -> None:
        self.assertEqual(
            {field.name for field in fields(GateCheck)},
            {
                "code",
                "stage",
                "state",
                "requirement",
                "final_review_reason",
            },
        )

    def test_gate_requirement_distinguishes_required_support_from_safety(self) -> None:
        required = GateCheck(
            "sequence_proof",
            GateStage.CANDIDATE,
            EvidenceState.UNAVAILABLE,
            GateRequirement.SUPPORTED_REQUIRED,
        )
        safety = GateCheck(
            "content_preservation",
            GateStage.CANDIDATE,
            EvidenceState.UNAVAILABLE,
            GateRequirement.NOT_CONTRADICTED,
        )

        self.assertTrue(required.blocks)
        self.assertFalse(safety.blocks)

    def test_gate_check_rejects_cross_stage_reason_ownership(self) -> None:
        invalid_factories = (
            lambda: GateCheck("", GateStage.CANDIDATE, EvidenceState.SUPPORTED),
            lambda: GateCheck(
                "content_preservation",
                GateStage.CANDIDATE,
                EvidenceState.CONTRADICTED,
                "content_preservation_unresolved",
            ),
            lambda: GateCheck(
                "content_preservation",
                "unknown",
                EvidenceState.CONTRADICTED,
            ),
            lambda: GateCheck(
                "decision_check",
                GateStage.DECISION,
                EvidenceState.CONTRADICTED,
            ),
        )
        for factory in invalid_factories:
            with self.subTest(factory=factory), self.assertRaises(
                (TypeError, ValueError)
            ):
                factory()

    def test_candidate_gate_rejects_incomplete_check_ownership(self) -> None:
        gate = _gate()
        with self.assertRaises(ValueError):
            replace(gate, checks=gate.checks[:-1])

    def test_sequence_check_must_match_proof_paths(self) -> None:
        gate = _gate()
        checks = tuple(
            replace(check, state=EvidenceState.CONTRADICTED)
            if check.code == "sequence_proof"
            else check
            for check in gate.checks
        )
        with self.assertRaises(ValueError):
            replace(gate, checks=checks)

    def test_candidate_gate_has_only_physical_checks(self) -> None:
        self.assertEqual(
            tuple(check.code for check in _gate().checks),
            (
                "frame_slot_topology",
                "content_preservation",
                "frame_dimension_consistency",
                "evidence_independence",
                "sequence_proof",
            ),
        )

    def test_each_physical_contradiction_blocks_its_own_check(self) -> None:
        cases = (
            ("frame_slot_topology", "frame_slot_topology"),
            ("content_preservation", "content_preservation"),
            ("frame_dimensions", "frame_dimension_consistency"),
            ("evidence_independence", "evidence_independence"),
        )
        for argument, expected in cases:
            with self.subTest(argument=argument):
                gate = _gate(**{argument: EvidenceState.CONTRADICTED})
                self.assertFalse(gate.passed)
                self.assertIn(expected, gate.failed_checks)

    def test_unavailable_measurement_is_not_a_contradiction(self) -> None:
        gate = _gate(
            frame_dimensions=EvidenceState.UNAVAILABLE,
            content_preservation=EvidenceState.UNAVAILABLE,
        )
        self.assertTrue(gate.passed)

    def test_one_supported_sequence_path_is_sufficient(self) -> None:
        gate = _gate(
            proof_paths=(
                _path("separator_sequence_led", EvidenceState.UNAVAILABLE),
                _path("dimension_sequence_led", EvidenceState.SUPPORTED),
                _path("partial_occupancy_led", EvidenceState.NOT_APPLICABLE),
            )
        )
        self.assertTrue(gate.passed)

    def test_no_supported_sequence_path_blocks_once(self) -> None:
        proof_paths = (
            _path("separator_sequence_led", EvidenceState.UNAVAILABLE),
            _path("dimension_sequence_led", EvidenceState.UNAVAILABLE),
            _path("partial_occupancy_led", EvidenceState.NOT_APPLICABLE),
        )
        gate = _gate(proof_paths=proof_paths)

        self.assertEqual(sequence_proof_state(proof_paths), EvidenceState.UNAVAILABLE)
        self.assertEqual(gate.failed_checks, ("sequence_proof",))

    def test_unknown_sequence_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "sequence proof path"):
            _gate(proof_paths=(_path("unknown", EvidenceState.SUPPORTED),))

    def test_standard_sequence_proof_set_must_be_complete(self) -> None:
        with self.assertRaises(ValueError):
            _gate(
                proof_paths=(
                    _path("separator_sequence_led", EvidenceState.SUPPORTED),
                )
            )

    def test_diagnostics_never_become_blockers(self) -> None:
        gate = _gate(
            diagnostics=(
                "separator_width_varies",
                "sequence_span_overcontains_holder_area",
            )
        )
        self.assertTrue(gate.passed)
        self.assertEqual(
            gate.diagnostics,
            ("separator_width_varies", "sequence_span_overcontains_holder_area"),
        )


if __name__ == "__main__":
    unittest.main()
