from __future__ import annotations

from ..decision.model import DecisionGateAssessment
from ..pipeline import PhotoGeometryCandidate
from .model import FinalDetection


def finalize_detection(
    candidate: PhotoGeometryCandidate,
    decision: DecisionGateAssessment,
    *,
    layout: str,
) -> FinalDetection:
    del layout  # Source-coordinate authority is already explicit in geometry.
    approved = decision.status == "approved_auto"
    geometries = candidate.resolved_output_geometries if approved else ()
    source_boxes = (
        tuple(item.source_sampling_box for item in geometries)
        if approved
        else ()
    )
    transform = candidate.transform_assessment.transform
    final_boxes = (
        tuple(
            transform.map_half_open_box_outward(box)
            for box in source_boxes
        )
        if approved and transform is not None
        else ()
    )
    return FinalDetection(
        candidate=candidate,
        decision=decision,
        source_core=candidate.source_core,
        resolved_output_slots=candidate.resolved_output_slots,
        output_slot_identities=candidate.output_slot_identities,
        transform_assessment=candidate.transform_assessment,
        resolved_output_geometries=geometries,
        source_sampling_boxes=source_boxes,
        final_boxes=final_boxes,
    )
