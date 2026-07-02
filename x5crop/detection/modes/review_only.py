from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...constants import ANALYSIS_SOURCE_REVIEW_ONLY
from ...domain import Box, Detection
from ...formats import FormatSpec
from ...geometry.boxes import map_work_box
from ...geometry.layout import work_gray
from ...policies.runtime_policy import DetectionPolicy
from ...runtime_config import RuntimeConfig


def review_only_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    policy: DetectionPolicy,
) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = Box(0, 0, ww, wh)
    source_h, source_w = gray.shape
    review_reasons = [policy.detector.review_only.reason, "needs_manual_review"]
    return Detection(
        fmt.name,
        config.layout,
        config.strip_mode,
        fmt.default_count,
        map_work_box(outer, config.layout, source_w, source_h),
        [],
        [],
        0.0,
        list(review_reasons),
        {
            "analysis_source": ANALYSIS_SOURCE_REVIEW_ONLY,
            "candidate_count": 0,
            "layout": config.layout,
            "work_outer": asdict(outer),
            "candidate_competition": {
                "candidate_count": 0,
                "formats": [fmt.name],
                "selected_candidate": {
                    "format": fmt.name,
                    "count": fmt.default_count,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "review_reasons": list(review_reasons),
                },
                "selection_override": policy.detector.review_only.selection_override,
                "top_candidates": [],
            },
        },
    )


__all__ = ["review_only_detection"]
