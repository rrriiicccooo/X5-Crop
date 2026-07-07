from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from ...runtime.config import RuntimeConfig
from ...domain import Detection
from ...output.bleed import (
    AxisBleedParameters,
    apply_output_bleed,
    detection_bleed_parameters,
    output_bleed_parameters_for_detection,
)
from ...policies.runtime.policy import DetectionPolicy
from ...cache import AnalysisCache
from ..evidence.read_only import attach_read_only_diagnostics
from .geometry import (
    apply_approved_geometry_adjustment,
    apply_edge_bleed_protection,
)


@dataclass
class DetectionFinalizationResult:
    detection: Detection
    status: str
    output_config: RuntimeConfig


def finalize_detection(
    gray: np.ndarray,
    detection: Detection,
    status: str,
    config: RuntimeConfig,
    analysis_cache: AnalysisCache,
    policy: DetectionPolicy,
) -> DetectionFinalizationResult:
    detection_bleed = detection_bleed_parameters(policy.output)
    if policy.finalization.apply_approved_geometry_adjustment:
        apply_approved_geometry_adjustment(
            detection,
            gray,
            config,
            status,
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
            detection,
            detection_bleed,
            output_bleed,
            gray.shape[1],
            gray.shape[0],
        )
        apply_edge_bleed_protection(
            detection,
            output_config,
            gray.shape[1],
            gray.shape[0],
            policy.output.edge_bleed_protection,
        )
    if not policy.diagnostics.attach_read_only_when_requested or config.diagnostics:
        attach_read_only_diagnostics(gray, detection, analysis_cache)
    return DetectionFinalizationResult(
        detection=detection,
        status=status,
        output_config=output_config,
    )
