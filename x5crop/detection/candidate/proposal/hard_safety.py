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
from ....geometry.detection_parameters import FrameFitParameters
from ....run_config import RunConfig


def hard_safety_detection(
    gray: np.ndarray,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    count: int,
    frame_fit: FrameFitParameters,
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
        geometry_parameters=frame_fit,
    )
    source_h, source_w = gray.shape
    boxes = [map_work_box(box, config.layout, source_w, source_h) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, source_w, source_h)
    return DetectionCandidate(
        format_id=fmt.format_id,
        layout=config.layout,
        strip_mode=config.strip_mode,
        count=count,
        outer=outer_original,
        frames=boxes,
        gaps=gaps,
        confidence=0.0,
        detail={
            "candidate_source": CANDIDATE_SOURCE_HARD_SAFETY,
            "mode_diagnostics": [
                "no_physical_candidates",
                "manual_processing_required",
            ],
            "automatic_processing_supported": False,
            "hard_safety_kind": "equal_split",
            "candidate_contract": "hard_safety_review_input",
            "layout": config.layout,
            "format_id": fmt.format_id,
            "strip_mode": config.strip_mode,
            "count": int(count),
            "work_outer": asdict(outer),
            "pitch": float(pitch),
        },
    )
