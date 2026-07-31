from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..formats import FormatSpec
from ..strip_modes import FULL, PARTIAL
from .content import ContentConfiguration
from .diagnostics import DiagnosticsConfiguration
from .preprocess import PreprocessConfiguration
from .scan_canvas import ScanCanvasDetectionConfiguration


class FrameCountMode(str, Enum):
    FIXED_FULL = "fixed_full"
    EXPLICIT = "explicit"
    AUTO = "auto"


@dataclass(frozen=True)
class FrameCountRequest:
    mode: FrameCountMode
    authoritative_count: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, FrameCountMode):
            raise TypeError("frame-count request requires a typed mode")
        if self.mode == FrameCountMode.AUTO:
            if self.authoritative_count is not None:
                raise ValueError("automatic count cannot carry an explicit value")
        elif self.authoritative_count is None or self.authoritative_count <= 0:
            raise ValueError(
                "fixed and explicit count requests require one positive authority"
            )

    @classmethod
    def from_user_input(
        cls,
        physical_spec: FormatSpec,
        strip_mode: str,
        requested_count: int | None,
    ) -> "FrameCountRequest":
        if strip_mode == FULL:
            if (
                requested_count is not None
                and requested_count != physical_spec.strip.default_count
            ):
                raise ValueError(
                    f"--format {physical_spec.format_id} full mode requires "
                    f"--count {physical_spec.strip.default_count}"
                )
            count = physical_spec.strip.default_count
            return cls(FrameCountMode.FIXED_FULL, count)
        if strip_mode != PARTIAL:
            raise ValueError(f"unsupported strip mode: {strip_mode}")
        if not physical_spec.strip.partial_mode_supported:
            raise ValueError(
                f"--format {physical_spec.format_id} does not support partial mode"
            )
        if requested_count is None:
            return cls(FrameCountMode.AUTO, None)
        if requested_count not in physical_spec.strip.partial_count_range:
            allowed = f"1..{physical_spec.strip.default_count}"
            raise ValueError(
                f"--format {physical_spec.format_id} partial mode allows "
                f"--count values: {allowed}"
            )
        return cls(FrameCountMode.EXPLICIT, requested_count)


@dataclass(frozen=True)
class DetectionConfiguration:
    physical_spec: FormatSpec
    strip_mode: str
    count_request: FrameCountRequest
    preprocess: PreprocessConfiguration
    scan_canvas: ScanCanvasDetectionConfiguration
    content: ContentConfiguration
    diagnostics: DiagnosticsConfiguration

    def __post_init__(self) -> None:
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError(f"unsupported strip mode: {self.strip_mode}")
        if self.strip_mode == FULL:
            if self.count_request.mode != FrameCountMode.FIXED_FULL:
                raise ValueError(
                    "full detection configuration requires fixed-full count"
                )
        elif self.count_request.mode == FrameCountMode.FIXED_FULL:
            raise ValueError(
                "partial detection configuration cannot use fixed-full mode"
            )
        if (
            self.count_request.authoritative_count is not None
            and self.count_request.authoritative_count
            > self.physical_spec.strip.default_count
        ):
            raise ValueError("authoritative output-slot count exceeds the format maximum")
        if not self.scan_canvas.profiles:
            raise ValueError(
                "detection configuration requires scan-canvas profiles"
            )

    @property
    def detector_kind(self) -> str:
        return "source_coordinate_photo_geometry"

    @property
    def configuration_id(self) -> str:
        count_identity = {
            FrameCountMode.FIXED_FULL: "format_default",
            FrameCountMode.AUTO: "scan_canvas_capacity",
        }.get(
            self.count_request.mode,
            f"user_explicit:{self.count_request.authoritative_count}",
        )
        return (
            f"detection:{self.physical_spec.format_id}:{self.strip_mode}:"
            f"slot_policy:{count_identity}"
        )
