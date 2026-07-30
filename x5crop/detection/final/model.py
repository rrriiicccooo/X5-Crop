from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from ..decision.model import DecisionGateAssessment
from ..grid.model import (
    OutputSlotIdentity,
    ProtectedCropEnvelope,
    ResolvedOutputSlots,
)
from ..output_geometry import OutputTransformAssessment
from ..pipeline import BoundedSafeCropCandidate
from ..source_core import SourceCoreEvidence


@dataclass(frozen=True)
class FinalDetection:
    candidate: BoundedSafeCropCandidate
    decision: DecisionGateAssessment
    source_core: SourceCoreEvidence
    resolved_output_slots: ResolvedOutputSlots | None
    output_slot_identities: tuple[OutputSlotIdentity, ...]
    protected_envelopes: tuple[ProtectedCropEnvelope, ...]
    transform_assessment: OutputTransformAssessment
    final_boxes: tuple[Box, ...]

    def __post_init__(self) -> None:
        if self.candidate.source_core is not self.source_core:
            raise ValueError("final detection must preserve source-core identity")
        if self.transform_assessment is not self.candidate.transform_assessment:
            raise ValueError("finalization cannot replace the selected transform")
        if self.resolved_output_slots is not self.candidate.resolved_output_slots:
            raise ValueError(
                "finalization cannot replace resolved output slots"
            )
        if self.output_slot_identities != (
            self.candidate.output_slot_identities
        ):
            raise ValueError("finalization cannot replace slot identities")
        approved = self.decision.status == "approved_auto"
        if approved:
            if (
                self.resolved_output_slots is None
                or len(self.output_slot_identities)
                != self.resolved_output_slots.output_slot_count
                or len(self.final_boxes)
                != self.resolved_output_slots.output_slot_count
                or len(self.protected_envelopes)
                != self.resolved_output_slots.output_slot_count
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

    @property
    def output_slot_count(self) -> int | None:
        return (
            None
            if self.resolved_output_slots is None
            else self.resolved_output_slots.output_slot_count
        )
