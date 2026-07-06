from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..constants import GAP_DETECTED, GAP_EDGE_PAIR, GAP_EQUAL, GAP_GRID
from ..domain import Box, Detection, Gap
from ..gap_methods import is_hard_gap_method
from ..policies.registry import get_detection_policy
from ..utils import clamp_float
from .canvas import (
    draw_preview_hline,
    draw_preview_line,
    draw_preview_mark,
)


def gap_mark_box(detection: Detection, gap: Gap) -> Optional[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return None
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return None
    if is_hard_gap_method(gap.method) and gap.start is not None and gap.end is not None:
        start = int(round(work_outer.left + min(gap.start, gap.end)))
        end = int(round(work_outer.left + max(gap.start, gap.end)))
        if end <= start:
            end = start + 1
        if detection.layout == "horizontal":
            return Box(start, work_outer.top, end, work_outer.bottom)
        return Box(work_outer.top, start, work_outer.bottom, end)

    x = int(round(work_outer.left + gap.center))
    if detection.layout == "horizontal":
        return Box(x, work_outer.top, x + 1, work_outer.bottom)
    return Box(work_outer.top, x, work_outer.bottom, x + 1)


def gap_tick_boxes(detection: Detection, gap: Gap, debug_gap: Any) -> list[Box]:
    work_outer_raw = gap.lane_box if isinstance(gap.lane_box, dict) else detection.detail.get("work_outer")
    if not isinstance(work_outer_raw, dict):
        return []
    try:
        work_outer = Box(
            int(work_outer_raw["left"]),
            int(work_outer_raw["top"]),
            int(work_outer_raw["right"]),
            int(work_outer_raw["bottom"]),
        )
    except Exception:
        return []
    tick_axis = work_outer.height if detection.layout == "horizontal" else work_outer.width
    tick = max(
        int(debug_gap.tick_length_min),
        int(round(tick_axis * float(debug_gap.tick_length_ratio))),
    )
    if detection.layout == "horizontal":
        x = int(round(work_outer.left + gap.center))
        return [
            Box(x, work_outer.top, x + 1, min(work_outer.bottom, work_outer.top + tick)),
            Box(x, max(work_outer.top, work_outer.bottom - tick), x + 1, work_outer.bottom),
        ]
    y = int(round(work_outer.left + gap.center))
    return [
        Box(work_outer.top, y, min(work_outer.bottom, work_outer.top + tick), y + 1),
        Box(max(work_outer.top, work_outer.bottom - tick), y, work_outer.bottom, y + 1),
    ]


def draw_gap_overlay(rgb: np.ndarray, detection: Detection, scale: float) -> None:
    debug_gap = get_detection_policy(detection.film_format, detection.strip_mode).diagnostics.debug_gap_overlay
    gap_colors = {
        GAP_DETECTED: (255, 0, 0),
        GAP_EDGE_PAIR: (255, 0, 0),
        GAP_GRID: (255, 220, 30),
        GAP_EQUAL: (190, 80, 255),
    }
    pitch = float(detection.detail.get("pitch", 0.0) or 0.0)
    detected_centers = [gap.center for gap in detection.gaps if is_hard_gap_method(gap.method)]
    overlap_tolerance = clamp_float(
        pitch * debug_gap.overlap_tolerance_ratio,
        debug_gap.overlap_tolerance_min,
        debug_gap.overlap_tolerance_max,
    )
    for gap in detection.gaps:
        if not is_hard_gap_method(gap.method):
            continue
        mark = gap_mark_box(detection, gap)
        if mark is not None:
            color = gap_colors.get(gap.method, (255, 255, 255))
            draw_preview_mark(rgb, mark, scale, color, debug_gap.hard_line_width)
    for gap in detection.gaps:
        if is_hard_gap_method(gap.method):
            continue
        if any(abs(gap.center - center) <= overlap_tolerance for center in detected_centers):
            continue
        color = gap_colors.get(gap.method, (255, 255, 255))
        for tick in gap_tick_boxes(detection, gap, debug_gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, debug_gap.model_line_width)
            else:
                draw_preview_hline(rgb, tick, scale, color, debug_gap.model_line_width)
    draw_gap_diagnostic_overlay(rgb, detection, scale)


def draw_gap_diagnostic_overlay(rgb: np.ndarray, detection: Detection, scale: float) -> None:
    debug_gap = get_detection_policy(detection.film_format, detection.strip_mode).diagnostics.debug_gap_overlay
    diagnostics = detection.detail.get("diagnostics")
    records: Any = None
    if isinstance(diagnostics, dict):
        records = diagnostics.get("gap_diagnostics", [])
    if not isinstance(records, list):
        overlap_bleed = detection.detail.get("overlap_bleed_risk")
        if isinstance(overlap_bleed, dict):
            records = overlap_bleed.get("gap_diagnostics", [])
    if not isinstance(records, list):
        return
    gaps_by_index = {gap.index: gap for gap in detection.gaps}
    for record in records:
        if not isinstance(record, dict):
            continue
        gap = gaps_by_index.get(int(record.get("index", -1)))
        if gap is None:
            continue
        color: Optional[tuple[int, int, int]] = None
        if record.get("hard_trust") in {
            "suspect_internal_edge",
            "suspect_frame_border",
            "nearby_separator_conflict",
            "geometry_conflict",
        }:
            color = (255, 0, 220)
        elif str(record.get("overlap_risk", "none")) in {"medium", "strong"}:
            color = (0, 220, 255)
        if color is None:
            continue
        for tick in gap_tick_boxes(detection, gap, debug_gap):
            if detection.layout == "horizontal":
                draw_preview_line(rgb, tick, scale, color, debug_gap.diagnostic_line_width)
            else:
                draw_preview_hline(rgb, tick, scale, color, debug_gap.diagnostic_line_width)
