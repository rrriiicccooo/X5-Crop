from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box, SeparatorBandObservation
from ...formats import FormatPhysicalSpec
from ...units import ScanCalibration
from ..physical.photo_size import FrameDimensionEvidence
from ..physical.spans import FilmSpan, HolderSpan
from .frame_coverage import FrameCoverageEvidence
from .state import EvidenceState


@dataclass(frozen=True)
class StripCompletenessEvidence:
    frame_count_complete: bool
    frame_sequence_complete: bool
    count: int
    nominal_count: int
    valid_frame_count: int
    expected_separator_count: int
    observed_separator_count: int

@dataclass(frozen=True)
class HolderOccupancyEvidence:
    state: EvidenceState
    strip_completeness: StripCompletenessEvidence
    expected_film_span_mm: float | None
    observed_film_span_px: float
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
    film_span: FilmSpan
    calibration_used: bool

def strip_completeness_evidence(
    *,
    count: int,
    work_frames: tuple[Box, ...],
    separators: tuple[SeparatorBandObservation, ...],
    physical_spec: FormatPhysicalSpec,
) -> StripCompletenessEvidence:
    valid_frame_count = sum(1 for frame in work_frames if frame.valid())
    frame_count_complete = int(count) == int(physical_spec.default_count)
    return StripCompletenessEvidence(
        frame_count_complete=frame_count_complete,
        frame_sequence_complete=bool(
            frame_count_complete and valid_frame_count == int(count)
        ),
        count=int(count),
        nominal_count=int(physical_spec.default_count),
        valid_frame_count=int(valid_frame_count),
        expected_separator_count=max(0, int(count) - 1),
        observed_separator_count=len(separators),
    )


def holder_occupancy_evidence(
    *,
    layout: str,
    strip_mode: str,
    count: int,
    holder_span: HolderSpan,
    film_span: FilmSpan,
    work_frames: tuple[Box, ...],
    separators: tuple[SeparatorBandObservation, ...],
    physical_spec: FormatPhysicalSpec,
    content_support_available: bool,
    frame_coverage: FrameCoverageEvidence,
    frame_dimensions: FrameDimensionEvidence,
    calibration: ScanCalibration,
) -> HolderOccupancyEvidence:
    completeness = strip_completeness_evidence(
        count=count,
        work_frames=work_frames,
        separators=separators,
        physical_spec=physical_spec,
    )
    holder = holder_span.box
    film = film_span.box
    leading_slack_px = max(0.0, float(film.left - holder.left))
    trailing_slack_px = max(0.0, float(holder.right - film.right))
    observed_span_px = float(film.width)
    holder_fill_ratio = observed_span_px / float(max(1, holder.width))
    long_axis = "x" if layout == "horizontal" else "y"
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
        and strip_mode == "partial"
        and completeness.frame_sequence_complete
        and content_support_available
        and frame_coverage.state == EvidenceState.SUPPORTED
        and photo_dimensions_stable
        and (leading_slack_px > 0.0 or trailing_slack_px > 0.0)
    )
    if strip_mode == "full":
        occupancy_status = "filled"
    elif complete_underfilled:
        occupancy_status = "underfilled"
    else:
        occupancy_status = "unknown"
    state = (
        EvidenceState.SUPPORTED
        if occupancy_status in {"filled", "underfilled"}
        else EvidenceState.UNAVAILABLE
    )
    return HolderOccupancyEvidence(
        state=state,
        strip_completeness=completeness,
        expected_film_span_mm=(
            float(count) * float(physical_spec.nominal_frame_size_mm.width_mm)
            if count > 0
            else None
        ),
        observed_film_span_px=observed_span_px,
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
        film_span=film_span,
        calibration_used=bool(calibration.trusted and px_per_mm is not None),
    )
