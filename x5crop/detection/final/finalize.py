from __future__ import annotations

from ..decision.model import DecisionGateAssessment
from ..output_deskew import LightweightDeskewObservation
from ..pipeline import PhotoGeometryCandidate
from ...geometry.convex import mapped_half_open_box
from .deskew import assess_output_deskew
from .model import FinalDetection


def finalize_detection(
    candidate: PhotoGeometryCandidate,
    decision: DecisionGateAssessment,
    deskew_observation: LightweightDeskewObservation | None,
    *,
    layout: str,
    source_width: int,
    source_height: int,
) -> FinalDetection:
    approved = decision.status == "approved_auto"
    if approved != (deskew_observation is not None):
        raise ValueError(
            "deskew observation is required only for approved output"
        )
    deskew_assessment = assess_output_deskew(
        deskew_observation,
        layout=layout,
        source_width=source_width,
        source_height=source_height,
    )
    footprints = candidate.output_footprints if approved else ()
    final_boxes = tuple(
        mapped_half_open_box(
            item.required_source_footprint,
            deskew_assessment.transform.map_point,
        )
        for item in footprints
    )
    extent = deskew_assessment.transform.output_extent
    if approved and any(
        box.left < 0
        or box.top < 0
        or box.right > extent.width
        or box.bottom > extent.height
        for box in final_boxes
    ):
        raise ValueError("approved deskew envelope exceeds its output extent")
    return FinalDetection(
        candidate=candidate,
        decision=decision,
        deskew_assessment=deskew_assessment,
        final_boxes=final_boxes,
    )
