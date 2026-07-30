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
    requested_count: int | None
    candidate_counts: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mode, FrameCountMode):
            raise TypeError("frame-count request requires a typed mode")
        if (
            not self.candidate_counts
            or tuple(sorted(set(self.candidate_counts))) != self.candidate_counts
            or any(count <= 0 for count in self.candidate_counts)
        ):
            raise ValueError(
                "frame-count candidates must be positive, unique, and ordered"
            )
        if self.mode == FrameCountMode.AUTO:
            if self.requested_count is not None:
                raise ValueError("automatic count cannot carry an explicit value")
        elif (
            self.requested_count is None
            or self.candidate_counts != (self.requested_count,)
        ):
            raise ValueError(
                "fixed and explicit count requests require one matching candidate"
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
            return cls(FrameCountMode.FIXED_FULL, count, (count,))
        if strip_mode != PARTIAL:
            raise ValueError(f"unsupported strip mode: {strip_mode}")
        if not physical_spec.strip.partial_mode_supported:
            raise ValueError(
                f"--format {physical_spec.format_id} does not support partial mode"
            )
        candidates = physical_spec.strip.partial_count_range
        if requested_count is None:
            return cls(FrameCountMode.AUTO, None, candidates)
        if requested_count not in candidates:
            allowed = f"1..{physical_spec.strip.default_count}"
            raise ValueError(
                f"--format {physical_spec.format_id} partial mode allows "
                f"--count values: {allowed}"
            )
        return cls(FrameCountMode.EXPLICIT, requested_count, (requested_count,))


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
        if any(
            count > self.physical_spec.strip.default_count
            for count in self.count_request.candidate_counts
        ):
            raise ValueError("frame-count candidates exceed the format maximum")
        if not self.scan_canvas.profiles:
            raise ValueError(
                "detection configuration requires scan-canvas profiles"
            )

    @property
    def detector_kind(self) -> str:
        return "bounded_safe_crop_grid"

    @property
    def configuration_id(self) -> str:
        count_identity = (
            self.count_request.mode.value
            + ":"
            + ",".join(str(value) for value in self.count_request.candidate_counts)
        )
        return (
            f"detection:{self.physical_spec.format_id}:{self.strip_mode}:"
            f"count:{count_identity}"
        )
