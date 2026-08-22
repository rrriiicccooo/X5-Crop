"""Selected-placement photo-group outer and W-only holder-fill facts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import Box, FiniteInterval
from .model import BoundaryAxis
from .template_placement import FormatPlacement


class HolderFillState(str, Enum):
    FILLED = "filled"
    NOT_FILLED = "not_filled"
    UNRESOLVED = "unresolved"


class HolderFillSide(str, Enum):
    LOWER = "lower"
    UPPER = "upper"


class HolderFillSideRelation(str, Enum):
    FITS = "fits"
    DOES_NOT_FIT = "does_not_fit"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class PhotoGroupOuter:
    """Long-axis bounds derived from one selected fixed-count placement."""

    placement_id: str
    lane_id: str
    axis: BoundaryAxis
    lower_px: FiniteInterval
    upper_px: FiniteInterval
    frame_width_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.placement_id
            or not self.lane_id
            or not isinstance(self.axis, BoundaryAxis)
            or not isinstance(self.lower_px, FiniteInterval)
            or not isinstance(self.upper_px, FiniteInterval)
            or not isinstance(self.frame_width_px, FiniteInterval)
            or self.lower_px.maximum > self.upper_px.minimum
            or self.frame_width_px.minimum <= 0.0
        ):
            raise ValueError("photo-group outer is invalid")


@dataclass(frozen=True)
class LaneLongAxisAuthority:
    lane_id: str
    axis: BoundaryAxis
    interval_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or not isinstance(self.axis, BoundaryAxis)
            or not isinstance(self.interval_px, FiniteInterval)
            or self.interval_px.maximum <= self.interval_px.minimum
        ):
            raise ValueError("lane long-axis authority is invalid")

    @classmethod
    def from_box(
        cls,
        lane_id: str,
        axis: BoundaryAxis,
        box: Box,
    ) -> "LaneLongAxisAuthority":
        if not isinstance(box, Box) or not box.valid():
            raise ValueError("lane long-axis authority requires a valid box")
        interval = (
            FiniteInterval(float(box.left), float(box.right))
            if axis == BoundaryAxis.X
            else FiniteInterval(float(box.top), float(box.bottom))
        )
        return cls(lane_id, axis, interval)


@dataclass(frozen=True)
class HolderFillSideFact:
    side: HolderFillSide
    free_space_px: FiniteInterval
    relation: HolderFillSideRelation

    def __post_init__(self) -> None:
        if (
            not isinstance(self.side, HolderFillSide)
            or not isinstance(self.free_space_px, FiniteInterval)
            or not isinstance(self.relation, HolderFillSideRelation)
        ):
            raise ValueError("holder-fill side fact is invalid")


@dataclass(frozen=True)
class HolderFillAssessment:
    outer: PhotoGroupOuter
    lane_authority: LaneLongAxisAuthority
    state: HolderFillState
    lower: HolderFillSideFact
    upper: HolderFillSideFact

    def __post_init__(self) -> None:
        if (
            not isinstance(self.outer, PhotoGroupOuter)
            or not isinstance(self.lane_authority, LaneLongAxisAuthority)
            or not isinstance(self.state, HolderFillState)
            or self.outer.lane_id != self.lane_authority.lane_id
            or self.outer.axis != self.lane_authority.axis
            or self.lower.side != HolderFillSide.LOWER
            or self.upper.side != HolderFillSide.UPPER
            or self.lower.relation
            != _side_relation(self.lower.free_space_px, self.outer.frame_width_px)
            or self.upper.relation
            != _side_relation(self.upper.free_space_px, self.outer.frame_width_px)
            or self.state != _state(self.lower.relation, self.upper.relation)
        ):
            raise ValueError("holder-fill assessment is inconsistent")


def photo_group_outer_from_selected_placement(
    placement: FormatPlacement,
) -> PhotoGroupOuter:
    if not isinstance(placement, FormatPlacement):
        raise TypeError("photo-group outer requires a selected placement")
    first = placement.frames[0]
    last = placement.frames[-1]
    if placement.sequence_fit.template.direction > 0:
        lower, upper = first.start, last.end
    else:
        lower, upper = last.end, first.start
    return PhotoGroupOuter(
        placement_id=placement.placement_id,
        lane_id=placement.lane_id,
        axis=placement.width_axis,
        lower_px=lower.full_position_interval_px,
        upper_px=upper.full_position_interval_px,
        frame_width_px=(
            placement.source_scan_geometry.width_state.extent_projection_px()
        ),
    )


def _side_relation(
    free_space_px: FiniteInterval,
    width_px: FiniteInterval,
) -> HolderFillSideRelation:
    if free_space_px.minimum >= width_px.maximum:
        return HolderFillSideRelation.FITS
    if free_space_px.maximum < width_px.minimum:
        return HolderFillSideRelation.DOES_NOT_FIT
    return HolderFillSideRelation.UNRESOLVED


def _state(
    lower: HolderFillSideRelation,
    upper: HolderFillSideRelation,
) -> HolderFillState:
    if HolderFillSideRelation.FITS in (lower, upper):
        return HolderFillState.NOT_FILLED
    if lower == upper == HolderFillSideRelation.DOES_NOT_FIT:
        return HolderFillState.FILLED
    return HolderFillState.UNRESOLVED


def assess_holder_fill_state(
    outer: PhotoGroupOuter,
    lane_authority: LaneLongAxisAuthority,
) -> HolderFillAssessment:
    """Classify fill after selection; no gap and no placement search."""

    if outer.lane_id != lane_authority.lane_id or outer.axis != lane_authority.axis:
        raise ValueError("holder-fill authorities disagree")
    lane = lane_authority.interval_px
    lower_space = FiniteInterval(
        outer.lower_px.minimum - lane.minimum,
        outer.lower_px.maximum - lane.minimum,
    )
    upper_space = FiniteInterval(
        lane.maximum - outer.upper_px.maximum,
        lane.maximum - outer.upper_px.minimum,
    )
    lower = HolderFillSideFact(
        HolderFillSide.LOWER,
        lower_space,
        _side_relation(lower_space, outer.frame_width_px),
    )
    upper = HolderFillSideFact(
        HolderFillSide.UPPER,
        upper_space,
        _side_relation(upper_space, outer.frame_width_px),
    )
    return HolderFillAssessment(
        outer,
        lane_authority,
        _state(lower.relation, upper.relation),
        lower,
        upper,
    )
