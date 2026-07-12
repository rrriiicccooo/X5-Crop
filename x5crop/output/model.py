from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box, CropEnvelope, FrameBoundaryReference


@dataclass(frozen=True)
class AxisBleedParameters:
    long_axis: int
    short_axis: int

    def __post_init__(self) -> None:
        if self.long_axis < 0 or self.short_axis < 0:
            raise ValueError("output bleed must be non-negative")


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
        if self.right_frame_index != self.left_frame_index + 1:
            raise ValueError("overlap protection applies to adjacent frames")
        if self.required_px <= 0:
            raise ValueError("overlap protection must be positive")
        if not self.provenance:
            raise ValueError("overlap requirement requires provenance")


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
        if (
            self.left_frame_index < 0
            or self.right_frame_index != self.left_frame_index + 1
        ):
            raise ValueError("overlap protection applies to adjacent frames")
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
        if any(
            side.leading_px < self.user_bleed.long_axis
            or side.trailing_px < self.user_bleed.long_axis
            or side.short_axis_px != self.user_bleed.short_axis
            for side in self.frame_sides
        ):
            raise ValueError("frame bleed sides must preserve user output preferences")
        protection_boundaries = tuple(
            item.boundary for item in self.overlap_protection
        )
        if len(set(protection_boundaries)) != len(protection_boundaries):
            raise ValueError("overlap protection boundaries must be unique")
        unresolved = self.unresolved_overlap_boundaries
        if len(set(unresolved)) != len(unresolved):
            raise ValueError("unresolved overlap boundaries must be unique")
        complete = {
            item.boundary for item in self.overlap_protection if item.complete
        }
        incomplete = {
            item.boundary for item in self.overlap_protection if not item.complete
        }
        unresolved_set = set(unresolved)
        if complete & unresolved_set or not incomplete.issubset(unresolved_set):
            raise ValueError("overlap protection state must match unresolved boundaries")
        if self.feasible != (not unresolved):
            raise ValueError("frame bleed feasibility must match unresolved overlap state")
        expected_reason = (
            "output_overlap_unresolved"
            if unresolved
            else "output_overlap_protected"
            if self.overlap_protection
            else "no_output_overlap"
        )
        if self.reason != expected_reason:
            raise ValueError("frame bleed reason must match its protection state")
        for item in self.overlap_protection:
            if item.right_frame_index >= len(self.frame_sides):
                raise ValueError("overlap protection references a missing frame")
            left = self.frame_sides[item.left_frame_index]
            right = self.frame_sides[item.right_frame_index]
            if (
                left.trailing_px < item.required_px
                or right.leading_px < item.required_px
            ):
                raise ValueError("frame bleed must include required overlap protection")
