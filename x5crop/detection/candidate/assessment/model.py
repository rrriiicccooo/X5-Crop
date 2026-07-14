from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState

from ...gate_checks import GateCheck, GateStage


BOUNDARY_PROOF_PATH_CODES = frozenset(
    {
        "separator_sequence_led",
        "geometry_led",
        "partial_occupancy_led",
        "mode_composition",
    }
)
STANDARD_BOUNDARY_PROOF_PATH_CODES = (
    "separator_sequence_led",
    "geometry_led",
    "partial_occupancy_led",
)
DUAL_LANE_BOUNDARY_PROOF_PATH_CODES = ("mode_composition",)
CANDIDATE_GATE_CHECK_CODES = (
    "content_preservation",
    "photo_geometry_consistency",
    "frame_sequence_conservation",
    "evidence_independence",
    "boundary_proof",
)


@dataclass(frozen=True)
class BoundaryProofPath:
    code: str
    state: EvidenceState
    supporting_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.code not in BOUNDARY_PROOF_PATH_CODES:
            raise ValueError(f"unowned boundary proof path: {self.code}")
        if any(not item for item in self.supporting_evidence) or len(
            set(self.supporting_evidence)
        ) != len(self.supporting_evidence):
            raise ValueError("boundary proof evidence names must be non-empty and unique")


def boundary_proof_state(
    proof_paths: tuple[BoundaryProofPath, ...],
) -> EvidenceState:
    if not proof_paths:
        raise ValueError("candidate gate requires boundary proof paths")
    if any(path.state == EvidenceState.SUPPORTED for path in proof_paths):
        return EvidenceState.SUPPORTED
    if all(path.state == EvidenceState.NOT_APPLICABLE for path in proof_paths):
        return EvidenceState.NOT_APPLICABLE
    return EvidenceState.CONTRADICTED


@dataclass(frozen=True)
class CandidateGateInput:
    content_preservation: EvidenceState
    photo_geometry: EvidenceState
    sequence_conservation: EvidenceState
    evidence_independence: EvidenceState
    proof_paths: tuple[BoundaryProofPath, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateGateAssessment:
    checks: tuple[GateCheck, ...]
    proof_paths: tuple[BoundaryProofPath, ...]
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if tuple(check.code for check in self.checks) != CANDIDATE_GATE_CHECK_CODES:
            raise ValueError("candidate gate checks must be complete and ordered")
        if any(check.stage != GateStage.CANDIDATE for check in self.checks):
            raise ValueError("candidate gate can contain only candidate-stage checks")
        path_codes = tuple(path.code for path in self.proof_paths)
        if path_codes not in {
            STANDARD_BOUNDARY_PROOF_PATH_CODES,
            DUAL_LANE_BOUNDARY_PROOF_PATH_CODES,
        }:
            raise ValueError("candidate boundary proof paths must be complete and ordered")
        if any(not item for item in self.diagnostics) or len(
            set(self.diagnostics)
        ) != len(self.diagnostics):
            raise ValueError("candidate diagnostics must be non-empty and unique")
        check_by_code = {check.code: check for check in self.checks}
        if (
            check_by_code["boundary_proof"].state
            != boundary_proof_state(self.proof_paths)
        ):
            raise ValueError("boundary proof check must derive from proof paths")

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(check.code for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.failed_checks
