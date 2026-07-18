from __future__ import annotations

from typing import Any

from ..configuration.model import DetectionConfiguration
from ..formats import expected_separator_count
from .read_models import typed_read_model


def detection_configuration_read_model(
    configuration: DetectionConfiguration,
) -> dict[str, Any]:
    spec = configuration.physical_spec
    return {
        "configuration_id": configuration.configuration_id,
        "format_id": spec.format_id,
        "strip_mode": configuration.strip_mode,
        "physical": {
            "physical_layout": spec.layout.kind,
            "default_count": int(spec.strip.default_count),
            "expected_separator_count": int(
                expected_separator_count(spec.strip, spec.layout)
            ),
            "allowed_partial_counts": list(
                spec.strip.allowed_partial_counts
            ),
            "nominal_frame_size_mm": typed_read_model(spec.frame.nominal_size_mm),
            "frame_size_mm_options": typed_read_model(
                spec.frame.frame_size_mm_options
            ),
            "frame_aspect": spec.frame.nominal_size_mm.aspect,
            "aspect_source": "frame_size_mm",
            "complete_strip_can_be_underfilled": bool(
                spec.strip.complete_strip_can_be_underfilled
            ),
        },
        "measurement": {
            "boundary_path": typed_read_model(configuration.boundary_path),
            "preprocess": typed_read_model(configuration.preprocess),
            "separator": typed_read_model(configuration.separator),
            "content": typed_read_model(configuration.content),
        },
        "execution": {
            "detector_kind": configuration.detector_kind,
            "candidate_plan": typed_read_model(configuration.candidate_plan),
        },
        "diagnostics": typed_read_model(configuration.diagnostics),
    }
