from __future__ import annotations

from x5crop.domain import EvidenceState
from ...physical.model import SequenceResiduals
from ..model import AssessedCandidate, CandidateEvidence, EvidenceQuality
from .candidate_gate import BoundaryProofPath


def evidence_quality(
    evidence: CandidateEvidence,
    proof_paths: tuple[BoundaryProofPath, ...],
    *,
    residuals: SequenceResiduals | None,
) -> EvidenceQuality:
    states = (
        ("frame_topology", evidence.frame_topology.state),
        ("frame_coverage", evidence.frame_coverage.state),
        ("frame_sequence_conservation", evidence.frame_sequence.conservation.state),
        ("separator_sequence", evidence.separator_sequence.state),
        ("frame_dimensions", evidence.frame_dimensions.state),
        ("frame_content", evidence.frame_content.state),
        ("holder_texture", evidence.holder_texture.state),
        ("content_preservation", evidence.content_preservation.state),
        ("sequence_content_alignment", evidence.sequence_content_alignment.state),
        ("holder_occupancy", evidence.holder_occupancy.state),
        ("partial_edge_safety", evidence.partial_edge_safety.state),
        ("evidence_independence", evidence.independence.state),
    )
    content_total = sum(
        max(0, int(end) - int(start))
        for start, end in evidence.frame_coverage.content_runs
    )
    uncovered = sum(
        max(0, int(end) - int(start))
        for start, end in evidence.frame_coverage.uncovered_content
    )
    return EvidenceQuality(
        supported=tuple(code for code, state in states if state == EvidenceState.SUPPORTED),
        contradicted=tuple(code for code, state in states if state == EvidenceState.CONTRADICTED),
        unavailable=tuple(code for code, state in states if state == EvidenceState.UNAVAILABLE),
        not_applicable=tuple(code for code, state in states if state == EvidenceState.NOT_APPLICABLE),
        covered_content_px=max(0, content_total - uncovered),
        uncovered_content_px=uncovered,
        supported_proof_paths=tuple(
            path.code for path in proof_paths if path.state == EvidenceState.SUPPORTED
        ),
        physical_residuals=residuals,
    )


def quality_for_candidate(candidate: AssessedCandidate) -> EvidenceQuality:
    return evidence_quality(
        candidate.assessment.evidence,
        candidate.assessment.gate.proof_paths,
        residuals=candidate.geometry.residuals,
    )
