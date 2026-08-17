from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..formats import FormatSpec
from .diagnostics import DiagnosticsConfiguration
from .preprocess import PreprocessConfiguration
from .scan_canvas import ScanCanvasDetectionConfiguration


class SlotCountAuthority(str, Enum):
    MATCHED_HOLDER_DEFAULT = "matched_holder_default_count"
    USER_EXPLICIT = "user_explicit_count"


@dataclass(frozen=True)
class SlotCountRequest:
    user_count: int | None

    def __post_init__(self) -> None:
        if self.user_count is None:
            return
        if not isinstance(self.user_count, int) or isinstance(self.user_count, bool):
            raise TypeError("--count must be an integer")
        if self.user_count <= 0:
            raise ValueError("--count must be a positive integer")

    @classmethod
    def from_user_input(
        cls,
        requested_count: int | None,
    ) -> "SlotCountRequest":
        return cls(requested_count)

    @property
    def authority(self) -> SlotCountAuthority:
        return (
            SlotCountAuthority.MATCHED_HOLDER_DEFAULT
            if self.user_count is None
            else SlotCountAuthority.USER_EXPLICIT
        )


@dataclass(frozen=True)
class ResolvedSlotCount:
    matched_holder_profile_id: str
    holder_full_count: int
    output_count: int
    authority: SlotCountAuthority

    def __post_init__(self) -> None:
        if not self.matched_holder_profile_id:
            raise ValueError("resolved count requires matched-holder identity")
        if (
            not isinstance(self.holder_full_count, int)
            or isinstance(self.holder_full_count, bool)
            or not isinstance(self.output_count, int)
            or isinstance(self.output_count, bool)
        ):
            raise TypeError("resolved counts must be integers")
        if self.holder_full_count <= 0 or self.output_count <= 0:
            raise ValueError("resolved counts must be positive")
        if self.output_count > self.holder_full_count:
            raise ValueError("resolved output count exceeds holder full count")
        if self.authority == SlotCountAuthority.MATCHED_HOLDER_DEFAULT:
            if self.output_count != self.holder_full_count:
                raise ValueError("default authority requires the holder full count")
        elif self.authority == SlotCountAuthority.USER_EXPLICIT:
            pass
        else:
            raise TypeError("resolved count requires typed authority")


@dataclass(frozen=True)
class DetectionConfiguration:
    physical_spec: FormatSpec
    count_request: SlotCountRequest
    preprocess: PreprocessConfiguration
    scan_canvas: ScanCanvasDetectionConfiguration
    diagnostics: DiagnosticsConfiguration

    def __post_init__(self) -> None:
        if not self.scan_canvas.profiles:
            raise ValueError(
                "detection configuration requires scan-canvas profiles"
            )

    @property
    def detector_kind(self) -> str:
        return "v5_bounded_template_placement"

    @property
    def configuration_id(self) -> str:
        count_identity = (
            "matched_holder_default"
            if self.count_request.user_count is None
            else f"user_explicit:{self.count_request.user_count}"
        )
        return (
            f"detection:{self.physical_spec.format_id}:slot_policy:{count_identity}"
        )
