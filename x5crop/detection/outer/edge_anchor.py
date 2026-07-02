from __future__ import annotations

from typing import Optional

import numpy as np

from ...domain import Box, OuterCandidate
from ...formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import DetectionPolicy
from ...runtime import AnalysisCache
from ...utils import bbox_from_mask, clamp_int
from .base import unique_outer_candidates
from .outer_cache_keys import long_axis_edge_anchor_cache_key


def long_axis_edge_anchor_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> list[OuterCandidate]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    edge_anchor_policy = policy.outer.edge_anchor_outer
    if edge_anchor_policy.mode == "off":
        return []
    if strip_mode == "full" and count != fmt.default_count:
        return []
    if strip_mode not in {"full", "partial"} or count <= 0:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []
    if cache is not None:
        candidate_key = long_axis_edge_anchor_cache_key(base_candidates, fmt, count, strip_mode)
        cached_candidates = cache.long_axis_edge_anchor_outer_candidates.get(candidate_key)
        if cached_candidates is not None:
            return list(cached_candidates)

    h, w = gray_work.shape
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:1]
    candidates: list[OuterCandidate] = []

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        outer_crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
        local_content = bbox_from_mask(
            outer_crop < int(edge_anchor_policy.content_threshold),
            min_row_fraction=0.010,
            min_col_fraction=0.010,
        )
        content = None
        if local_content is not None and local_content.valid():
            content = Box(
                outer.left + local_content.left,
                outer.top + local_content.top,
                outer.left + local_content.right,
                outer.top + local_content.bottom,
            ).clamp(w, h)
        if strip_mode == "partial":
            if content is None or not content.valid():
                continue
            content_center = ((float(content.left + content.right) * 0.5) - float(outer.left)) / max(1.0, float(outer.width))
            edge_limit = float(edge_anchor_policy.partial_center_ratio)
            if edge_limit <= content_center <= (1.0 - edge_limit):
                continue
        margin = clamp_int(
            float(outer.height) * edge_anchor_policy.content_margin_ratio,
            edge_anchor_policy.content_margin_min,
            edge_anchor_policy.content_margin_max,
        )
        y_top = outer.top
        y_bottom = outer.bottom
        if content is not None and content.valid():
            y_top = max(outer.top, content.top - margin)
            y_bottom = min(outer.bottom, content.bottom + margin)
            if y_bottom - y_top < max(40, int(round(float(outer.height) * 0.65))):
                y_top = outer.top
                y_bottom = outer.bottom
        short_axis = max(1, y_bottom - y_top)
        min_width = max(80, int(round(float(outer.width) * edge_anchor_policy.min_width_ratio)))

        for extra in edge_anchor_policy.ratio_extras:
            target_ratio = float(count) * float(aspect) + float(extra)
            target_width = int(round(float(short_axis) * target_ratio))
            if target_width < min_width or target_width >= outer.width:
                continue
            anchors = (
                ("start", outer.left, outer.left + target_width),
                ("end", outer.right - target_width, outer.right),
            )
            for anchor_name, left, right in anchors:
                box = Box(int(left), y_top, int(right), y_bottom).clamp(w, h)
                if not box.valid() or box.width < min_width:
                    continue
                candidates.append(
                    OuterCandidate(
                        f"long_axis_edge_anchor_{strip_mode}_{anchor_name}_{source.name}_r{target_ratio:.3f}",
                        box,
                        "edge_anchor_outer",
                    )
                )

    result = unique_outer_candidates(candidates)[: int(edge_anchor_policy.max_candidates)]
    if cache is not None:
        cache.long_axis_edge_anchor_outer_candidates[candidate_key] = list(result)
    return result
