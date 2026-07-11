from __future__ import annotations

from ..domain import Box, SeparatorBandObservation


def frame_boxes_from_gaps(
    outer: Box,
    gaps: list[SeparatorBandObservation],
    count: int,
    image_width: int,
    image_height: int,
    bleed_x: int,
    bleed_y: int,
    *,
    origin: float,
    pitch: float,
) -> list[Box]:
    cuts = [
        float(outer.left + origin),
        *(float(outer.left) + gap.center for gap in gaps),
        float(outer.left + origin + pitch * count),
    ]
    return [
        Box(
            int(round(left)),
            outer.top,
            int(round(right)),
            outer.bottom,
        ).expand(bleed_x, bleed_y, image_width, image_height)
        for left, right in zip(cuts[:-1], cuts[1:])
    ][:count]
