from __future__ import annotations

from ...output.frame_bleed import apply_frame_bleed
from ..decision.model import DecisionResult
from .model import FinalDetection


def finalize_detection(
    decision: DecisionResult,
    *,
    image_width: int,
    image_height: int,
) -> FinalDetection:
    geometry = apply_frame_bleed(
        decision.decision_geometry,
        decision.frame_bleed_plan,
        layout=decision.layout,
        image_width=image_width,
        image_height=image_height,
    )
    return FinalDetection(decision=decision, output_geometry=geometry)
