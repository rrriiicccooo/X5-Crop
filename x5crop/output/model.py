from __future__ import annotations

from dataclasses import dataclass

from ..domain import AxisBleedParameters, Box, CropEnvelope


@dataclass(frozen=True)
class OutputGeometry:
    crop_envelope: CropEnvelope
    frames: tuple[Box, ...]


@dataclass(frozen=True)
class FrameOverlapRequirement:
    boundary_index: int
    left_frame_index: int
    right_frame_index: int
    required_px: int
    independently_observed: bool
    provenance: str

    def __post_init__(self) -> None:
        if self.boundary_index <= 0:
            raise ValueError("overlap boundary index must be positive")
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


@dataclass(frozen=True)
class BoundaryOverlapProtection:
    boundary_index: int
    left_frame_index: int
    right_frame_index: int
    required_px: int
    left_trailing_available_px: int
    right_leading_available_px: int
    provenance: str

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
    unresolved_overlap_boundaries: tuple[int, ...]
    feasible: bool
    reason: str
