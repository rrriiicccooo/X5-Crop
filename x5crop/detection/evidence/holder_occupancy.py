from __future__ import annotations

from dataclasses import dataclass, field
import math

from ...formats import FormatPhysicalSpec
from ...geometry.layout import is_horizontal_layout
from ...units import ScanCalibration
from ..physical.photo_size import FrameDimensionEvidence
from ...domain import (
    Box,
    EvidenceState,
    FrameBoundary,
    HolderSpan,
    SeparatorAssignment,
    VisibleSequenceSpan,
)
from .frame_coverage import FrameCoverageEvidence


@dataclass(frozen=True)
class StripCompletenessEvidence:
    count: int
    nominal_count: int
    valid_frame_count: int
    resolved_boundary_count: int
    independent_separator_count: int
    frame_count_complete: bool = field(init=False)
    frame_sequence_complete: bool = field(init=False)
    expected_internal_boundary_count: int = field(init=False)

    def __post_init__(self) -> None:
        if min(self.count, self.nominal_count) <= 0:
            raise ValueError("strip counts must be positive")
        expected = self.count - 1
        if not 0 <= self.valid_frame_count <= self.count:
            raise ValueError("valid frame count must fit the candidate count")
        if not 0 <= self.resolved_boundary_count <= expected:
            raise ValueError("resolved boundaries must fit the candidate count")
        if not 0 <= self.independent_separator_count <= self.resolved_boundary_count:
            raise ValueError("independent separators must resolve candidate boundaries")
        frame_count_complete = self.count == self.nominal_count
        object.__setattr__(self, "frame_count_complete", frame_count_complete)
        object.__setattr__(
            self,
            "frame_sequence_complete",
            bool(
                frame_count_complete
                and self.valid_frame_count == self.count
                and self.resolved_boundary_count == expected
            ),
        )
        object.__setattr__(self, "expected_internal_boundary_count", expected)


@dataclass(frozen=True)
class HolderOccupancyEvidence:
    strip_completeness: StripCompletenessEvidence
    content_support_available: bool
    frame_coverage_state: EvidenceState
    frame_dimension_state: EvidenceState
    complete_strip_can_be_underfilled: bool
    holder_span: HolderSpan
    visible_sequence_span: VisibleSequenceSpan
    long_axis: str
    long_axis_px_per_mm: float | None
    observed_sequence_span_px: float = field(init=False)
    leading_slack_px: float = field(init=False)
    trailing_slack_px: float = field(init=False)
    leading_slack_mm: float | None = field(init=False)
    trailing_slack_mm: float | None = field(init=False)
    holder_fill_ratio: float = field(init=False)
    underfilled: bool = field(init=False)
    complete_underfilled_strip: bool = field(init=False)
    calibration_used: bool = field(init=False)

    def __post_init__(self) -> None:
        if self.long_axis not in {"x", "y"}:
            raise ValueError("holder occupancy requires a physical long axis")
        scale = self.long_axis_px_per_mm
        if scale is not None and (not math.isfinite(scale) or scale <= 0.0):
            raise ValueError("holder occupancy calibration must be finite and positive")

        holder = self.holder_span.box
        sequence = self.visible_sequence_span.box
        if not (
            holder.left <= sequence.left < sequence.right <= holder.right
            and holder.top <= sequence.top < sequence.bottom <= holder.bottom
        ):
            raise ValueError("visible sequence span must be contained by holder span")
        if self.long_axis == "x":
            holder_start, holder_end = holder.left, holder.right
            sequence_start, sequence_end = sequence.left, sequence.right
        else:
            holder_start, holder_end = holder.top, holder.bottom
            sequence_start, sequence_end = sequence.top, sequence.bottom

        holder_length = float(holder_end - holder_start)
        sequence_length = float(sequence_end - sequence_start)
        leading_slack = float(sequence_start - holder_start)
        trailing_slack = float(holder_end - sequence_end)
        underfilled = leading_slack > 0.0 or trailing_slack > 0.0
        object.__setattr__(self, "observed_sequence_span_px", sequence_length)
        object.__setattr__(self, "leading_slack_px", leading_slack)
        object.__setattr__(self, "trailing_slack_px", trailing_slack)
        object.__setattr__(
            self,
            "leading_slack_mm",
            None if scale is None else leading_slack / scale,
        )
        object.__setattr__(
            self,
            "trailing_slack_mm",
            None if scale is None else trailing_slack / scale,
        )
        object.__setattr__(self, "holder_fill_ratio", sequence_length / holder_length)
        object.__setattr__(self, "underfilled", underfilled)
        object.__setattr__(
            self,
            "complete_underfilled_strip",
            bool(
                self.complete_strip_can_be_underfilled
                and self.strip_completeness.frame_sequence_complete
                and self.content_support_available
                and self.frame_coverage_state == EvidenceState.SUPPORTED
                and self.frame_dimension_state == EvidenceState.SUPPORTED
                and underfilled
            ),
        )
        object.__setattr__(self, "calibration_used", scale is not None)


def strip_completeness_evidence(
    *,
    count: int,
    frames: tuple[Box, ...],
    frame_boundaries: tuple[FrameBoundary, ...],
    separator_assignments: tuple[SeparatorAssignment, ...],
    physical_spec: FormatPhysicalSpec,
) -> StripCompletenessEvidence:
    valid_frame_count = sum(1 for frame in frames if frame.valid())
    return StripCompletenessEvidence(
        count=int(count),
        nominal_count=int(physical_spec.default_count),
        valid_frame_count=int(valid_frame_count),
        resolved_boundary_count=len(frame_boundaries),
        independent_separator_count=sum(
            assignment.used_for_boundary and assignment.independent
            for assignment in separator_assignments
        ),
    )


def holder_occupancy_evidence(
    *,
    layout: str,
    count: int,
    holder_span: HolderSpan,
    visible_sequence_span: VisibleSequenceSpan,
    frames: tuple[Box, ...],
    frame_boundaries: tuple[FrameBoundary, ...],
    separator_assignments: tuple[SeparatorAssignment, ...],
    physical_spec: FormatPhysicalSpec,
    content_support_available: bool,
    frame_coverage: FrameCoverageEvidence,
    frame_dimensions: FrameDimensionEvidence,
    calibration: ScanCalibration,
) -> HolderOccupancyEvidence:
    completeness = strip_completeness_evidence(
        count=count,
        frames=frames,
        frame_boundaries=frame_boundaries,
        separator_assignments=separator_assignments,
        physical_spec=physical_spec,
    )
    long_axis = "x" if is_horizontal_layout(layout) else "y"
    return HolderOccupancyEvidence(
        strip_completeness=completeness,
        content_support_available=content_support_available,
        frame_coverage_state=frame_coverage.state,
        frame_dimension_state=frame_dimensions.state,
        complete_strip_can_be_underfilled=(
            physical_spec.complete_strip_can_be_underfilled
        ),
        holder_span=holder_span,
        visible_sequence_span=visible_sequence_span,
        long_axis=long_axis,
        long_axis_px_per_mm=(
            calibration.px_per_mm(long_axis) if calibration.trusted else None
        ),
    )
