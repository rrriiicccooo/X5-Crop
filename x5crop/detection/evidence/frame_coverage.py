from __future__ import annotations

from dataclasses import dataclass

from ...cache import AnalysisCache
from ...domain import DetectionCandidate
from ...formats import FormatPhysicalSpec
from ...policies.runtime.content import ContentPolicy
from ..physical.spans import (
    candidate_work_frames,
    film_span_from_frames,
    holder_span_from_candidate,
)
from .content.regions import content_region_runs
from .state import EvidenceState


@dataclass(frozen=True)
class FrameCoverageEvidence:
    state: EvidenceState
    reason: str
    holder_interval: tuple[int, int]
    film_interval: tuple[int, int] | None
    frame_intervals: tuple[tuple[int, int], ...]
    content_runs: tuple[tuple[int, int], ...]
    uncovered_content: tuple[tuple[int, int], ...]


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
    candidate: DetectionCandidate,
    fmt: FormatPhysicalSpec,
    cache: AnalysisCache,
    content_policy: ContentPolicy,
) -> FrameCoverageEvidence:
    holder = holder_span_from_candidate(candidate).box.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    frames = candidate_work_frames(candidate)
    film = film_span_from_frames(frames)
    frame_intervals = _merged_intervals(
        [
            (max(holder.left, frame.left), min(holder.right, frame.right))
            for frame in frames
        ]
    )
    runs, _detail = content_region_runs(
        cache.content_evidence_work,
        holder,
        fmt.default_count,
        fmt.format_id,
        cache,
        content_policy=content_policy,
    )
    tolerance = max(1, int(content_policy.profile.min_run_width_px))
    uncovered = tuple(
        segment
        for run in runs
        for segment in _uncovered_segments(run, frame_intervals)
        if segment[1] - segment[0] >= tolerance
    )
    if not runs:
        state = EvidenceState.UNAVAILABLE
        reason = "content_runs_unavailable"
    elif uncovered:
        state = EvidenceState.CONTRADICTED
        reason = "content_outside_frame_union"
    else:
        state = EvidenceState.SUPPORTED
        reason = "content_runs_covered"
    return FrameCoverageEvidence(
        state=state,
        reason=reason,
        holder_interval=(holder.left, holder.right),
        film_interval=(None if film is None else (film.box.left, film.box.right)),
        frame_intervals=frame_intervals,
        content_runs=tuple(runs),
        uncovered_content=uncovered,
    )
