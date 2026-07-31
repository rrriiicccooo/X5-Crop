from __future__ import annotations

from typing import Any

from ..configuration.model import DetectionConfiguration
from ..configuration.photo_geometry import (
    frame_sequence_physical_constraints,
)
from ..detection.photo_geometry.model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
)
from .read_models import typed_read_model


def detection_configuration_read_model(
    configuration: DetectionConfiguration,
) -> dict[str, Any]:
    spec = configuration.physical_spec
    return {
        "configuration_id": configuration.configuration_id,
        "format_id": spec.format_id,
        "strip_mode": configuration.strip_mode,
        "output_slot_request": typed_read_model(
            configuration.count_request
        ),
        "design_aperture_components_mm": typed_read_model(
            spec.aperture_components
        ),
        "aperture_tolerance_mm": typed_read_model(
            spec.aperture_tolerance
        ),
        "strip_handling": typed_read_model(spec.strip),
        "scan_layout": typed_read_model(spec.layout),
        "measurement": {
            "preprocess": typed_read_model(configuration.preprocess),
            "scan_canvas": typed_read_model(configuration.scan_canvas),
            "content": typed_read_model(configuration.content),
            "photo_boundary_measurement_spec": typed_read_model(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC
            ),
            "frame_sequence_physical_constraints": typed_read_model(
                frame_sequence_physical_constraints(
                    spec.format_id,
                    spec.aperture_components,
                )
            ),
        },
        "execution": {
            "detector_kind": configuration.detector_kind,
            "automatic_frame_export": True,
        },
        "diagnostics": typed_read_model(configuration.diagnostics),
    }
