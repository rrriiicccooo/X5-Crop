from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState

from ..physical.model import (
    CandidateGeometry,
    DualLaneSolution,
    ReviewOnlyGeometry,
)
from .assessment.evidence_independence import EvidenceIndependenceEvidence
from .assessment.separator_support import SeparatorSequenceEvidence
from ..evidence.content.preservation import ContentPreservationEvidence
from ..evidence.content.frame_support import FrameContentEvidence
from ..evidence.content.holder_texture import HolderTextureEvidence
from ..evidence.frame_coverage import FrameCoverageEvidence
from ..evidence.frame_sequence import FrameSequenceEvidence
from ..evidence.frame_topology import FrameTopologyEvidence
from ..evidence.holder_occupancy import HolderOccupancyEvidence
from ..evidence.sequence_content_alignment import SequenceContentAlignmentEvidence
from ..evidence.partial_edge import PartialEdgeSafetyEvidence
from ..physical.photo_size import FrameDimensionEvidence
from .assessment.candidate_gate import CandidateGateAssessment
from .plan.count_hypotheses import CountHypothesis
from ..physical.model import SequenceResiduals


@dataclass(frozen=True)
class BuiltCandidate:
    geometry: CandidateGeometry
    count_hypothesis: CountHypothesis
    build_diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.count_hypothesis.count != self.geometry.count
            or self.count_hypothesis.strip_mode != self.geometry.strip_mode
        ):
            raise ValueError("built candidate count hypothesis must match geometry")
        if any(not item for item in self.build_diagnostics) or len(
            set(self.build_diagnostics)
        ) != len(self.build_diagnostics):
            raise ValueError("build diagnostics must be non-empty and unique")


@dataclass(frozen=True)
class CandidateEvidence:
    frame_topology: FrameTopologyEvidence
    frame_coverage: FrameCoverageEvidence
    frame_sequence: FrameSequenceEvidence
    separator_sequence: SeparatorSequenceEvidence
    frame_dimensions: FrameDimensionEvidence
    frame_content: FrameContentEvidence
    holder_texture: HolderTextureEvidence
    content_preservation: ContentPreservationEvidence
    sequence_content_alignment: SequenceContentAlignmentEvidence
    holder_occupancy: HolderOccupancyEvidence
    partial_edge_safety: PartialEdgeSafetyEvidence
    independence: EvidenceIndependenceEvidence


@dataclass(frozen=True)
class DualLaneEvidence:
    lane_evidence: tuple[CandidateEvidence, ...]

    def __post_init__(self) -> None:
        if len(self.lane_evidence) <= 1:
            raise ValueError("dual-lane evidence requires multiple lane evidence sets")


@dataclass(frozen=True)
class ReviewOnlyEvidence:
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("review-only evidence requires a reason")


CandidateEvidenceModel = CandidateEvidence | DualLaneEvidence | ReviewOnlyEvidence


@dataclass(frozen=True)
class EvidenceQuality:
    supported: tuple[str, ...]
    contradicted: tuple[str, ...]
    unavailable: tuple[str, ...]
    covered_content_px: int
    uncovered_content_px: int
    supported_proof_paths: tuple[str, ...]
    physical_residuals: SequenceResiduals | None


@dataclass(frozen=True)
class CandidateAssessment:
    evidence: CandidateEvidenceModel
    gate: CandidateGateAssessment | None

    def __post_init__(self) -> None:
        if isinstance(self.evidence, ReviewOnlyEvidence):
            if self.gate is not None:
                raise ValueError("review-only assessment cannot own CandidateGate")
        elif self.gate is None:
            raise ValueError("physical candidate assessment requires CandidateGate")


@dataclass(frozen=True)
class AssessedCandidate:
    geometry: CandidateGeometry
    count_hypothesis: CountHypothesis
    assessment: CandidateAssessment

    def __post_init__(self) -> None:
        if (
            self.count_hypothesis.count != self.geometry.count
            or self.count_hypothesis.strip_mode != self.geometry.strip_mode
        ):
            raise ValueError("assessed candidate count hypothesis must match geometry")
        expected_evidence = (
            ReviewOnlyEvidence
            if isinstance(self.geometry, ReviewOnlyGeometry)
            else DualLaneEvidence
            if isinstance(self.geometry, DualLaneSolution)
            else CandidateEvidence
        )
        if not isinstance(self.assessment.evidence, expected_evidence):
            raise ValueError("candidate geometry and evidence model must match")

    @property
    def evidence_quality(self) -> EvidenceQuality:
        evidence_model = self.assessment.evidence
        if isinstance(evidence_model, ReviewOnlyEvidence):
            return EvidenceQuality(
                supported=(),
                contradicted=(),
                unavailable=(evidence_model.reason,),
                covered_content_px=0,
                uncovered_content_px=0,
                supported_proof_paths=(),
                physical_residuals=self.geometry.residuals,
            )
        evidence_sets = (
            evidence_model.lane_evidence
            if isinstance(evidence_model, DualLaneEvidence)
            else (evidence_model,)
        )
        named_states: list[tuple[str, EvidenceState]] = []
        content_total = 0
        uncovered = 0
        for lane_index, evidence in enumerate(evidence_sets, start=1):
            prefix = (
                f"lane_{lane_index}:"
                if isinstance(evidence_model, DualLaneEvidence)
                else ""
            )
            named_states.extend(
                (f"{prefix}{code}", state)
                for code, state in (
                    ("frame_topology", evidence.frame_topology.state),
                    ("frame_coverage", evidence.frame_coverage.state),
                    (
                        "frame_sequence_conservation",
                        evidence.frame_sequence.conservation.state,
                    ),
                    ("separator_sequence", evidence.separator_sequence.state),
                    ("frame_dimensions", evidence.frame_dimensions.state),
                    ("frame_content", evidence.frame_content.state),
                    ("holder_texture", evidence.holder_texture.state),
                    ("content_preservation", evidence.content_preservation.state),
                    (
                        "sequence_content_alignment",
                        evidence.sequence_content_alignment.state,
                    ),
                    ("holder_occupancy", evidence.holder_occupancy.state),
                    ("partial_edge_safety", evidence.partial_edge_safety.state),
                    ("evidence_independence", evidence.independence.state),
                )
            )
            content_total += sum(
                max(0, int(end) - int(start))
                for start, end in evidence.frame_coverage.content_runs
            )
            uncovered += sum(
                max(0, int(end) - int(start))
                for start, end in evidence.frame_coverage.uncovered_content
            )
        gate = self.assessment.gate
        if gate is None:
            raise ValueError("physical evidence quality requires CandidateGate")
        return EvidenceQuality(
            supported=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.SUPPORTED
            ),
            contradicted=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.CONTRADICTED
            ),
            unavailable=tuple(
                code
                for code, state in named_states
                if state == EvidenceState.UNAVAILABLE
            ),
            covered_content_px=max(0, content_total - uncovered),
            uncovered_content_px=uncovered,
            supported_proof_paths=tuple(
                path.code
                for path in gate.proof_paths
                if path.state == EvidenceState.SUPPORTED
            ),
            physical_residuals=self.geometry.residuals,
        )
