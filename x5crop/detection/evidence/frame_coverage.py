from __future__ import annotations

from dataclasses import dataclass

from ...cache import MeasurementCache
from ...domain import Box
from ...configuration.content import ContentConfiguration
from x5crop.domain import VisibleSequenceSpan, HolderSpan
from .content.regions import content_region_runs
from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class FrameCoverageEvidence:
    state: EvidenceState
    reason: str
    holder_long_axis_interval: tuple[int, int]
    visible_sequence_interval: tuple[int, int]
    frame_intervals: tuple[tuple[int, int], ...]
    content_runs: tuple[tuple[int, int], ...]
    uncovered_content: tuple[tuple[int, int], ...]
    unexplained_content_region_count: int


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
    content_policy: ContentConfiguration,
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
        content_policy=content_policy,
    )
    tolerance = max(1, int(content_policy.profile.min_run_width_px))
    uncovered = tuple(
        segment
        for run in runs
        for segment in _uncovered_segments(run, frame_intervals)
        if segment[1] - segment[0] >= tolerance
    )
    unexplained_region_count = max(0, len(runs) - len(frames))
    if not runs:
        state = EvidenceState.UNAVAILABLE
        reason = "content_runs_unavailable"
    elif uncovered:
        state = EvidenceState.CONTRADICTED
        reason = "content_outside_frame_union"
    else:
        state = EvidenceState.SUPPORTED
        reason = (
            "content_runs_covered_multiple_regions"
            if unexplained_region_count
            else "content_runs_covered"
        )
    return FrameCoverageEvidence(
        state=state,
        reason=reason,
        holder_long_axis_interval=(holder.left, holder.right),
        visible_sequence_interval=(
            visible_sequence_span.box.left,
            visible_sequence_span.box.right,
        ),
        frame_intervals=frame_intervals,
        content_runs=tuple(runs),
        uncovered_content=uncovered,
        unexplained_content_region_count=unexplained_region_count,
    )
