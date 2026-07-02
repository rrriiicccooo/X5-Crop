from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...runtime_config import RuntimeConfig
from ...constants import ANALYSIS_SOURCE_UNSUPPORTED
from ...domain import Box, Detection
from ...geometry.boxes import map_work_box
from ...geometry.layout import work_gray


def unsupported_parallel_lane_partial_detection(gray: np.ndarray, config: RuntimeConfig) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = Box(0, 0, ww, wh)
    source_h, source_w = gray.shape
    return Detection(
        "135-dual",
        config.layout,
        config.strip_mode,
        12,
        map_work_box(outer, config.layout, source_w, source_h),
        [],
        [],
        0.0,
        ["parallel_lane_partial_not_supported", "needs_manual_review"],
        {
            "analysis_source": ANALYSIS_SOURCE_UNSUPPORTED,
            "candidate_count": 0,
            "layout": config.layout,
            "work_outer": asdict(outer),
            "candidate_competition": {
                "candidate_count": 0,
                "formats": ["135-dual"],
                "selected_candidate": {
                    "format": "135-dual",
                    "count": 12,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "review_reasons": ["parallel_lane_partial_not_supported", "needs_manual_review"],
                },
                "selection_override": "unsupported_parallel_lane_partial",
                "top_candidates": [],
            },
        },
    )
