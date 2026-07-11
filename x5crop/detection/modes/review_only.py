from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ...constants import CANDIDATE_SOURCE_REVIEW_ONLY
from ...domain import Box, DetectionCandidate
from ...formats import FormatPhysicalSpec
from ...geometry.boxes import map_work_box
from ...geometry.layout import work_gray
from ...run_config import RunConfig
from ..candidate.assessment.mode import apply_mode_candidate_assessment


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
        "dual_lane_partial_not_supported",
        "manual_processing_required",
    ]
    detection = DetectionCandidate(
        format_id=fmt.format_id,
        layout=config.layout,
        strip_mode=config.strip_mode,
        count=fmt.default_count,
        outer=map_work_box(outer, config.layout, source_w, source_h),
        frames=[],
        gaps=[],
        confidence=0.0,
        detail={
            "candidate_source": CANDIDATE_SOURCE_REVIEW_ONLY,
            "candidate_count": 0,
            "mode_diagnostics": list(mode_diagnostics),
            "layout": config.layout,
            "work_outer": asdict(outer),
        },
    )
    return apply_mode_candidate_assessment(
        detection,
        source=CANDIDATE_SOURCE_REVIEW_ONLY,
        automatic_processing_supported=False,
        component_candidate_gates=[],
    )
