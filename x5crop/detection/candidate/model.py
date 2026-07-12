from __future__ import annotations

from dataclasses import dataclass

from ..physical.model import CandidateGeometry
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
class EvidenceQuality:
    supported: tuple[str, ...]
    contradicted: tuple[str, ...]
    unavailable: tuple[str, ...]
    not_applicable: tuple[str, ...]
    covered_content_px: int
    uncovered_content_px: int
    supported_proof_paths: tuple[str, ...]
    physical_residuals: SequenceResiduals | None


@dataclass(frozen=True)
class CandidateAssessment:
    evidence: CandidateEvidence
    gate: CandidateGateAssessment


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
