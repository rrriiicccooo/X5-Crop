from __future__ import annotations

from dataclasses import replace

from ...output.frame_bleed import apply_frame_bleed
from ..decision.model import FinalDetection


def finalize_detection(
    detection: FinalDetection,
    *,
    image_width: int,
    image_height: int,
) -> FinalDetection:
    geometry = apply_frame_bleed(
        detection.decision_geometry,
        detection.frame_bleed_plan,
        layout=detection.layout,
        image_width=image_width,
        image_height=image_height,
    )
    return replace(detection, output_geometry=geometry)
