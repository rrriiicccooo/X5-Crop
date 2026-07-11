from __future__ import annotations

from dataclasses import replace

from ...output.bleed import output_bleed_geometry
from ..decision.model import FinalDetection


def finalize_detection(
    detection: FinalDetection,
    *,
    image_width: int,
    image_height: int,
) -> FinalDetection:
    geometry = output_bleed_geometry(
        detection.decision_geometry,
        detection.output_bleed_plan.effective_bleed,
        layout=detection.layout,
        image_width=image_width,
        image_height=image_height,
    )
    return replace(detection, output_geometry=geometry)
