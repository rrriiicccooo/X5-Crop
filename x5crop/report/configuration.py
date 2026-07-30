from __future__ import annotations

from typing import Any

from ..configuration.model import DetectionConfiguration
from .read_models import typed_read_model


def detection_configuration_read_model(
    configuration: DetectionConfiguration,
) -> dict[str, Any]:
    spec = configuration.physical_spec
    return {
        "configuration_id": configuration.configuration_id,
        "format_id": spec.format_id,
        "strip_mode": configuration.strip_mode,
        "resolved_frame_count": configuration.resolved_frame_count,
        "design_aperture_components_mm": typed_read_model(
            spec.aperture_components
        ),
        "strip_handling": typed_read_model(spec.strip),
        "scan_layout": typed_read_model(spec.layout),
        "measurement": {
            "preprocess": typed_read_model(configuration.preprocess),
            "scan_canvas": typed_read_model(configuration.scan_canvas),
            "content": typed_read_model(configuration.content),
        },
        "execution": {
            "detector_kind": configuration.detector_kind,
            "automatic_frame_export": False,
        },
        "diagnostics": typed_read_model(configuration.diagnostics),
    }
