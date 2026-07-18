from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState

from ...gate_checks import GateCheck, GateStage


SEQUENCE_PROOF_PATH_CODES = frozenset(
    {
        "separator_sequence_led",
        "dimension_sequence_led",
        "partial_occupancy_led",
        "mode_composition",
    }
)
STANDARD_SEQUENCE_PROOF_PATH_CODES = (
    "separator_sequence_led",
    "dimension_sequence_led",
    "partial_occupancy_led",
)
DUAL_LANE_SEQUENCE_PROOF_PATH_CODES = ("mode_composition",)
CANDIDATE_GATE_CHECK_CODES = (
    "frame_slot_topology",
    "content_preservation",
    "frame_dimension_consistency",
    "evidence_independence",
    "sequence_proof",
)


@dataclass(frozen=True)
class SequenceProofPath:
    code: str
    state: EvidenceState
    supporting_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.code not in SEQUENCE_PROOF_PATH_CODES:
            raise ValueError(f"unowned sequence proof path: {self.code}")
        if any(not item for item in self.supporting_evidence) or len(
            set(self.supporting_evidence)
        ) != len(self.supporting_evidence):
            raise ValueError("sequence proof evidence names must be non-empty and unique")


def sequence_proof_state(
    proof_paths: tuple[SequenceProofPath, ...],
) -> EvidenceState:
    if not proof_paths:
        raise ValueError("candidate gate requires sequence proof paths")
    if any(path.state == EvidenceState.SUPPORTED for path in proof_paths):
        return EvidenceState.SUPPORTED
    applicable = tuple(
        path for path in proof_paths if path.state != EvidenceState.NOT_APPLICABLE
    )
    if not applicable:
        return EvidenceState.NOT_APPLICABLE
    if all(path.state == EvidenceState.CONTRADICTED for path in applicable):
        return EvidenceState.CONTRADICTED
    return EvidenceState.UNAVAILABLE


@dataclass(frozen=True)
class CandidateGateInput:
    frame_slot_topology: EvidenceState
    content_preservation: EvidenceState
    frame_dimensions: EvidenceState
    evidence_independence: EvidenceState
    proof_paths: tuple[SequenceProofPath, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateGateAssessment:
    checks: tuple[GateCheck, ...]
    proof_paths: tuple[SequenceProofPath, ...]
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if tuple(check.code for check in self.checks) != CANDIDATE_GATE_CHECK_CODES:
            raise ValueError("candidate gate checks must be complete and ordered")
        if any(check.stage != GateStage.CANDIDATE for check in self.checks):
            raise ValueError("candidate gate can contain only candidate-stage checks")
        path_codes = tuple(path.code for path in self.proof_paths)
        if path_codes not in {
            STANDARD_SEQUENCE_PROOF_PATH_CODES,
            DUAL_LANE_SEQUENCE_PROOF_PATH_CODES,
        }:
            raise ValueError("candidate sequence proof paths must be complete and ordered")
        if any(not item for item in self.diagnostics) or len(
            set(self.diagnostics)
        ) != len(self.diagnostics):
            raise ValueError("candidate diagnostics must be non-empty and unique")
        check_by_code = {check.code: check for check in self.checks}
        if (
            check_by_code["sequence_proof"].state
            != sequence_proof_state(self.proof_paths)
        ):
            raise ValueError("sequence proof check must derive from proof paths")

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(check.code for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.failed_checks
