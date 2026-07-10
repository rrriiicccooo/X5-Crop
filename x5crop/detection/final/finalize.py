from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from typing import Any

import numpy as np

from ...run_config import RunConfig
from ...domain import FinalDetection, OutputProtectionPlan
from ...output.bleed import (
    apply_output_protection_plan,
)
from ...policies.runtime.policy import DetectionPolicy
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
    config: RunConfig,
    analysis_cache: AnalysisCache,
    policy: DetectionPolicy,
    output_protection_plan: OutputProtectionPlan,
) -> FinalDetection:
    output_detection = deepcopy(detection)
    output_detection.detail[DECISION_GEOMETRY] = _geometry_detail(detection)
    apply_approved_geometry_adjustment(
        output_detection,
        gray,
        policy.finalization.approved_geometry_adjustment,
    )
    output_config = replace(
        config,
        bleed_x=output_protection_plan.output_bleed.long_axis,
        bleed_y=output_protection_plan.output_bleed.short_axis,
    )
    apply_output_protection_plan(
        output_detection,
        output_protection_plan,
        gray.shape[1],
        gray.shape[0],
    )
    apply_edge_bleed_protection(
        output_detection,
        output_config,
        gray.shape[1],
        gray.shape[0],
        policy.output.edge_bleed_protection,
    )
    if config.diagnostics:
        attach_read_only_diagnostics(
            gray,
            output_detection,
            analysis_cache,
            separator_policy=policy.separator,
            diagnostics_policy=policy.diagnostics,
        )
    return output_detection
