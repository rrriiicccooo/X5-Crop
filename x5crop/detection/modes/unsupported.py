from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...runtime_config import RuntimeConfig
from ...constants import ANALYSIS_SOURCE_UNSUPPORTED
from ...domain import Box, Detection
from ...geometry.boxes import map_work_box
from ...geometry.layout import work_gray
from .dual_lane_context import DualLaneDetectionContext


def unsupported_dual_lane_partial_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    context: DualLaneDetectionContext,
) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = Box(0, 0, ww, wh)
    source_h, source_w = gray.shape
    review_reasons = [context.unsupported_partial_reason, "needs_manual_review"]
    return Detection(
        context.format_id,
        config.layout,
        config.strip_mode,
        context.total_count,
        map_work_box(outer, config.layout, source_w, source_h),
        [],
        [],
        0.0,
        list(review_reasons),
        {
            "analysis_source": ANALYSIS_SOURCE_UNSUPPORTED,
            "candidate_count": 0,
            "layout": config.layout,
            "work_outer": asdict(outer),
            "candidate_competition": {
                "candidate_count": 0,
                "formats": [context.format_id],
                "selected_candidate": {
                    "format": context.format_id,
                    "count": context.total_count,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "review_reasons": list(review_reasons),
                },
                "selection_override": "unsupported_dual_lane_partial",
                "top_candidates": [],
            },
        },
    )
