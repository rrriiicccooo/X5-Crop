from __future__ import annotations

from dataclasses import dataclass

from .candidate.assessment.candidate_gate import candidate_gate_assessment
from .candidate.assessment.model import CandidateGateAssessment
from .source_core import SourceCoreEvidence


@dataclass(frozen=True)
class SourceCoreCandidate:
    source_core: SourceCoreEvidence
    gate: CandidateGateAssessment


def choose_detection(source_core: SourceCoreEvidence) -> SourceCoreCandidate:
    return SourceCoreCandidate(
        source_core=source_core,
        gate=candidate_gate_assessment(source_core),
    )
