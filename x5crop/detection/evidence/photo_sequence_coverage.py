from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...cache import MeasurementCache
from ...configuration.content import ContentConfiguration
from ...domain import EvidenceState
from .content.regions import content_region_runs

if TYPE_CHECKING:
    from ..physical.model import PhotoSequenceSolution


@dataclass(frozen=True)
class PhotoSequenceCoverageEvidence:
    holder_long_axis_interval: tuple[int, int]
    photo_sequence_interval: tuple[int, int]
    photo_aperture_intervals: tuple[tuple[int, int], ...]
    content_runs: tuple[tuple[int, int], ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    uncovered_content: tuple[tuple[int, int], ...] = field(init=False)

    def __post_init__(self) -> None:
        holder_start, holder_end = self.holder_long_axis_interval
        sequence_start, sequence_end = self.photo_sequence_interval
        if holder_end <= holder_start:
            raise ValueError("holder coverage interval must have positive extent")
        if not holder_start <= sequence_start < sequence_end <= holder_end:
            raise ValueError("photo sequence interval must fit the holder")
        previous_start: int | None = None
        previous_end: int | None = None
        for start, end in self.photo_aperture_intervals:
            if not sequence_start <= start < end <= sequence_end:
                raise ValueError("photo aperture intervals must fit the sequence")
            if (
                previous_start is not None
                and previous_end is not None
                and (start <= previous_start or end <= previous_end)
            ):
                raise ValueError("photo aperture intervals must be strictly monotonic")
            previous_start = start
            previous_end = end
        for start, end in self.content_runs:
            if not holder_start <= start < end <= holder_end:
                raise ValueError("content intervals must fit the holder")

        uncovered = tuple(
            run
            for run in self.content_runs
            if run[0] < sequence_start or run[1] > sequence_end
        )
        if not self.content_runs:
            state = EvidenceState.UNAVAILABLE
            reason = "content_runs_unavailable"
        elif uncovered:
            state = EvidenceState.CONTRADICTED
            reason = "content_outside_photo_sequence"
        else:
            state = EvidenceState.SUPPORTED
            reason = "content_inside_photo_sequence"
        object.__setattr__(self, "uncovered_content", uncovered)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _aperture_intervals(
    geometry: PhotoSequenceSolution,
) -> tuple[tuple[int, int], ...]:
    holder = geometry.holder_span.box
    intervals = tuple(
        (
            max(holder.left, item.box.left),
            min(holder.right, item.box.right),
        )
        for item in geometry.frame_crop_envelopes
    )
    if not intervals or any(end <= start for start, end in intervals):
        raise ValueError("photo sequence coverage requires valid apertures")
    return intervals


def photo_sequence_coverage_evidence(
    geometry: PhotoSequenceSolution,
    cache: MeasurementCache,
    content_configuration: ContentConfiguration,
) -> PhotoSequenceCoverageEvidence:
    holder = geometry.holder_span.box.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    aperture_intervals = _aperture_intervals(geometry)
    runs = content_region_runs(
        cache.content_evidence_work,
        holder,
        content_configuration=content_configuration,
    )
    return PhotoSequenceCoverageEvidence(
        holder_long_axis_interval=(holder.left, holder.right),
        photo_sequence_interval=(
            aperture_intervals[0][0],
            aperture_intervals[-1][1],
        ),
        photo_aperture_intervals=aperture_intervals,
        content_runs=tuple(runs),
    )


def photo_sequence_coverage_matches_geometry(
    geometry: PhotoSequenceSolution,
    evidence: PhotoSequenceCoverageEvidence,
) -> bool:
    holder = geometry.holder_span.box
    intervals = _aperture_intervals(geometry)
    return bool(
        evidence.holder_long_axis_interval == (holder.left, holder.right)
        and evidence.photo_sequence_interval
        == (intervals[0][0], intervals[-1][1])
        and evidence.photo_aperture_intervals == intervals
    )
