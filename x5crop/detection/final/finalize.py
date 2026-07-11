from __future__ import annotations

from dataclasses import replace

import numpy as np

from ...policies.parameters.exposure_overlap import EdgeBleedProtectionParameters
from ...policies.parameters.finalization import ApprovedGeometryAdjustmentParameters
from ...output.bleed import output_bleed_geometry
from ...output.geometry_adjustment import (
    approved_geometry_adjustment,
    edge_bleed_protected_geometry,
)
from ..decision.model import FinalDetection


def finalize_detection(
    gray: np.ndarray,
    detection: FinalDetection,
    *,
    approved_geometry_parameters: ApprovedGeometryAdjustmentParameters,
    edge_bleed_parameters: EdgeBleedProtectionParameters,
) -> FinalDetection:
    geometry = approved_geometry_adjustment(
        detection.decision_geometry,
        gray,
        layout=detection.layout,
        strip_mode=detection.strip_mode,
        count=detection.count,
        approved=detection.status == "approved_auto"
        and not detection.final_review_reasons,
        parameters=approved_geometry_parameters,
    )
    geometry = output_bleed_geometry(
        geometry,
        detection.output_protection.output_bleed,
        layout=detection.layout,
        image_width=gray.shape[1],
        image_height=gray.shape[0],
    )
    geometry = edge_bleed_protected_geometry(
        geometry,
        layout=detection.layout,
        strip_mode=detection.strip_mode,
        count=detection.count,
        output_bleed=detection.output_protection.output_bleed,
        image_width=gray.shape[1],
        image_height=gray.shape[0],
        calibration=detection.scan_calibration,
        parameters=edge_bleed_parameters,
    )
    return replace(detection, output_geometry=geometry)
