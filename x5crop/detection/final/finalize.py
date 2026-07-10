from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

import numpy as np

from ...domain import FinalDetection, OutputProtectionPlan
from ...output.bleed import (
    apply_output_protection_plan,
)
from ...policies.parameters.exposure_overlap import EdgeBleedProtectionParameters
from ...policies.parameters.finalization import ApprovedGeometryAdjustmentParameters
from ...policies.runtime.diagnostics import RuntimeDiagnosticsPolicy
from ...policies.runtime.separator import SeparatorPolicy
from ...cache import AnalysisCache
from ..detail import DECISION_GEOMETRY
from ..evidence.read_only import attach_read_only_diagnostics
from ...output.geometry_adjustment import (
    apply_approved_geometry_adjustment,
    apply_edge_bleed_protection,
)


def _geometry_detail(detection: FinalDetection) -> dict[str, Any]:
    return {
        "outer_box": asdict(detection.outer),
        "frame_boxes": [asdict(frame) for frame in detection.frames],
    }


def finalize_detection(
    gray: np.ndarray,
    detection: FinalDetection,
    analysis_cache: AnalysisCache,
    output_protection_plan: OutputProtectionPlan,
    *,
    diagnostics_enabled: bool,
    approved_geometry_adjustment: ApprovedGeometryAdjustmentParameters,
    edge_bleed_protection: EdgeBleedProtectionParameters,
    separator_policy: SeparatorPolicy,
    diagnostics_policy: RuntimeDiagnosticsPolicy,
) -> FinalDetection:
    output_detection = deepcopy(detection)
    output_detection.detail[DECISION_GEOMETRY] = _geometry_detail(detection)
    apply_approved_geometry_adjustment(
        output_detection,
        gray,
        approved_geometry_adjustment,
    )
    apply_output_protection_plan(
        output_detection,
        output_protection_plan,
        gray.shape[1],
        gray.shape[0],
    )
    apply_edge_bleed_protection(
        output_detection,
        output_protection_plan.output_bleed,
        gray.shape[1],
        gray.shape[0],
        edge_bleed_protection,
    )
    if diagnostics_enabled:
        attach_read_only_diagnostics(
            gray,
            output_detection,
            analysis_cache,
            separator_policy=separator_policy,
            diagnostics_policy=diagnostics_policy,
        )
    return output_detection
