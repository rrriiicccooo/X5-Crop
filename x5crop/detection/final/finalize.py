from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from typing import Any

import numpy as np

from ...runtime.config import RuntimeConfig
from ...domain import FinalDetection
from ...output.bleed import (
    AxisBleedParameters,
    apply_output_bleed,
    detection_bleed_parameters,
    output_bleed_parameters_for_detection,
)
from ...policies.runtime.policy import DetectionPolicy
from ...cache import AnalysisCache
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
    config: RuntimeConfig,
    analysis_cache: AnalysisCache,
    policy: DetectionPolicy,
) -> FinalDetection:
    output_detection = deepcopy(detection)
    output_detection.detail["decision_geometry"] = _geometry_detail(detection)
    detection_bleed = detection_bleed_parameters(policy.output)
    if policy.finalization.apply_approved_geometry_adjustment:
        apply_approved_geometry_adjustment(
            output_detection,
            gray,
            policy.finalization.approved_geometry_adjustment,
        )
    base_bleed = AxisBleedParameters(
        long_axis=int(config.bleed_x),
        short_axis=int(config.bleed_y),
    )
    output_bleed = output_bleed_parameters_for_detection(base_bleed, detection, policy.output)
    output_config = replace(
        config,
        bleed_x=output_bleed.long_axis,
        bleed_y=output_bleed.short_axis,
    )
    if policy.output.apply_output_bleed:
        apply_output_bleed(
            output_detection,
            detection_bleed,
            output_bleed,
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
    if not policy.diagnostics.attach_read_only_when_requested or config.diagnostics:
        attach_read_only_diagnostics(
            gray,
            output_detection,
            analysis_cache,
            separator_policy=policy.separator,
            diagnostics_policy=policy.diagnostics,
            output_evidence_policy=policy.output_evidence,
        )
    output_detection.detail["output_geometry"] = _geometry_detail(output_detection)
    return output_detection
