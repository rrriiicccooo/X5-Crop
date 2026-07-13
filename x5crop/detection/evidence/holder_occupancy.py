from __future__ import annotations

from dataclasses import dataclass, field

from ...formats import FormatPhysicalSpec
from ..physical.photo_size import FrameDimensionEvidence
from ...domain import (
    Box,
    EvidenceState,
    HolderSpan,
    PhotoAperture,
    SeparatorBandAssignment,
)
from .photo_aperture_coverage import PhotoApertureCoverageEvidence


@dataclass(frozen=True)
class StripCompletenessEvidence:
    count: int
    nominal_count: int
    valid_aperture_count: int
    resolved_inter_photo_boundary_count: int
    independent_separator_count: int
    photo_count_complete: bool = field(init=False)
    aperture_sequence_complete: bool = field(init=False)
    expected_inter_photo_boundary_count: int = field(init=False)

    def __post_init__(self) -> None:
        if min(self.count, self.nominal_count) <= 0:
            raise ValueError("strip counts must be positive")
        expected = self.count - 1
        if not 0 <= self.valid_aperture_count <= self.count:
            raise ValueError("valid aperture count must fit the candidate count")
        if not 0 <= self.resolved_inter_photo_boundary_count <= expected:
            raise ValueError("resolved boundaries must fit the candidate count")
        if not 0 <= self.independent_separator_count <= self.resolved_inter_photo_boundary_count:
            raise ValueError("independent separators must resolve candidate boundaries")
        photo_count_complete = self.count == self.nominal_count
        object.__setattr__(self, "photo_count_complete", photo_count_complete)
        object.__setattr__(
            self,
            "aperture_sequence_complete",
            bool(
                photo_count_complete
                and self.valid_aperture_count == self.count
                and self.resolved_inter_photo_boundary_count == expected
            ),
        )
        object.__setattr__(self, "expected_inter_photo_boundary_count", expected)


@dataclass(frozen=True)
class HolderOccupancyEvidence:
    strip_completeness: StripCompletenessEvidence
    content_support_available: bool
    photo_aperture_coverage_state: EvidenceState
    frame_dimension_state: EvidenceState
    complete_strip_can_be_underfilled: bool
    holder_span: HolderSpan
    photo_sequence_envelope: Box
    observed_sequence_span_px: float = field(init=False)
    leading_slack_px: float = field(init=False)
    trailing_slack_px: float = field(init=False)
    holder_fill_ratio: float = field(init=False)
    underfilled: bool = field(init=False)
    complete_underfilled_strip: bool = field(init=False)

    def __post_init__(self) -> None:
        holder = self.holder_span.box
        sequence = self.photo_sequence_envelope
        if not (
            holder.left <= sequence.left < sequence.right <= holder.right
            and holder.top <= sequence.top < sequence.bottom <= holder.bottom
        ):
            raise ValueError("photo sequence envelope must be contained by holder span")
        holder_start, holder_end = holder.left, holder.right
        sequence_start, sequence_end = sequence.left, sequence.right
        holder_length = float(holder_end - holder_start)
        sequence_length = float(sequence_end - sequence_start)
        leading_slack = float(sequence_start - holder_start)
        trailing_slack = float(holder_end - sequence_end)
        underfilled = leading_slack > 0.0 or trailing_slack > 0.0
        object.__setattr__(self, "observed_sequence_span_px", sequence_length)
        object.__setattr__(self, "leading_slack_px", leading_slack)
        object.__setattr__(self, "trailing_slack_px", trailing_slack)
        object.__setattr__(self, "holder_fill_ratio", sequence_length / holder_length)
        object.__setattr__(self, "underfilled", underfilled)
        object.__setattr__(
            self,
            "complete_underfilled_strip",
            bool(
                self.complete_strip_can_be_underfilled
                and self.strip_completeness.aperture_sequence_complete
                and self.content_support_available
                and self.photo_aperture_coverage_state == EvidenceState.SUPPORTED
                and self.frame_dimension_state == EvidenceState.SUPPORTED
                and underfilled
            ),
        )


def strip_completeness_evidence(
    *,
    count: int,
    photo_apertures: tuple[PhotoAperture, ...],
    separator_assignments: tuple[SeparatorBandAssignment, ...],
    physical_spec: FormatPhysicalSpec,
) -> StripCompletenessEvidence:
    valid_aperture_count = len(photo_apertures)
    resolved_boundaries = sum(
        left.trailing.independently_observed
        and right.leading.independently_observed
        for left, right in zip(photo_apertures, photo_apertures[1:])
    )
    return StripCompletenessEvidence(
        count=int(count),
        nominal_count=int(physical_spec.default_count),
        valid_aperture_count=int(valid_aperture_count),
        resolved_inter_photo_boundary_count=int(resolved_boundaries),
        independent_separator_count=sum(
            assignment.independent
            for assignment in separator_assignments
        ),
    )


def holder_occupancy_evidence(
    *,
    count: int,
    holder_span: HolderSpan,
    photo_apertures: tuple[PhotoAperture, ...],
    separator_assignments: tuple[SeparatorBandAssignment, ...],
    physical_spec: FormatPhysicalSpec,
    content_support_available: bool,
    photo_aperture_coverage: PhotoApertureCoverageEvidence,
    frame_dimensions: FrameDimensionEvidence,
) -> HolderOccupancyEvidence:
    completeness = strip_completeness_evidence(
        count=count,
        photo_apertures=photo_apertures,
        separator_assignments=separator_assignments,
        physical_spec=physical_spec,
    )
    return HolderOccupancyEvidence(
        strip_completeness=completeness,
        content_support_available=content_support_available,
        photo_aperture_coverage_state=photo_aperture_coverage.state,
        frame_dimension_state=frame_dimensions.state,
        complete_strip_can_be_underfilled=(
            physical_spec.complete_strip_can_be_underfilled
        ),
        holder_span=holder_span,
        photo_sequence_envelope=Box(
            min(item.frame_crop_envelope.box.left for item in photo_apertures),
            min(item.frame_crop_envelope.box.top for item in photo_apertures),
            max(item.frame_crop_envelope.box.right for item in photo_apertures),
            max(item.frame_crop_envelope.box.bottom for item in photo_apertures),
        ),
    )
