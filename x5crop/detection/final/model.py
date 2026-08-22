from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from ..decision.model import DecisionGateAssessment
from ..photo_geometry.output_model import (
    OutputFootprint,
    OutputSlotIdentity,
    ResolvedOutputSlots,
)
from ..pipeline import PhotoGeometryCandidate
from ..source_core import SourceCoreEvidence
from .deskew import OutputDeskewAssessment


@dataclass(frozen=True)
class FinalDetection:
    """Decision-gated output authority.

    Candidate geometry remains available for audit on review outcomes, but only
    an approved decision may expose output geometry or sampling boxes to the
    product writer.
    """

    candidate: PhotoGeometryCandidate
    decision: DecisionGateAssessment
    deskew_assessment: OutputDeskewAssessment
    final_boxes: tuple[Box, ...]

    def __post_init__(self) -> None:
        approved = self.decision.status == "approved_auto"
        if approved:
            expected = (
                None
                if self.resolved_output_slots is None
                else self.resolved_output_slots.output_slot_count
            )
            if (
                expected is None
                or len(self.output_slot_identities) != expected
                or len(self.output_footprints) != expected
                or len(self.final_boxes) != expected
                or any(
                    not footprint.sampling_authority_box.valid()
                    for footprint in self.output_footprints
                )
                or any(not box.valid() for box in self.final_boxes)
            ):
                raise ValueError(
                    "approved finalization requires one resolved geometry "
                    "and affine sampling box per output slot"
                )
        elif (
            self.decision.status != "needs_review"
            or self.final_boxes
        ):
            raise ValueError(
                "review finalization cannot expose official output geometry"
            )

    @property
    def frame_export_eligible(self) -> bool:
        return self.decision.status == "approved_auto"

    @property
    def frame_export_reason(self) -> str | None:
        return None if self.frame_export_eligible else "decision_gate_needs_review"

    @property
    def source_core(self) -> SourceCoreEvidence:
        return self.candidate.source_core

    @property
    def resolved_output_slots(self) -> ResolvedOutputSlots | None:
        return self.candidate.resolved_output_slots

    @property
    def output_slot_identities(self) -> tuple[OutputSlotIdentity, ...]:
        return self.candidate.output_slot_identities

    @property
    def output_footprints(self) -> tuple[OutputFootprint, ...]:
        return (
            self.candidate.output_footprints
            if self.frame_export_eligible
            else ()
        )

    @property
    def output_slot_count(self) -> int | None:
        return (
            None
            if self.resolved_output_slots is None
            else self.resolved_output_slots.output_slot_count
        )
