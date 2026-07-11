from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box, DetectionCandidate
from ...utils import box_from_dict


@dataclass(frozen=True)
class HolderSpan:
    box: Box


@dataclass(frozen=True)
class FilmSpan:
    box: Box


def candidate_work_outer(candidate: DetectionCandidate) -> Box:
    value = candidate.detail.get("work_outer")
    if isinstance(value, dict):
        box = box_from_dict(value)
        if box.valid():
            return box
    return candidate.outer


def candidate_work_frames(candidate: DetectionCandidate) -> tuple[Box, ...]:
    value = candidate.detail.get("work_frame_boxes")
    frames: list[Box] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            box = box_from_dict(item)
            if box.valid():
                frames.append(box)
    if frames:
        return tuple(frames)
    return tuple(frame for frame in candidate.frames if frame.valid())


def holder_span_from_candidate(candidate: DetectionCandidate) -> HolderSpan:
    value = candidate.detail.get("holder_reference_outer_box")
    if isinstance(value, dict):
        box = box_from_dict(value)
        if box.valid():
            return HolderSpan(box)
    return HolderSpan(candidate_work_outer(candidate))


def film_span_from_frames(frames: tuple[Box, ...]) -> FilmSpan | None:
    if not frames:
        return None
    return FilmSpan(
        Box(
            min(frame.left for frame in frames),
            min(frame.top for frame in frames),
            max(frame.right for frame in frames),
            max(frame.bottom for frame in frames),
        )
    )
