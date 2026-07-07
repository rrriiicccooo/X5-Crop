from __future__ import annotations

import numpy as np

from ...domain import Box, OuterCandidate
from ...formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ...policies.runtime.policy import DetectionPolicy
from ...utils import bbox_from_mask, clamp_int
from ..physical.outer.common import unique_outer_candidates


def floating_content_position_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterCandidate],
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    policy: DetectionPolicy,
) -> list[OuterCandidate]:
    partial_placement = policy.outer.proposal.geometry.partial_placement
    floating_policy = partial_placement.floating
    if not partial_placement.enabled or not floating_policy.enabled:
        return []
    if strip_mode != "partial" or count <= 0:
        return []
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if aspect is None or aspect <= 0.0:
        return []
    if not base_candidates:
        return []

    h, w = gray_work.shape
    content = bbox_from_mask(
        gray_work < int(floating_policy.content_threshold),
        min_row_fraction=0.010,
        min_col_fraction=0.010,
    )
    candidates: list[OuterCandidate] = []
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:1]

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0:
            continue
        margin = clamp_int(
            float(outer.height) * floating_policy.content_margin_ratio,
            floating_policy.content_margin_min,
            floating_policy.content_margin_max,
        )
        y_top = outer.top
        y_bottom = outer.bottom
        if content is not None and content.valid():
            y_top = max(outer.top, content.top - margin)
            y_bottom = min(outer.bottom, content.bottom + margin)
            if y_bottom - y_top < max(40, int(round(outer.height * 0.65))):
                y_top = outer.top
                y_bottom = outer.bottom
        height = max(1, y_bottom - y_top)
        min_width = max(80, int(round(float(outer.width) * floating_policy.min_width_ratio)))

        starts_from_content: list[int] = []
        if content is not None and content.valid():
            starts_from_content.extend(
                [
                    int(round(float(content.left - margin))),
                    int(round(float(content.right + margin))),
                    int(round(float((content.left + content.right) * 0.5))),
                ]
            )

        for extra in floating_policy.ratio_extras:
            target_ratio = float(count) * float(aspect) + float(extra)
            target_width = int(round(float(height) * target_ratio))
            if target_width < min_width or target_width >= outer.width:
                continue
            starts: list[int] = []
            available = max(0, outer.width - target_width)
            starts.extend(
                [
                    outer.left,
                    outer.left + int(round(available * 0.50)),
                    outer.left + available,
                ]
            )
            for anchor in starts_from_content:
                starts.append(anchor)
                starts.append(anchor - target_width)
                starts.append(anchor - int(round(target_width * 0.5)))
            for start in starts:
                left = max(outer.left, min(start, outer.right - target_width))
                right = left + target_width
                box = Box(left, y_top, right, y_bottom).clamp(w, h)
                if not box.valid() or box.width < min_width:
                    continue
                candidates.append(
                    OuterCandidate(
                        f"floating_{strip_mode}_{source.name}_r{target_ratio:.3f}",
                        box,
                        "content_outer",
                        {
                            "family": "content_outer",
                            "placement": "floating",
                            "source_outer": source.name,
                            "target_ratio": float(target_ratio),
                            "content_guidance_role": "outer_position_hint",
                        },
                    )
                )

    return unique_outer_candidates(candidates)[: int(floating_policy.max_candidates)]
