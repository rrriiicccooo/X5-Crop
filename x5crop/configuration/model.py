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
    resolved_frame_count: int | None
    preprocess: PreprocessConfiguration
    scan_canvas: ScanCanvasDetectionConfiguration
    content: ContentConfiguration
    diagnostics: DiagnosticsConfiguration

    def __post_init__(self) -> None:
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError(f"unsupported strip mode: {self.strip_mode}")
        if self.strip_mode == FULL:
            if (
                self.resolved_frame_count
                != self.physical_spec.strip.default_count
            ):
                raise ValueError(
                    "full detection configuration requires default count"
                )
        elif (
            self.resolved_frame_count is not None
            and self.resolved_frame_count
            not in self.physical_spec.strip.allowed_partial_counts
        ):
            raise ValueError(
                "partial detection configuration requires an allowed count"
            )
        if not self.scan_canvas.profiles:
            raise ValueError(
                "detection configuration requires scan-canvas profiles"
            )

    @property
    def detector_kind(self) -> str:
        return "source_core_review"

    @property
    def configuration_id(self) -> str:
        count_identity = (
            "unspecified"
            if self.resolved_frame_count is None
            else str(self.resolved_frame_count)
        )
        return (
            f"detection:{self.physical_spec.format_id}:{self.strip_mode}:"
            f"count:{count_identity}"
        )
