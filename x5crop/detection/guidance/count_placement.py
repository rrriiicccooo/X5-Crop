from __future__ import annotations

from dataclasses import dataclass
from ...cache import MeasurementCache
from ...domain import Box
from ...formats import FormatPhysicalSpec
from ...policies.runtime.content import ContentPolicy
from ..evidence.content.regions import content_mask_region


@dataclass(frozen=True)
class CountPlacementGuidance:
    offsets: tuple[float, ...]
    source: str


def content_count_placement_guidance(
    cache: MeasurementCache,
    fmt: FormatPhysicalSpec,
    count: int,
    source_outer: Box,
    content_policy: ContentPolicy,
) -> CountPlacementGuidance:
    if count <= 0:
        raise ValueError("count placement guidance requires a positive count")
    outer = source_outer.clamp(cache.gray_work.shape[1], cache.gray_work.shape[0])
    if not outer.valid():
        return CountPlacementGuidance(
            (0.5,),
            "neutral_center",
        )

    frame_span = min(
        float(outer.width),
        float(outer.height) * float(fmt.horizontal_content_aspect) * float(count),
    )
    available = max(0.0, float(outer.width) - frame_span)
    if available <= 0.0:
        return CountPlacementGuidance(
            (0.0,),
            "full_span",
        )

    content = content_mask_region(
        cache.content_evidence_float_work,
        cache.gray_work.shape,
        cache,
        content_policy=content_policy,
    )
    if content is None or not content.valid():
        return CountPlacementGuidance(
            (0.5,),
            "neutral_center",
        )

    local_left = float(content.left - outer.left)
    local_right = float(content.right - outer.left)
    content_center = (local_left + local_right) * 0.5
    origins = (
        local_left,
        content_center - frame_span * 0.5,
        local_right - frame_span,
    )
    offsets: list[float] = []
    for origin in origins:
        normalized = round(max(0.0, min(available, origin)) / available, 4)
        if normalized not in offsets:
            offsets.append(normalized)
    return CountPlacementGuidance(
        tuple(offsets),
        "content_position_guidance",
    )
