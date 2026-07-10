from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...constants import CANDIDATE_SOURCE_REVIEW_ONLY
from ...domain import Box, DetectionCandidate
from ...formats import FormatPhysicalSpec
from ...geometry.boxes import map_work_box
from ...geometry.layout import work_gray
from ...run_config import RunConfig
from ..candidate.signals import (
    SIGNAL_DUAL_LANE_PARTIAL_NOT_SUPPORTED,
    SIGNAL_NEEDS_MANUAL_REVIEW,
)


def review_only_detection(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
) -> DetectionCandidate:
    if fmt.physical_layout != "dual_lane" or config.strip_mode != "partial":
        raise ValueError("Review-only detector requires dual-lane partial input")
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    outer = Box(0, 0, ww, wh)
    source_h, source_w = gray.shape
    mode_diagnostics = [
        SIGNAL_DUAL_LANE_PARTIAL_NOT_SUPPORTED,
        SIGNAL_NEEDS_MANUAL_REVIEW,
    ]
    return DetectionCandidate(
        format_id=fmt.format_id,
        layout=config.layout,
        strip_mode=config.strip_mode,
        count=fmt.default_count,
        outer=map_work_box(outer, config.layout, source_w, source_h),
        frames=[],
        gaps=[],
        confidence=0.0,
        detail={
            "candidate_signals": list(mode_diagnostics),
            "candidate_source": CANDIDATE_SOURCE_REVIEW_ONLY,
            "candidate_count": 0,
            "mode_diagnostics": list(mode_diagnostics),
            "layout": config.layout,
            "work_outer": asdict(outer),
            "candidate_competition": {
                "candidate_count": 0,
                "format_ids": [fmt.format_id],
                "selected_candidate": {
                    "format_id": fmt.format_id,
                    "count": fmt.default_count,
                    "strip_mode": config.strip_mode,
                    "confidence": 0.0,
                    "candidate_signals": list(mode_diagnostics),
                },
                "top_candidates": [],
            },
        },
    )
