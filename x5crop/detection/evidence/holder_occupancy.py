from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ...formats import FormatSpec
from ..physical.frame_dimensions import FrameDimensionEvidence
from ...domain import (
    BoundarySide,
    EvidenceState,
    HolderSafetyEnvelope,
    PixelInterval,
)
from ..physical.model import FrameSlot, SeparatorBandAssignment
from .frame_coverage import FrameCoverageEvidence


@dataclass(frozen=True)
class StripCompletenessEvidence:
    count: int
    nominal_count: int
    valid_frame_slot_count: int
    resolved_internal_boundary_count: int
    independent_separator_count: int
    frame_count_complete: bool = field(init=False)
    frame_sequence_complete: bool = field(init=False)
    expected_internal_boundary_count: int = field(init=False)

    def __post_init__(self) -> None:
        if min(self.count, self.nominal_count) <= 0:
            raise ValueError("strip counts must be positive")
        expected = self.count - 1
        if not 0 <= self.valid_frame_slot_count <= self.count:
            raise ValueError("valid frame-slot count must fit the candidate count")
        if not 0 <= self.resolved_internal_boundary_count <= expected:
            raise ValueError("resolved boundaries must fit the candidate count")
        if not 0 <= self.independent_separator_count <= self.resolved_internal_boundary_count:
            raise ValueError("independent separators must resolve candidate boundaries")
        frame_count_complete = self.count == self.nominal_count
        object.__setattr__(self, "frame_count_complete", frame_count_complete)
        object.__setattr__(
            self,
            "frame_sequence_complete",
            bool(
                frame_count_complete
                and self.valid_frame_slot_count == self.count
                and self.resolved_internal_boundary_count == expected
            ),
        )
        object.__setattr__(self, "expected_internal_boundary_count", expected)


class HolderOccupancyState(str, Enum):
    FILLED = "filled"
    UNDERFILLED = "underfilled"
    UNAVAILABLE = "unavailable"


def _side_occupancy(
    holder_boundary: PixelInterval,
    sequence_boundary: PixelInterval,
    *,
    leading: bool,
) -> tuple[HolderOccupancyState, PixelInterval]:
    slack = (
        sequence_boundary.minus(holder_boundary)
        if leading
        else holder_boundary.minus(sequence_boundary)
    )
    if holder_boundary.intersects(sequence_boundary):
        return HolderOccupancyState.FILLED, slack
    if slack.minimum > 0.0:
        return HolderOccupancyState.UNDERFILLED, slack
    return HolderOccupancyState.UNAVAILABLE, slack


@dataclass(frozen=True)
class HolderOccupancyEvidence:
    strip_completeness: StripCompletenessEvidence
    content_support_available: bool
    frame_coverage_state: EvidenceState
    frame_dimension_state: EvidenceState
    complete_strip_can_be_underfilled: bool
    holder_safety: HolderSafetyEnvelope
    sequence_leading_boundary: PixelInterval
    sequence_trailing_boundary: PixelInterval
    observed_sequence_span_px: PixelInterval = field(init=False)
    leading_slack_px: PixelInterval | None = field(init=False)
    trailing_slack_px: PixelInterval | None = field(init=False)
    holder_fill_ratio: PixelInterval | None = field(init=False)
    occupancy_state: HolderOccupancyState = field(init=False)
    complete_underfilled_strip: bool = field(init=False)

    def __post_init__(self) -> None:
        sequence_span = self.sequence_trailing_boundary.minus(
            self.sequence_leading_boundary
        )
        if sequence_span.minimum <= 0.0:
            raise ValueError("frame sequence occupancy requires positive extent")
        object.__setattr__(self, "observed_sequence_span_px", sequence_span)

        leading_holder = self.holder_safety.boundary(BoundarySide.LEADING)
        trailing_holder = self.holder_safety.boundary(BoundarySide.TRAILING)
        if leading_holder is None or trailing_holder is None:
            object.__setattr__(self, "leading_slack_px", None)
            object.__setattr__(self, "trailing_slack_px", None)
            object.__setattr__(self, "holder_fill_ratio", None)
            object.__setattr__(
                self,
                "occupancy_state",
                HolderOccupancyState.UNAVAILABLE,
            )
        else:
            leading_state, leading_slack = _side_occupancy(
                leading_holder.position,
                self.sequence_leading_boundary,
                leading=True,
            )
            trailing_state, trailing_slack = _side_occupancy(
                trailing_holder.position,
                self.sequence_trailing_boundary,
                leading=False,
            )
            holder_span = trailing_holder.position.minus(leading_holder.position)
            if holder_span.minimum <= 0.0:
                raise ValueError("holder occupancy boundaries must be ordered")
            if HolderOccupancyState.UNAVAILABLE in {leading_state, trailing_state}:
                occupancy_state = HolderOccupancyState.UNAVAILABLE
            elif HolderOccupancyState.UNDERFILLED in {leading_state, trailing_state}:
                occupancy_state = HolderOccupancyState.UNDERFILLED
            else:
                occupancy_state = HolderOccupancyState.FILLED
            object.__setattr__(self, "leading_slack_px", leading_slack)
            object.__setattr__(self, "trailing_slack_px", trailing_slack)
            object.__setattr__(
                self,
                "holder_fill_ratio",
                PixelInterval(
                    sequence_span.minimum / holder_span.maximum,
                    sequence_span.maximum / holder_span.minimum,
                ),
            )
            object.__setattr__(self, "occupancy_state", occupancy_state)
        object.__setattr__(
            self,
            "complete_underfilled_strip",
            bool(
                self.complete_strip_can_be_underfilled
                and self.strip_completeness.frame_sequence_complete
                and self.content_support_available
                and self.frame_coverage_state == EvidenceState.SUPPORTED
                and self.frame_dimension_state == EvidenceState.SUPPORTED
                and self.occupancy_state == HolderOccupancyState.UNDERFILLED
            ),
        )


def strip_completeness_evidence(
    *,
    count: int,
    frame_slots: tuple[FrameSlot, ...],
    separator_assignments: tuple[SeparatorBandAssignment, ...],
    physical_spec: FormatSpec,
) -> StripCompletenessEvidence:
    valid_frame_slot_count = len(frame_slots)
    resolved_boundaries = sum(
        left.trailing.geometry_resolved
        and right.leading.geometry_resolved
        for left, right in zip(frame_slots, frame_slots[1:])
    )
    return StripCompletenessEvidence(
        count=int(count),
        nominal_count=int(physical_spec.strip.default_count),
        valid_frame_slot_count=int(valid_frame_slot_count),
        resolved_internal_boundary_count=int(resolved_boundaries),
        independent_separator_count=len(separator_assignments),
    )


def holder_occupancy_evidence(
    *,
    count: int,
    holder_safety: HolderSafetyEnvelope,
    frame_slots: tuple[FrameSlot, ...],
    separator_assignments: tuple[SeparatorBandAssignment, ...],
    physical_spec: FormatSpec,
    content_support_available: bool,
    frame_coverage: FrameCoverageEvidence,
    frame_dimensions: FrameDimensionEvidence,
) -> HolderOccupancyEvidence:
    if not frame_slots:
        raise ValueError("holder occupancy requires frame slots")
    completeness = strip_completeness_evidence(
        count=count,
        frame_slots=frame_slots,
        separator_assignments=separator_assignments,
        physical_spec=physical_spec,
    )
    return HolderOccupancyEvidence(
        strip_completeness=completeness,
        content_support_available=content_support_available,
        frame_coverage_state=frame_coverage.state,
        frame_dimension_state=frame_dimensions.state,
        complete_strip_can_be_underfilled=(
            physical_spec.strip.complete_strip_can_be_underfilled
        ),
        holder_safety=holder_safety,
        sequence_leading_boundary=frame_slots[0].leading.position,
        sequence_trailing_boundary=frame_slots[-1].trailing.position,
    )
