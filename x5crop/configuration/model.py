from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..formats import FormatSpec
from ..strip_modes import FULL, PARTIAL
from .diagnostics import DiagnosticsConfiguration
from .preprocess import PreprocessConfiguration
from .scan_canvas import ScanCanvasDetectionConfiguration


class SlotCountAuthority(str, Enum):
    MATCHED_HOLDER_FULL_COUNT = "matched_holder_full_count"
    USER_EXPLICIT_PARTIAL_COUNT = "user_explicit_partial_count"


class HolderLayoutAuthority(str, Enum):
    USER_CONFIRMED_FILLED_HOLDER_LAYOUT = (
        "user_confirmed_filled_holder_layout"
    )
    USER_CONFIRMED_NONFILLING_LAYOUT = "user_confirmed_nonfilling_layout"


@dataclass(frozen=True)
class SlotCountRequest:
    strip_mode: str
    user_count: int | None

    def __post_init__(self) -> None:
        if self.strip_mode == FULL:
            if self.user_count is not None:
                raise ValueError("full mode must not carry --count")
            return
        if self.strip_mode != PARTIAL:
            raise ValueError(f"unsupported strip mode: {self.strip_mode}")
        if self.user_count is None:
            raise ValueError("partial mode requires --count")
        if self.user_count <= 0:
            raise ValueError("partial --count must be a positive integer")

    @classmethod
    def from_user_input(
        cls,
        strip_mode: str,
        requested_count: int | None,
    ) -> "SlotCountRequest":
        return cls(strip_mode, requested_count)

    @property
    def holder_layout_authority(self) -> HolderLayoutAuthority:
        return (
            HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
            if self.strip_mode == FULL
            else HolderLayoutAuthority.USER_CONFIRMED_NONFILLING_LAYOUT
        )


@dataclass(frozen=True)
class ResolvedSlotCount:
    matched_holder_profile_id: str
    full_count: int
    output_count: int
    authority: SlotCountAuthority
    holder_layout_authority: HolderLayoutAuthority

    def __post_init__(self) -> None:
        if not self.matched_holder_profile_id:
            raise ValueError("resolved count requires matched-holder identity")
        if self.full_count <= 0 or self.output_count <= 0:
            raise ValueError("resolved counts must be positive")
        if self.output_count > self.full_count:
            raise ValueError("resolved output count exceeds holder full count")
        if self.authority == SlotCountAuthority.MATCHED_HOLDER_FULL_COUNT:
            if (
                self.output_count != self.full_count
                or self.holder_layout_authority
                != HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
            ):
                raise ValueError("full authority requires the holder full count")
        elif self.authority == SlotCountAuthority.USER_EXPLICIT_PARTIAL_COUNT:
            # Partial describes layout, not merely a count comparison.  A
            # non-filling strip may contain the holder's full_count while
            # remaining freely phased along the holder.
            if (
                self.holder_layout_authority
                != HolderLayoutAuthority.USER_CONFIRMED_NONFILLING_LAYOUT
            ):
                raise ValueError("partial authority requires a non-filling layout")
        else:
            raise TypeError("resolved count requires typed authority")


@dataclass(frozen=True)
class DetectionConfiguration:
    physical_spec: FormatSpec
    strip_mode: str
    count_request: SlotCountRequest
    preprocess: PreprocessConfiguration
    scan_canvas: ScanCanvasDetectionConfiguration
    diagnostics: DiagnosticsConfiguration

    def __post_init__(self) -> None:
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError(f"unsupported strip mode: {self.strip_mode}")
        if self.count_request.strip_mode != self.strip_mode:
            raise ValueError("slot-count request and strip mode disagree")
        if (
            self.strip_mode == PARTIAL
            and not self.physical_spec.partial_mode_supported
        ):
            raise ValueError(
                f"--format {self.physical_spec.format_id} does not support "
                "partial mode"
            )
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
            "matched_holder_full_count"
            if self.strip_mode == FULL
            else f"user_explicit:{self.count_request.user_count}"
        )
        return (
            f"detection:{self.physical_spec.format_id}:{self.strip_mode}:"
            f"slot_policy:{count_identity}"
        )
