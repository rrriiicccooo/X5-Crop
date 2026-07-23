from __future__ import annotations

from ..formats import FORMAT_CHOICES, format_spec
from ..strip_modes import STRIP_MODES
from .boundary import BoundaryPathParameters
from .candidate import CandidatePlanParameters
from .content import ContentConfiguration
from .diagnostics import DiagnosticsConfiguration
from .model import DetectionConfiguration
from .photo_edges import PhotoEdgeDetectionParameters
from .preprocess import PreprocessConfiguration
from .separator import SeparatorConfiguration
from .scan_canvas import ScanCanvasDetectionConfiguration
from .transform import TransformDetectionParameters
from ..formats.scan_canvas import scan_canvas_specs_for_format


def get_detection_configuration(
    format_id: str,
    strip_mode: str,
) -> DetectionConfiguration:
    if strip_mode not in STRIP_MODES:
        raise ValueError(f"Unsupported strip mode: {strip_mode}")
    if format_id not in FORMAT_CHOICES:
        raise ValueError(f"Unsupported format: {format_id}")
    spec = format_spec(format_id)
    return DetectionConfiguration(
        physical_spec=spec,
        strip_mode=strip_mode,
        preprocess=PreprocessConfiguration(),
        scan_canvas=ScanCanvasDetectionConfiguration(
            scan_canvas_specs_for_format(format_id)
        ),
        photo_edges=PhotoEdgeDetectionParameters(),
        transform=TransformDetectionParameters(),
        boundary_path=BoundaryPathParameters(),
        separator=SeparatorConfiguration(),
        content=ContentConfiguration(),
        candidate_plan=CandidatePlanParameters(),
        diagnostics=DiagnosticsConfiguration(),
    )
