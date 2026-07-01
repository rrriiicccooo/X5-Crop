from __future__ import annotations

from typing import Any, Optional

from ..domain import Detection
from ..geometry import box_cache_key


def detection_frame_cache_key(detection: Detection) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(box_cache_key(frame) for frame in detection.frames)


def detection_gap_cache_key(
    detection: Detection,
) -> tuple[tuple[int, str, float, Optional[float], Optional[float]], ...]:
    return tuple(
        (
            int(gap.index),
            str(gap.method),
            round(float(gap.center), 4),
            None if gap.start is None else round(float(gap.start), 4),
            None if gap.end is None else round(float(gap.end), 4),
        )
        for gap in detection.gaps
    )


def content_detail_cache_key(
    detection: Detection,
    source_w: int,
    source_h: int,
    policy_key: tuple[Any, ...] = (),
) -> tuple[Any, ...]:
    return (
        str(detection.film_format),
        str(detection.layout),
        int(source_w),
        int(source_h),
        box_cache_key(detection.outer),
        detection_frame_cache_key(detection),
        policy_key,
    )
