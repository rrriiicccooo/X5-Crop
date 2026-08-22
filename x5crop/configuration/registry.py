from __future__ import annotations

from ..formats import FORMAT_CHOICES, format_spec
from ..image.gray import BaseGrayParameters
from .diagnostics import DiagnosticsConfiguration
from .model import DetectionConfiguration, SlotCountRequest
from .scan_canvas import ScanCanvasDetectionConfiguration
from ..formats.scan_canvas import scan_canvas_specs_for_format


def get_detection_configuration(
    format_id: str,
    frame_count: int | None = None,
) -> DetectionConfiguration:
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format: {format_id}")
    spec = format_spec(format_id)
    count_request = SlotCountRequest(frame_count)
    return DetectionConfiguration(
        physical_spec=spec,
        count_request=count_request,
        base_gray=BaseGrayParameters(),
        scan_canvas=ScanCanvasDetectionConfiguration(
            scan_canvas_specs_for_format(format_id)
        ),
        diagnostics=DiagnosticsConfiguration(),
    )
