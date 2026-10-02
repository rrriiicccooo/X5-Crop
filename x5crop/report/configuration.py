from __future__ import annotations

from typing import Any

from ..configuration.model import DetectionConfiguration
from ..detection.evidence.content_occupancy_model import (
    CONTENT_OCCUPANCY_MEASUREMENT_SPEC,
)
from ..detection.photo_geometry.model import (
    PHOTO_BOUNDARY_MEASUREMENT_SPEC,
    REGISTERED_NORMALIZATION_REVISION,
)
from .read_models import typed_read_model


def native_coarse_intensity_read_model() -> dict[str, Any]:
    from ..detection.photo_geometry.coarse_strip_support import NATIVE_COARSE_INTENSITY_QUANTUM
    from ..image.gray import BaseGrayParameters
    parameters = BaseGrayParameters()
    return {
        "unit": "native_uint16_rec709_code",
        "quantization_step": NATIVE_COARSE_INTENSITY_QUANTUM,
        "percentile_clipped": False,
        "weights": [parameters.red_weight, parameters.green_weight, parameters.blue_weight],
        "scope": "coarse_strip_short_broad",
    }


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
        "frame_physical_spec": typed_read_model(spec.frame),
        "scan_layout": typed_read_model(spec.layout),
        "measurement": {
            "coarse_broad_intensity": native_coarse_intensity_read_model(),
            "registered_normalization_revision": REGISTERED_NORMALIZATION_REVISION,
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
