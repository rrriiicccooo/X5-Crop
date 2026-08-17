from __future__ import annotations

from ..decision.model import DecisionGateAssessment
from ..pipeline import PhotoGeometryCandidate
from .model import FinalDetection


def finalize_detection(
    candidate: PhotoGeometryCandidate,
    decision: DecisionGateAssessment,
) -> FinalDetection:
    approved = decision.status == "approved_auto"
    footprints = candidate.output_footprints if approved else ()
    authority_boxes = (
        tuple(item.sampling_authority_box for item in footprints)
        if approved
        else ()
    )
    final_boxes = (
        tuple(item.mapped_output_box for item in footprints)
        if approved
        else ()
    )
    if approved and any(box is None for box in final_boxes):
        raise ValueError("approved geometry requires its mapped output box")
    return FinalDetection(
        candidate=candidate,
        decision=decision,
        source_core=candidate.source_core,
        resolved_output_slots=candidate.resolved_output_slots,
        output_slot_identities=candidate.output_slot_identities,
        source_transform_assessment=candidate.source_transform_assessment,
        output_transforms=(candidate.output_transforms if approved else ()),
        output_footprints=footprints,
        sampling_authority_boxes=authority_boxes,
        final_boxes=final_boxes,
    )
