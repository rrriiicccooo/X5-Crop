from __future__ import annotations

from dataclasses import dataclass

from ..formats import FormatSpec
from ..strip_modes import FULL, PARTIAL
from .content import ContentConfiguration
from .diagnostics import DiagnosticsConfiguration
from .preprocess import PreprocessConfiguration
from .scan_canvas import ScanCanvasDetectionConfiguration


@dataclass(frozen=True)
class DetectionConfiguration:
    physical_spec: FormatSpec
    strip_mode: str
    preprocess: PreprocessConfiguration
    scan_canvas: ScanCanvasDetectionConfiguration
    content: ContentConfiguration
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
        return "source_core_review"

    @property
    def configuration_id(self) -> str:
        return (
            f"detection:{self.physical_spec.format_id}:{self.strip_mode}"
        )
