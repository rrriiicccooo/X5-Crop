from __future__ import annotations

from dataclasses import dataclass

from ..formats import FormatSpec
from ..strip_modes import FULL, PARTIAL
from .boundary import BoundaryPathParameters
from .candidate import CandidatePlanParameters
from .content import ContentConfiguration
from .diagnostics import DiagnosticsConfiguration
from .photo_edges import PhotoEdgeDetectionParameters
from .preprocess import PreprocessConfiguration
from .separator import SeparatorConfiguration
from .scan_canvas import ScanCanvasDetectionConfiguration
from .transform import TransformDetectionParameters


@dataclass(frozen=True)
class DetectionConfiguration:
    physical_spec: FormatSpec
    strip_mode: str
    preprocess: PreprocessConfiguration
    scan_canvas: ScanCanvasDetectionConfiguration
    photo_edges: PhotoEdgeDetectionParameters
    transform: TransformDetectionParameters
    boundary_path: BoundaryPathParameters
    separator: SeparatorConfiguration
    content: ContentConfiguration
    candidate_plan: CandidatePlanParameters
    diagnostics: DiagnosticsConfiguration

    def __post_init__(self) -> None:
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError(f"unsupported strip mode: {self.strip_mode}")
        has_fixed_canvas = self.physical_spec.layout.kind != "dual_lane"
        if has_fixed_canvas != bool(self.scan_canvas.profiles):
            raise ValueError(
                "only single-strip detection requires scan-canvas profiles"
            )

    @property
    def detector_kind(self) -> str:
        if self.physical_spec.layout.kind != "dual_lane":
            return "standard_strip"
        return "dual_lane" if self.strip_mode == FULL else "review_only"

    @property
    def configuration_id(self) -> str:
        return (
            f"detection:{self.physical_spec.format_id}:{self.strip_mode}"
        )
