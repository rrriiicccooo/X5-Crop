from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...cache import MeasurementCache
from ...domain import Box
from ...configuration.content import ContentConfiguration
from x5crop.domain import VisibleSequenceSpan, HolderSpan
from .content.regions import content_region_runs
from x5crop.domain import EvidenceState

if TYPE_CHECKING:
    from ..physical.model import SequenceSolution


@dataclass(frozen=True)
class FrameCoverageEvidence:
    holder_long_axis_interval: tuple[int, int]
    visible_sequence_interval: tuple[int, int]
    frame_intervals: tuple[tuple[int, int], ...]
    content_runs: tuple[tuple[int, int], ...]
    candidate_frame_count: int
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    uncovered_content: tuple[tuple[int, int], ...] = field(init=False)
    unexplained_content_region_count: int = field(init=False)

    def __post_init__(self) -> None:
        holder_start, holder_end = self.holder_long_axis_interval
        sequence_start, sequence_end = self.visible_sequence_interval
        if holder_end <= holder_start:
            raise ValueError("holder coverage interval must have positive extent")
        if not holder_start <= sequence_start < sequence_end <= holder_end:
            raise ValueError("visible sequence interval must fit the holder")
        if self.candidate_frame_count <= 0:
            raise ValueError("frame coverage requires a positive candidate count")
        for name, intervals in (
            ("frame", self.frame_intervals),
            ("content", self.content_runs),
        ):
            previous_end: int | None = None
            for start, end in intervals:
                if not holder_start <= start < end <= holder_end:
                    raise ValueError(f"{name} intervals must fit the holder")
                if previous_end is not None and start <= previous_end:
                    raise ValueError(f"{name} intervals must be canonical and disjoint")
                previous_end = end

        uncovered = tuple(
            segment
            for run in self.content_runs
            for segment in _uncovered_segments(run, self.frame_intervals)
        )
        unexplained = max(0, len(self.content_runs) - self.candidate_frame_count)
        if not self.content_runs:
            state = EvidenceState.UNAVAILABLE
            reason = "content_runs_unavailable"
        elif uncovered:
            state = EvidenceState.CONTRADICTED
            reason = "content_outside_frame_union"
        else:
            state = EvidenceState.SUPPORTED
            reason = (
                "content_runs_covered_multiple_regions"
                if unexplained
                else "content_runs_covered"
            )
        object.__setattr__(self, "uncovered_content", uncovered)
        object.__setattr__(self, "unexplained_content_region_count", unexplained)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _merged_intervals(intervals: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((start, end) for start, end in merged)


def _uncovered_segments(
    interval: tuple[int, int],
    coverage: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    cursor, end = interval
    uncovered: list[tuple[int, int]] = []
    for cover_start, cover_end in coverage:
        if cover_end <= cursor or cover_start >= end:
            continue
        if cover_start > cursor:
            uncovered.append((cursor, min(cover_start, end)))
        cursor = max(cursor, cover_end)
        if cursor >= end:
            break
    if cursor < end:
        uncovered.append((cursor, end))
    return tuple(segment for segment in uncovered if segment[1] > segment[0])


def frame_coverage_evidence(
    holder_span: HolderSpan,
    visible_sequence_span: VisibleSequenceSpan,
    frames: tuple[Box, ...],
    cache: MeasurementCache,
    content_configuration: ContentConfiguration,
) -> FrameCoverageEvidence:
    holder = holder_span.box.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    frame_intervals = _merged_intervals(
        [
            (max(holder.left, frame.left), min(holder.right, frame.right))
            for frame in frames
        ]
    )
    runs = content_region_runs(
        cache.content_evidence_work,
        holder,
        content_configuration=content_configuration,
    )
    return FrameCoverageEvidence(
        holder_long_axis_interval=(holder.left, holder.right),
        visible_sequence_interval=(
            visible_sequence_span.box.left,
            visible_sequence_span.box.right,
        ),
        frame_intervals=frame_intervals,
        content_runs=tuple(runs),
        candidate_frame_count=len(frames),
    )


def frame_coverage_matches_geometry(
    geometry: SequenceSolution,
    evidence: FrameCoverageEvidence,
) -> bool:
    holder = geometry.holder_span.box
    expected_intervals = _merged_intervals(
        [
            (max(holder.left, frame.left), min(holder.right, frame.right))
            for frame in geometry.frames
        ]
    )
    visible = geometry.visible_sequence_span.box
    return bool(
        evidence.holder_long_axis_interval == (holder.left, holder.right)
        and evidence.visible_sequence_interval == (visible.left, visible.right)
        and evidence.frame_intervals == expected_intervals
        and evidence.candidate_frame_count == geometry.count
    )
