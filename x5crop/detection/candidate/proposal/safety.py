from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ....constants import CANDIDATE_SOURCE_HARD_SAFETY
from ....domain import Box, Detection
from ....formats import FormatSpec
from ....geometry.boxes import map_work_box
from ....geometry.frame_fit import frame_boxes_from_gaps
from ....geometry.layout import work_gray
from ....geometry.model_gaps import equal_model_gap
from ....runtime.config import RuntimeConfig


def hard_safety_detection(gray: np.ndarray, config: RuntimeConfig, fmt: FormatSpec) -> Detection:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    count = max(1, int(config.count))
    outer = Box(0, 0, ww, wh)
    if count > 1:
        pitch = ww / float(count)
        gaps = [equal_model_gap(i, pitch * i, 0.0) for i in range(1, count)]
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
        [],
        {
            "candidate_reasons": ["hard_safety_no_candidates", "needs_manual_review"],
            "candidate_source": CANDIDATE_SOURCE_HARD_SAFETY,
            "safety_candidate_kind": "hard_safety_equal_split",
            "candidate_contract": "hard_safety_review_input",
            "candidate_auto_gate_eligible": False,
            "layout": config.layout,
            "film_format": fmt.name,
            "strip_mode": config.strip_mode,
            "count": int(count),
            "work_outer": asdict(outer),
            "pitch": float(pitch),
        },
    )
