from __future__ import annotations

from ..decision.model import DecisionGateAssessment
from ..output_geometry import source_boxes_from_work_envelopes
from ..pipeline import BoundedSafeCropCandidate
from .model import FinalDetection


def finalize_detection(
    candidate: BoundedSafeCropCandidate,
    decision: DecisionGateAssessment,
    *,
    layout: str,
) -> FinalDetection:
    approved = decision.status == "approved_auto"
    protected = (
        tuple(
            envelope
            for lane_envelopes in candidate.protected_envelopes_by_lane
            for envelope in lane_envelopes
        )
        if approved
        else ()
    )
    boxes = (
        source_boxes_from_work_envelopes(
            protected,
            layout=layout,
        )
        if approved
        else ()
    )
    return FinalDetection(
        candidate=candidate,
        decision=decision,
        source_core=candidate.source_core,
        resolved_output_slots=candidate.resolved_output_slots,
        output_slot_identities=candidate.output_slot_identities,
        protected_envelopes=protected,
        transform_assessment=candidate.transform_assessment,
        final_boxes=boxes,
    )
