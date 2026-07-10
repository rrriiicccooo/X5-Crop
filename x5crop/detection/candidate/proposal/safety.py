from __future__ import annotations

from dataclasses import asdict

import numpy as np

from ....constants import CANDIDATE_SOURCE_HARD_SAFETY
from ....domain import Box, DetectionCandidate
from ....formats import FormatPhysicalSpec
from ....geometry.boxes import map_work_box
from ....geometry.frame_fit import frame_boxes_from_gaps
from ....geometry.layout import work_gray
from ....geometry.model_gaps import equal_model_gap
from ....runtime.config import RuntimeConfig
from ..signals import SIGNAL_HARD_SAFETY_NO_CANDIDATES, SIGNAL_NEEDS_MANUAL_REVIEW


def hard_safety_detection(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatPhysicalSpec,
    count: int,
) -> DetectionCandidate:
    gray_work = work_gray(gray, config.layout)
    wh, ww = gray_work.shape
    count = max(1, int(count))
    outer = Box(0, 0, ww, wh)
    if count > 1:
        pitch = ww / float(count)
        gaps = [equal_model_gap(i, pitch * i, 0.0) for i in range(1, count)]
    else:
        pitch = float(ww)
        gaps = []
    boxes_work = frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        ww,
        wh,
        config.bleed_x,
        config.bleed_y,
        origin=0.0,
        pitch=pitch,
        geometry_parameters=None,
    )
    source_h, source_w = gray.shape
    boxes = [map_work_box(box, config.layout, source_w, source_h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, source_w, source_h)
    return DetectionCandidate(
        film_format=fmt.name,
        layout=config.layout,
        strip_mode=config.strip_mode,
        count=count,
        outer=outer_original,
        frames=boxes,
        gaps=gaps,
        confidence=0.0,
        detail={
            "candidate_signals": [SIGNAL_HARD_SAFETY_NO_CANDIDATES, SIGNAL_NEEDS_MANUAL_REVIEW],
            "candidate_source": CANDIDATE_SOURCE_HARD_SAFETY,
            "safety_candidate_kind": "hard_safety_equal_split",
            "candidate_contract": "hard_safety_review_input",
            "candidate_gate_eligible": False,
            "layout": config.layout,
            "film_format": fmt.name,
            "strip_mode": config.strip_mode,
            "count": int(count),
            "work_outer": asdict(outer),
            "pitch": float(pitch),
        },
    )
