from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...cache import AnalysisCache
from ...domain import Box
from ...formats import FormatPhysicalSpec
from ...policies.runtime.content import ContentPolicy
from ...utils import box_from_dict
from ..evidence.content.regions import content_mask_region_detail


@dataclass(frozen=True)
class CountPlacementGuidance:
    offsets: tuple[float, ...]
    source: str
    detail: dict[str, Any]


def content_count_placement_guidance(
    cache: AnalysisCache,
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
            {"used": False, "reason": "invalid_outer"},
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
            {"used": True, "reason": "no_placement_range"},
        )

    mask_detail = content_mask_region_detail(
        cache.content_evidence_float_work,
        cache.gray_work.shape,
        fmt,
        cache,
        content_policy=content_policy,
    )
    content_raw = mask_detail.get("outer") if isinstance(mask_detail, dict) else None
    content = box_from_dict(content_raw) if isinstance(content_raw, dict) else None
    if content is None or not content.valid():
        return CountPlacementGuidance(
            (0.5,),
            "neutral_center",
            {"used": False, "reason": "content_position_unavailable"},
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
        {
            "used": True,
            "role": "placement_guidance_only",
            "count": int(count),
            "frame_span": float(frame_span),
            "placement_range": float(available),
            "content_outer": content_raw,
        },
    )
