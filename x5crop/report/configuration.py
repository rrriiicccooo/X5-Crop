from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from ..configuration.model import DetectionConfiguration


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def detection_configuration_read_model(
    configuration: DetectionConfiguration,
) -> dict[str, Any]:
    spec = configuration.physical_spec
    return {
        "configuration_id": configuration.configuration_id,
        "format_id": spec.format_id,
        "strip_mode": configuration.strip_mode,
        "physical": {
            "physical_layout": spec.physical_layout,
            "default_count": int(spec.default_count),
            "expected_separator_count": int(spec.expected_separator_count),
            "allowed_counts": list(spec.allowed_counts),
            "nominal_frame_size_mm": _plain(spec.nominal_frame_size_mm),
            "frame_size_mm_options": _plain(spec.frame_size_mm_options),
            "frame_aspect": spec.horizontal_content_aspect,
            "aspect_source": "frame_size_mm",
            "complete_strip_can_be_underfilled": bool(
                spec.complete_strip_can_be_underfilled
            ),
        },
        "measurement": {
            "preprocess": _plain(configuration.preprocess),
            "separator": _plain(configuration.separator),
            "content": _plain(configuration.content),
        },
        "execution": {
            "detector_kind": configuration.detector_kind,
            "candidate_plan": _plain(configuration.candidate_plan),
        },
        "diagnostics": _plain(configuration.diagnostics),
    }
