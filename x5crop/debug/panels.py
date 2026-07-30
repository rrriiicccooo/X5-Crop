from __future__ import annotations

import numpy as np

from ..configuration.diagnostics import DebugStyleParameters
from ..detection.workspace import DetectionWorkspace
from ..domain import Box
from .canvas import (
    DebugRenderCache,
    cached_preview_gray,
    draw_preview_rect,
    fill_preview_rect,
)


DEBUG_CONTENT_COMPONENT_DISPLAY_LIMIT = 200


def make_bounded_safe_crop_preview_rgb(
    workspace: DetectionWorkspace,
    detection,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = cached_preview_gray(
        render_cache,
        "bounded_safe_crop_grid",
        workspace.measurement_cache.gray_work,
        style.preview_max_side,
    )
    for lane in workspace.source_core.lanes:
        domain = lane.domain.work_box
        fill_preview_rect(
            rgb,
            domain,
            scale,
            style.domain_color,
            style.domain_fill_alpha,
        )
        draw_preview_rect(
            rgb,
            domain,
            scale,
            style.domain_color,
            style.domain_line_width,
        )
        for component in lane.content.components[
            :DEBUG_CONTENT_COMPONENT_DISPLAY_LIMIT
        ]:
            draw_preview_rect(
                rgb,
                component.footprint,
                scale,
                style.content_color,
                style.content_line_width,
            )
    for separator in workspace.separator_fields:
        lane = next(
            lane
            for lane in workspace.source_core.lanes
            if lane.domain.lane_id == separator.lane_id
        )
        for line in separator.lines[:256]:
            x = lane.domain.work_box.left + int(round(line.boundary_px))
            draw_preview_rect(
                rgb,
                Box(
                    max(lane.domain.work_box.left, x - 1),
                    lane.domain.work_box.top,
                    min(lane.domain.work_box.right, x + 1),
                    lane.domain.work_box.bottom,
                ),
                scale,
                style.domain_color,
                1,
            )
    for lane_envelopes in detection.candidate.protected_envelopes_by_lane:
        for envelope in lane_envelopes:
            draw_preview_rect(
                rgb,
                envelope.protected_work_box,
                scale,
                style.review_color,
                style.domain_line_width,
            )
    return rgb
