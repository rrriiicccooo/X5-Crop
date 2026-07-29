from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from ..decision.model import DecisionGateAssessment
from ..pipeline import SourceCoreCandidate
from ..source_core import SourceCoreEvidence


FRAME_EXPORT_REASON_GRID_AUTHORITY_UNAVAILABLE = (
    "frame_grid_authority_unavailable"
)


@dataclass(frozen=True)
class FinalDetection:
    candidate: SourceCoreCandidate
    decision: DecisionGateAssessment
    source_core: SourceCoreEvidence
    final_boxes: tuple[Box, ...] = ()

    def __post_init__(self) -> None:
        if self.candidate.source_core is not self.source_core:
            raise ValueError("final detection must preserve source-core identity")
        if self.decision.status != "needs_review":
            raise ValueError("current safety baseline cannot approve auto export")
        if self.final_boxes:
            raise ValueError("unavailable frame Grid cannot carry final boxes")

    @property
    def frame_export_eligible(self) -> bool:
        return False

    @property
    def frame_export_reason(self) -> str:
        return FRAME_EXPORT_REASON_GRID_AUTHORITY_UNAVAILABLE
