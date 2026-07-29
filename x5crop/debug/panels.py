from __future__ import annotations

import numpy as np

from ..configuration.diagnostics import DebugStyleParameters
from ..detection.workspace import DetectionWorkspace
from .canvas import (
    DebugRenderCache,
    cached_preview_gray,
    draw_preview_rect,
    fill_preview_rect,
)


DEBUG_CONTENT_COMPONENT_DISPLAY_LIMIT = 200


def make_source_core_preview_rgb(
    workspace: DetectionWorkspace,
    style: DebugStyleParameters,
    render_cache: DebugRenderCache,
) -> np.ndarray:
    rgb, scale = cached_preview_gray(
        render_cache,
        "source_core",
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
    return rgb
