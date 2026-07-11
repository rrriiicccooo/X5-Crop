from __future__ import annotations

from dataclasses import dataclass

from .. import geometry as geometry_types
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
from ..evidence.separator_continuity import SeparatorContinuityEvidence
from ..physical.photo_size import FrameDimensionEvidence
from .assessment.candidate_gate import CandidateGateAssessment
from .plan.count_hypotheses import CountHypothesis


@dataclass(frozen=True)
class BuiltCandidate:
    geometry: geometry_types.CandidateGeometry
    count_hypothesis: CountHypothesis | None
    build_diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class CandidateEvidence:
    frame_topology: FrameTopologyEvidence
    frame_coverage: FrameCoverageEvidence
    frame_sequence: FrameSequenceEvidence
    separator_sequence: SeparatorSequenceEvidence
    separator_continuity: SeparatorContinuityEvidence
    frame_dimensions: FrameDimensionEvidence
    frame_content: FrameContentEvidence
    holder_texture: HolderTextureEvidence
    content_preservation: ContentPreservationEvidence
    sequence_content_alignment: SequenceContentAlignmentEvidence
    holder_occupancy: HolderOccupancyEvidence
    partial_edge_safety: PartialEdgeSafetyEvidence
    independence: EvidenceIndependenceEvidence


@dataclass(frozen=True)
class CandidateScores:
    confidence: float
    base: float
    geometry: float
    separator: float
    content: float
    joint: float


@dataclass(frozen=True)
class CandidateAssessment:
    evidence: CandidateEvidence
    scores: CandidateScores
    gate: CandidateGateAssessment
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class AssessedCandidate:
    geometry: geometry_types.CandidateGeometry
    count_hypothesis: CountHypothesis | None
    assessment: CandidateAssessment
