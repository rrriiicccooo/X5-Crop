from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from ..decision.model import DecisionGateAssessment
from ..grid.model import ProtectedCropEnvelope
from ..output_geometry import OutputTransformAssessment
from ..pipeline import BoundedSafeCropCandidate
from ..source_core import SourceCoreEvidence


@dataclass(frozen=True)
class FinalDetection:
    candidate: BoundedSafeCropCandidate
    decision: DecisionGateAssessment
    source_core: SourceCoreEvidence
    selected_count: int | None
    protected_envelopes: tuple[ProtectedCropEnvelope, ...]
    transform_assessment: OutputTransformAssessment
    final_boxes: tuple[Box, ...]

    def __post_init__(self) -> None:
        if self.candidate.source_core is not self.source_core:
            raise ValueError("final detection must preserve source-core identity")
        if self.transform_assessment is not self.candidate.transform_assessment:
            raise ValueError("finalization cannot replace the selected transform")
        if self.selected_count != self.candidate.selected_count:
            raise ValueError("finalization cannot replace the selected count")
        approved = self.decision.status == "approved_auto"
        if approved:
            if (
                self.selected_count is None
                or self.selected_count <= 0
                or len(self.final_boxes) != self.selected_count
                or len(self.protected_envelopes) != self.selected_count
                or any(not box.valid() for box in self.final_boxes)
            ):
                raise ValueError(
                    "approved finalization requires one protected box per frame"
                )
        elif (
            self.decision.status != "needs_review"
            or self.final_boxes
            or self.protected_envelopes
        ):
            raise ValueError("review finalization cannot expose frame outputs")

    @property
    def frame_export_eligible(self) -> bool:
        return self.decision.status == "approved_auto"

    @property
    def frame_export_reason(self) -> str | None:
        return (
            None
            if self.frame_export_eligible
            else "decision_gate_needs_review"
        )
