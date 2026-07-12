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
    count_hypothesis: CountHypothesis | None
    build_diagnostics: tuple[str, ...]


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
    quality: EvidenceQuality
    gate: CandidateGateAssessment
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class AssessedCandidate:
    geometry: CandidateGeometry
    count_hypothesis: CountHypothesis | None
    assessment: CandidateAssessment
