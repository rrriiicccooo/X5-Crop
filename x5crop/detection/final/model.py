from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from ...geometry.affine import AffineCoordinateTransform
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
    source_core: SourceCoreEvidence
    resolved_output_slots: ResolvedOutputSlots | None
    output_slot_identities: tuple[OutputSlotIdentity, ...]
    deskew_assessment: OutputDeskewAssessment
    output_transforms: tuple[AffineCoordinateTransform, ...]
    output_footprints: tuple[OutputFootprint, ...]
    sampling_authority_boxes: tuple[Box, ...]
    final_boxes: tuple[Box, ...]

    def __post_init__(self) -> None:
        if self.candidate.source_core is not self.source_core:
            raise ValueError("final detection must preserve source-core identity")
        if self.resolved_output_slots is not self.candidate.resolved_output_slots:
            raise ValueError(
                "finalization cannot replace resolved output slots"
            )
        if self.output_slot_identities != self.candidate.output_slot_identities:
            raise ValueError("finalization cannot replace slot identities")
        approved = self.decision.status == "approved_auto"
        if approved:
            expected = (
                None
                if self.resolved_output_slots is None
                else self.resolved_output_slots.output_slot_count
            )
            if (
                expected is None
                or len(self.output_transforms) != expected
                or len(self.output_slot_identities) != expected
                or len(self.output_footprints) != expected
                or len(self.sampling_authority_boxes) != expected
                or len(self.final_boxes) != expected
                or any(not box.valid() for box in self.sampling_authority_boxes)
                or any(not box.valid() for box in self.final_boxes)
                or any(
                    transform is not self.deskew_assessment.transform
                    for transform in self.output_transforms
                )
            ):
                raise ValueError(
                    "approved finalization requires one resolved geometry "
                    "and affine sampling box per output slot"
                )
        elif (
            self.decision.status != "needs_review"
            or self.output_transforms
            or self.output_footprints
            or self.sampling_authority_boxes
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
    def output_slot_count(self) -> int | None:
        return (
            None
            if self.resolved_output_slots is None
            else self.resolved_output_slots.output_slot_count
        )
