from __future__ import annotations

from dataclasses import dataclass

from ..domain import AxisBleedParameters, Box, CropEnvelope, FrameBoundaryReference


@dataclass(frozen=True)
class OutputGeometry:
    crop_envelope: CropEnvelope
    frames: tuple[Box, ...]

    def __post_init__(self) -> None:
        envelope = self.crop_envelope.box
        for frame in self.frames:
            if not frame.valid():
                raise ValueError("output frames must have positive extent")
            if not (
                envelope.left <= frame.left
                and envelope.top <= frame.top
                and envelope.right >= frame.right
                and envelope.bottom >= frame.bottom
            ):
                raise ValueError("output frames must remain inside the crop envelope")


@dataclass(frozen=True)
class FrameOverlapRequirement:
    boundary: FrameBoundaryReference
    left_frame_index: int
    right_frame_index: int
    required_px: int
    physically_supported: bool
    provenance: str

    def __post_init__(self) -> None:
        if self.left_frame_index < 0 or self.right_frame_index < 0:
            raise ValueError("overlap frame indexes must be non-negative")
        if self.right_frame_index <= self.left_frame_index:
            raise ValueError("overlap frames must be ordered")
        if self.required_px <= 0:
            raise ValueError("overlap protection must be positive")


@dataclass(frozen=True)
class FrameSideBleed:
    frame_index: int
    leading_px: int
    trailing_px: int
    short_axis_px: int

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame bleed index must be non-negative")
        if min(self.leading_px, self.trailing_px, self.short_axis_px) < 0:
            raise ValueError("frame bleed values must be non-negative")


@dataclass(frozen=True)
class BoundaryOverlapProtection:
    boundary: FrameBoundaryReference
    left_frame_index: int
    right_frame_index: int
    required_px: int
    left_trailing_available_px: int
    right_leading_available_px: int
    provenance: str

    def __post_init__(self) -> None:
        if self.left_frame_index < 0 or self.right_frame_index <= self.left_frame_index:
            raise ValueError("overlap protection frames must be ordered")
        if self.required_px <= 0:
            raise ValueError("overlap protection requirement must be positive")
        if min(
            self.left_trailing_available_px,
            self.right_leading_available_px,
        ) < 0:
            raise ValueError("overlap protection availability must be non-negative")
        if not self.provenance:
            raise ValueError("overlap protection requires provenance")

    @property
    def complete(self) -> bool:
        return bool(
            self.left_trailing_available_px >= self.required_px
            and self.right_leading_available_px >= self.required_px
        )


@dataclass(frozen=True)
class FrameBleedPlan:
    user_bleed: AxisBleedParameters
    frame_sides: tuple[FrameSideBleed, ...]
    overlap_protection: tuple[BoundaryOverlapProtection, ...]
    unresolved_overlap_boundaries: tuple[FrameBoundaryReference, ...]
    feasible: bool
    reason: str

    def __post_init__(self) -> None:
        indexes = tuple(side.frame_index for side in self.frame_sides)
        if indexes != tuple(range(len(indexes))):
            raise ValueError("frame bleed plan indexes must be complete and ordered")
        unresolved = self.unresolved_overlap_boundaries
        if len(set(unresolved)) != len(unresolved):
            raise ValueError("unresolved overlap boundaries must be unique")
        if self.feasible != (not unresolved):
            raise ValueError("frame bleed feasibility must match unresolved overlap state")
        if not self.reason:
            raise ValueError("frame bleed plan requires a reason")
