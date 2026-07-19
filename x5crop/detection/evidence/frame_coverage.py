from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...cache import MeasurementCache
from ...configuration.content import ContentConfiguration
from ...domain import Box, EvidenceState
from ...image.content import ContentRegionObservation, uncovered_content_runs
from .content.regions import cached_content_region_observation

if TYPE_CHECKING:
    from ..physical.model import FrameSequenceSolution


@dataclass(frozen=True)
class FrameCoverageEvidence:
    holder_long_axis_interval: tuple[int, int]
    frame_slot_intervals: tuple[tuple[int, int], ...]
    content_runs: tuple[tuple[int, int], ...]
    content_position_uncertainty_px: int
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    uncovered_content: tuple[tuple[int, int], ...] = field(init=False)

    def __post_init__(self) -> None:
        holder_start, holder_end = self.holder_long_axis_interval
        if holder_end <= holder_start:
            raise ValueError("holder coverage interval must have positive extent")
        if self.content_position_uncertainty_px < 0:
            raise ValueError("content position uncertainty must be non-negative")
        if not self.frame_slot_intervals:
            raise ValueError("frame coverage requires slots")
        previous_start: int | None = None
        previous_end: int | None = None
        for start, end in self.frame_slot_intervals:
            if not holder_start <= start < end <= holder_end:
                raise ValueError("frame-slot intervals must fit the holder")
            if (
                previous_start is not None
                and previous_end is not None
                and (start <= previous_start or end <= previous_end)
            ):
                raise ValueError("frame-slot intervals must be strictly monotonic")
            previous_start = start
            previous_end = end
        for start, end in self.content_runs:
            if not holder_start <= start < end <= holder_end:
                raise ValueError("content intervals must fit the holder")

        sequence_interval = (
            self.frame_slot_intervals[0][0],
            self.frame_slot_intervals[-1][1],
        )
        uncovered = uncovered_content_runs(
            self.content_runs,
            (sequence_interval,),
            position_uncertainty_px=self.content_position_uncertainty_px,
            bounds=self.holder_long_axis_interval,
        )
        if not self.content_runs:
            state = EvidenceState.UNAVAILABLE
            reason = "content_runs_unavailable"
        elif uncovered:
            state = EvidenceState.CONTRADICTED
            reason = "content_outside_frame_sequence"
        else:
            state = EvidenceState.SUPPORTED
            reason = "content_inside_frame_slots"
        object.__setattr__(self, "uncovered_content", uncovered)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _frame_intervals(
    geometry: FrameSequenceSolution,
) -> tuple[tuple[int, int], ...]:
    holder = geometry.holder_safety.box
    intervals = tuple(
        (
            max(holder.left, item.box.left),
            min(holder.right, item.box.right),
        )
        for item in geometry.frame_crop_envelopes
    )
    if not intervals or any(end <= start for start, end in intervals):
        raise ValueError("frame coverage requires valid slots")
    return intervals


def _merged_reliable_content_runs(
    observations: tuple[ContentRegionObservation, ...],
    holder: Box,
) -> tuple[tuple[int, int], ...]:
    clipped = sorted(
        {
            (max(holder.left, start), min(holder.right, end))
            for observation in observations
            for start, end in observation.reliable_runs
            if min(holder.right, end) > max(holder.left, start)
        }
    )
    merged: list[tuple[int, int]] = []
    for start, end in clipped:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def frame_coverage_evidence(
    geometry: FrameSequenceSolution,
    cache: MeasurementCache,
    content_configuration: ContentConfiguration,
) -> FrameCoverageEvidence:
    holder = geometry.holder_safety.box.clamp(
        cache.gray_work.shape[1],
        cache.gray_work.shape[0],
    )
    frame_intervals = _frame_intervals(geometry)
    content = cached_content_region_observation(
        cache,
        holder,
        content_configuration,
    )
    workspace_content = cached_content_region_observation(
        cache,
        Box(
            0,
            0,
            cache.gray_work.shape[1],
            cache.gray_work.shape[0],
        ),
        content_configuration,
    )
    return FrameCoverageEvidence(
        holder_long_axis_interval=(holder.left, holder.right),
        frame_slot_intervals=frame_intervals,
        content_runs=_merged_reliable_content_runs(
            (content, workspace_content),
            holder,
        ),
        content_position_uncertainty_px=max(
            content.position_uncertainty_px,
            workspace_content.position_uncertainty_px,
        ),
    )


def frame_coverage_matches_geometry(
    geometry: FrameSequenceSolution,
    evidence: FrameCoverageEvidence,
) -> bool:
    holder = geometry.holder_safety.box
    intervals = _frame_intervals(geometry)
    return bool(
        evidence.holder_long_axis_interval == (holder.left, holder.right)
        and evidence.frame_slot_intervals == intervals
    )
