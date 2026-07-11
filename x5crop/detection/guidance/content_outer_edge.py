from __future__ import annotations

import numpy as np

from ...domain import Box, MeasurementProvenance
from ...formats import FormatPhysicalSpec
from ...policies.runtime.outer import PartialPlacementGeometryPolicy
from ...utils import bbox_from_mask, clamp_int
from ..physical.outer.common import unique_outer_proposals
from ..physical.outer.types import OuterProposal


def _edge_anchor_side(content_center: float, edge_limit: float) -> str | None:
    if content_center < edge_limit:
        return "start"
    if content_center > (1.0 - edge_limit):
        return "end"
    return None


def edge_anchored_outer_candidates(
    gray_work: np.ndarray,
    base_candidates: list[OuterProposal],
    fmt: FormatPhysicalSpec,
    count: int,
    strip_mode: str,
    *,
    partial_placement: PartialPlacementGeometryPolicy,
) -> list[OuterProposal]:
    edge_anchor_policy = partial_placement.edge_anchor
    if not partial_placement.enabled:
        return []
    if strip_mode != "partial" or count <= 0:
        return []
    aspect = float(fmt.horizontal_content_aspect)
    if aspect <= 0.0:
        return []
    if not base_candidates:
        return []
    h, w = gray_work.shape
    source_candidates = sorted(
        [candidate for candidate in base_candidates if candidate.box.valid()],
        key=lambda candidate: candidate.box.width * candidate.box.height,
        reverse=True,
    )[:1]
    candidates: list[OuterProposal] = []

    for source in source_candidates:
        outer = source.box.clamp(w, h)
        if not outer.valid() or outer.height <= 0 or outer.width <= 0:
            continue
        outer_crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
        local_content = bbox_from_mask(
            outer_crop < int(edge_anchor_policy.content_threshold),
            min_row_fraction=edge_anchor_policy.content_bbox_min_fraction,
            min_col_fraction=edge_anchor_policy.content_bbox_min_fraction,
        )
        content = None
        if local_content is not None and local_content.valid():
            content = Box(
                outer.left + local_content.left,
                outer.top + local_content.top,
                outer.left + local_content.right,
                outer.top + local_content.bottom,
            ).clamp(w, h)
        if content is None or not content.valid():
            continue
        content_center_abs = float(content.left + content.right) * 0.5
        content_center = (content_center_abs - float(outer.left)) / max(1.0, float(outer.width))
        anchor_side = _edge_anchor_side(content_center, float(edge_anchor_policy.partial_center_ratio))
        if anchor_side is None:
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
            if y_bottom - y_top < max(
                edge_anchor_policy.min_short_axis_px,
                int(round(float(outer.height) * edge_anchor_policy.min_short_axis_ratio)),
            ):
                y_top = outer.top
                y_bottom = outer.bottom
        short_axis = max(1, y_bottom - y_top)
        min_width = max(
            edge_anchor_policy.min_width_px,
            int(round(float(outer.width) * edge_anchor_policy.min_width_ratio)),
        )

        for extra in edge_anchor_policy.ratio_extras:
            target_ratio = float(count) * float(aspect) + float(extra)
            target_width = int(round(float(short_axis) * target_ratio))
            if target_width < min_width or target_width >= outer.width:
                continue
            anchors = (
                (anchor_side, outer.left, outer.left + target_width)
                if anchor_side == "start"
                else (anchor_side, outer.right - target_width, outer.right),
            )
            for anchor_name, left, right in anchors:
                if not (float(left) <= content_center_abs <= float(right)):
                    continue
                box = Box(int(left), y_top, int(right), y_bottom).clamp(w, h)
                if not box.valid() or box.width < min_width:
                    continue
                candidates.append(
                    OuterProposal(
                        f"edge_anchor_{strip_mode}_{anchor_name}_{source.name}_r{target_ratio:.3f}",
                        box,
                        "edge_anchor_outer",
                        MeasurementProvenance(
                            "content_guidance",
                            f"edge_anchor_{anchor_name}",
                            (source.provenance.root_measurement, "content_bbox"),
                        ),
                    )
                )

    return unique_outer_proposals(candidates)[: int(edge_anchor_policy.max_candidates)]
