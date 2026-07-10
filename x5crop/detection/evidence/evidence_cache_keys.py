from __future__ import annotations

from typing import Any, Optional

from ...domain import DetectionCandidate
from ...geometry.boxes import box_cache_key


def detection_frame_cache_key(detection: DetectionCandidate) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(box_cache_key(frame) for frame in detection.frames)


def detection_gap_cache_key(
    detection: DetectionCandidate,
) -> tuple[tuple[int, str, float, Optional[float], Optional[float]], ...]:
    return tuple(
        (
            int(gap.index),
            str(gap.method),
            float(gap.center),
            None if gap.start is None else float(gap.start),
            None if gap.end is None else float(gap.end),
        )
        for gap in detection.gaps
    )


def content_detail_cache_key(
    detection: DetectionCandidate,
    source_w: int,
    source_h: int,
    policy_key: tuple[Any, ...],
) -> tuple[Any, ...]:
    return (
        str(detection.format_id),
        str(detection.layout),
        int(source_w),
        int(source_h),
        box_cache_key(detection.outer),
        detection_frame_cache_key(detection),
        policy_key,
    )
