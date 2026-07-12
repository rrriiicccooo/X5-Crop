from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box
from ...formats import FormatPhysicalSpec
from ...geometry.layout import is_horizontal_layout
from ...units import ScanCalibration
from ..physical.photo_size import FrameDimensionEvidence
from x5crop.domain import VisibleSequenceSpan, HolderSpan
from x5crop.domain import FrameBoundary, SeparatorAssignment
from .frame_coverage import FrameCoverageEvidence
from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class StripCompletenessEvidence:
    frame_count_complete: bool
    frame_sequence_complete: bool
    count: int
    nominal_count: int
    valid_frame_count: int
    expected_internal_boundary_count: int
    resolved_boundary_count: int
    independent_separator_count: int

@dataclass(frozen=True)
class HolderOccupancyEvidence:
    state: EvidenceState
    strip_completeness: StripCompletenessEvidence
    nominal_frame_total_mm: float | None
    observed_sequence_span_px: float
    leading_slack_px: float
    trailing_slack_px: float
    leading_slack_mm: float | None
    trailing_slack_mm: float | None
    holder_fill_ratio: float
    occupancy_status: str
    complete_underfilled_strip: bool
    content_support_available: bool
    frame_coverage_state: EvidenceState
    photo_dimensions_stable: bool
    holder_span: HolderSpan
    visible_sequence_span: VisibleSequenceSpan
    calibration_used: bool

def strip_completeness_evidence(
    *,
    count: int,
    frames: tuple[Box, ...],
    frame_boundaries: tuple[FrameBoundary, ...],
    separator_assignments: tuple[SeparatorAssignment, ...],
    physical_spec: FormatPhysicalSpec,
) -> StripCompletenessEvidence:
    valid_frame_count = sum(1 for frame in frames if frame.valid())
    frame_count_complete = int(count) == int(physical_spec.default_count)
    return StripCompletenessEvidence(
        frame_count_complete=frame_count_complete,
        frame_sequence_complete=bool(
            frame_count_complete
            and valid_frame_count == int(count)
            and len(frame_boundaries) == max(0, int(count) - 1)
        ),
        count=int(count),
        nominal_count=int(physical_spec.default_count),
        valid_frame_count=int(valid_frame_count),
        expected_internal_boundary_count=max(0, int(count) - 1),
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
    holder = holder_span.box
    sequence_box = visible_sequence_span.box
    leading_slack_px = max(0.0, float(sequence_box.left - holder.left))
    trailing_slack_px = max(0.0, float(holder.right - sequence_box.right))
    observed_span_px = float(sequence_box.width)
    holder_fill_ratio = observed_span_px / float(max(1, holder.width))
    long_axis = "x" if is_horizontal_layout(layout) else "y"
    px_per_mm = calibration.px_per_mm(long_axis) if calibration.trusted else None
    leading_slack_mm = (
        None
        if px_per_mm is None
        else leading_slack_px / float(px_per_mm)
    )
    trailing_slack_mm = (
        None
        if px_per_mm is None
        else trailing_slack_px / float(px_per_mm)
    )
    photo_dimensions_stable = frame_dimensions.state == EvidenceState.SUPPORTED
    complete_underfilled = bool(
        physical_spec.complete_strip_can_be_underfilled
        and completeness.frame_sequence_complete
        and content_support_available
        and frame_coverage.state == EvidenceState.SUPPORTED
        and photo_dimensions_stable
        and (leading_slack_px > 0.0 or trailing_slack_px > 0.0)
    )
    occupancy_status = (
        "underfilled"
        if leading_slack_px > 0.0 or trailing_slack_px > 0.0
        else "filled"
    )
    return HolderOccupancyEvidence(
        state=EvidenceState.SUPPORTED,
        strip_completeness=completeness,
        nominal_frame_total_mm=(
            float(count) * float(physical_spec.nominal_frame_size_mm.width_mm)
            if count > 0
            else None
        ),
        observed_sequence_span_px=observed_span_px,
        leading_slack_px=leading_slack_px,
        trailing_slack_px=trailing_slack_px,
        leading_slack_mm=leading_slack_mm,
        trailing_slack_mm=trailing_slack_mm,
        holder_fill_ratio=holder_fill_ratio,
        occupancy_status=occupancy_status,
        complete_underfilled_strip=complete_underfilled,
        content_support_available=content_support_available,
        frame_coverage_state=frame_coverage.state,
        photo_dimensions_stable=photo_dimensions_stable,
        holder_span=holder_span,
        visible_sequence_span=visible_sequence_span,
        calibration_used=bool(calibration.trusted and px_per_mm is not None),
    )
