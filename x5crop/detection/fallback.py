from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ..config import RuntimeConfig
from ..constants import ANALYSIS_SOURCE_HARD_FALLBACK
from ..domain import Box, Detection, Gap
from ..formats import FormatSpec
from ..geometry.boxes import map_work_box
from ..geometry.frame_fit import frame_boxes_from_gaps
from ..geometry.layout import work_gray


def hard_fallback_detection(gray: np.ndarray, config: RuntimeConfig, fmt: FormatSpec) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    count = max(1, int(config.count))
    outer = Box(0, 0, ww, wh)
    if count > 1:
        pitch = ww / float(count)
        gaps = [Gap(i, pitch * i, 0.0, "equal") for i in range(1, count)]
    else:
        pitch = float(ww)
        gaps = []
    boxes_work = frame_boxes_from_gaps(outer, gaps, count, ww, wh, config.bleed_x, config.bleed_y, origin=0.0, pitch=pitch)
    source_h, source_w = gray.shape
    boxes = [map_work_box(box, config.layout, source_w, source_h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, source_w, source_h)
    return Detection(
        fmt.name,
        config.layout,
        config.strip_mode,
        count,
        outer_original,
        boxes,
        gaps,
        0.0,
        ["hard_fallback_no_candidates", "needs_manual_review"],
        {
            "analysis_source": ANALYSIS_SOURCE_HARD_FALLBACK,
            "fallback_kind": "review_only_equal_split",
            "changes_pass_review": False,
            "layout": config.layout,
            "film_format": fmt.name,
            "strip_mode": config.strip_mode,
            "count": int(count),
            "work_outer": asdict(outer),
            "pitch": float(pitch),
        },
    )
