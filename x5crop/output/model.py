from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from ..domain import (
    Box,
    FrameCropEnvelope,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingKind,
    MeasurementProvenance,
)


@dataclass(frozen=True)
class AxisBleedParameters:
    long_axis: int
    short_axis: int

    def __post_init__(self) -> None:
        if self.long_axis < 0 or self.short_axis < 0:
            raise ValueError("output bleed must be non-negative")


@dataclass(frozen=True)
class OutputGeometry:
    frame_crop_envelopes: tuple[FrameCropEnvelope, ...]
    final_boxes: tuple[Box, ...]

    def __post_init__(self) -> None:
        if len(self.frame_crop_envelopes) != len(self.final_boxes):
            raise ValueError("output geometry requires one final box per frame envelope")
        if tuple(item.frame_index for item in self.frame_crop_envelopes) != tuple(
            range(1, len(self.frame_crop_envelopes) + 1)
        ):
            raise ValueError("output frame envelopes must be complete and ordered")
        for envelope, final_box in zip(
            self.frame_crop_envelopes,
            self.final_boxes,
            strict=True,
        ):
            if not final_box.valid():
                raise ValueError("final output boxes must have positive extent")
            envelope_box = envelope.box
            if not (
                final_box.left <= envelope_box.left
                and final_box.top <= envelope_box.top
                and final_box.right >= envelope_box.right
                and final_box.bottom >= envelope_box.bottom
            ):
                raise ValueError("final output boxes must contain frame envelopes")


@dataclass(frozen=True)
class FrameOverlapRequirement:
    spacing: InterFrameSpacing
    left_frame_index: int
    right_frame_index: int

    def __post_init__(self) -> None:
        if self.left_frame_index < 0 or self.right_frame_index < 0:
            raise ValueError("overlap frame indexes must be non-negative")
        if self.right_frame_index != self.left_frame_index + 1:
            raise ValueError("overlap protection applies to adjacent frames")
        if self.spacing.kind != InterFrameSpacingKind.OVERLAP:
            raise ValueError("overlap protection requires negative spacing")

    @property
    def boundary(self) -> InterFrameBoundaryReference:
        return self.spacing.boundary

    @property
    def required_px(self) -> int:
        return max(1, int(ceil(-self.spacing.signed_width_px.minimum)))

    @property
    def physically_supported(self) -> bool:
        return self.spacing.supports_output_protection

    @property
    def provenance(self) -> MeasurementProvenance:
        return self.spacing.provenance


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
    requirement: FrameOverlapRequirement
    left_trailing_available_px: int
    right_leading_available_px: int

    def __post_init__(self) -> None:
        if min(
            self.left_trailing_available_px,
            self.right_leading_available_px,
        ) < 0:
            raise ValueError("overlap protection availability must be non-negative")

    @property
    def boundary(self) -> InterFrameBoundaryReference:
        return self.requirement.boundary

    @property
    def left_frame_index(self) -> int:
        return self.requirement.left_frame_index

    @property
    def right_frame_index(self) -> int:
        return self.requirement.right_frame_index

    @property
    def required_px(self) -> int:
        return self.requirement.required_px

    @property
    def provenance(self) -> MeasurementProvenance:
        return self.requirement.provenance

    @property
    def complete(self) -> bool:
        return bool(
            self.left_trailing_available_px >= self.required_px
            and self.right_leading_available_px >= self.required_px
        )


@dataclass(frozen=True)
class FrameBleedPlan:
    user_bleed: AxisBleedParameters
    frame_output_bounds: tuple[Box, ...]
    frame_sides: tuple[FrameSideBleed, ...]
    overlap_protection: tuple[BoundaryOverlapProtection, ...]
    unresolved_overlap_boundaries: tuple[InterFrameBoundaryReference, ...]
    feasible: bool = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        indexes = tuple(side.frame_index for side in self.frame_sides)
        if indexes != tuple(range(len(indexes))):
            raise ValueError("frame bleed plan indexes must be complete and ordered")
        if len(self.frame_output_bounds) != len(self.frame_sides) or any(
            not bound.valid() for bound in self.frame_output_bounds
        ):
            raise ValueError("frame bleed plan requires one valid output bound per frame")
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
        feasible = not unresolved
        reason = (
            "output_overlap_unresolved"
            if unresolved
            else "output_overlap_protected"
            if self.overlap_protection
            else "no_output_overlap"
        )
        object.__setattr__(self, "feasible", feasible)
        object.__setattr__(self, "reason", reason)
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
