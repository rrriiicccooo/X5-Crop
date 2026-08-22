from __future__ import annotations

from typing import Any

from ..configuration.model import DetectionConfiguration
from ..formats import FRAME_DIMENSION_TOLERANCE_SPEC
from ..detection.evidence.content_occupancy_model import (
    CONTENT_OCCUPANCY_MEASUREMENT_SPEC,
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
        "slot_count_request": typed_read_model(
            configuration.count_request
        ),
        "frame_physical_spec_mm": typed_read_model(spec.frame),
        "frame_dimension_tolerance": typed_read_model(
            FRAME_DIMENSION_TOLERANCE_SPEC
        ),
        "scan_layout": typed_read_model(spec.layout),
        "measurement": {
            "base_gray": typed_read_model(configuration.base_gray),
            "scan_canvas": typed_read_model(configuration.scan_canvas),
            "photo_boundary_measurement_spec": typed_read_model(
                PHOTO_BOUNDARY_MEASUREMENT_SPEC
            ),
            "content_occupancy_measurement_spec": typed_read_model(
                CONTENT_OCCUPANCY_MEASUREMENT_SPEC
            ),
        },
    }
