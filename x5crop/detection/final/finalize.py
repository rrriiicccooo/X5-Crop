from __future__ import annotations

from ..decision.model import DecisionGateAssessment
from ..pipeline import SourceCoreCandidate
from .model import FinalDetection


def finalize_detection(
    candidate: SourceCoreCandidate,
    decision: DecisionGateAssessment,
) -> FinalDetection:
    return FinalDetection(
        candidate=candidate,
        decision=decision,
        source_core=candidate.source_core,
        final_boxes=(),
    )
