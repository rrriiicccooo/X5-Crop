from __future__ import annotations

from typing import Any

import numpy as np

from ..constants import GAP_DETECTED, GAP_EDGE_PAIR, GAP_EQUAL
from ..detection.decision.model import FinalDetection
from ..domain import Box, SeparatorBandObservation
from ..gap_methods import is_hard_gap_method
from ..geometry.boxes import map_work_box
from ..utils import clamp_float
from .canvas import draw_preview_line, draw_preview_mark


def _work_outer(
    detection: FinalDetection,
    observation: SeparatorBandObservation,
) -> Box:
    return observation.lane_box or detection.work_film_span


def gap_mark_box(
    detection: FinalDetection,
    observation: SeparatorBandObservation,
    image_width: int,
    image_height: int,
) -> Box:
    outer = _work_outer(detection, observation)
    if (
        is_hard_gap_method(observation.method)
        and observation.start is not None
        and observation.end is not None
    ):
        start = int(round(outer.left + min(observation.start, observation.end)))
        end = max(
            start + 1,
            int(round(outer.left + max(observation.start, observation.end))),
        )
    else:
        start = int(round(outer.left + observation.center))
        end = start + 1
    return map_work_box(
        Box(start, outer.top, end, outer.bottom),
        detection.layout,
        image_width,
        image_height,
    )


def gap_tick_boxes(
    detection: FinalDetection,
    observation: SeparatorBandObservation,
    debug_gap: Any,
    image_width: int,
    image_height: int,
) -> tuple[Box, Box]:
    outer = _work_outer(detection, observation)
    tick = max(
        int(debug_gap.tick_length_min),
        int(round(outer.height * float(debug_gap.tick_length_ratio))),
    )
    x = int(round(outer.left + observation.center))
    work_ticks = (
        Box(x, outer.top, x + 1, min(outer.bottom, outer.top + tick)),
        Box(x, max(outer.top, outer.bottom - tick), x + 1, outer.bottom),
    )
    return tuple(
        map_work_box(
            box,
            detection.layout,
            image_width,
            image_height,
        )
        for box in work_ticks
    )


def draw_gap_overlay(
    rgb: np.ndarray,
    detection: FinalDetection,
    scale: float,
    debug_gap: Any,
) -> None:
    colors = {
        GAP_DETECTED: (255, 0, 0),
        GAP_EDGE_PAIR: (255, 0, 0),
        GAP_EQUAL: (190, 80, 255),
    }
    pitch = float(detection.pitch)
    hard_centers = [
        observation.center
        for observation in detection.separator_observations
        if is_hard_gap_method(observation.method)
    ]
    overlap_tolerance = clamp_float(
        pitch * debug_gap.overlap_tolerance_ratio,
        debug_gap.overlap_tolerance_min,
        debug_gap.overlap_tolerance_max,
    )
    image_height = max(1, int(round(rgb.shape[0] / max(scale, 1e-9))))
    image_width = max(1, int(round(rgb.shape[1] / max(scale, 1e-9))))
    for observation in detection.separator_observations:
        if is_hard_gap_method(observation.method):
            draw_preview_mark(
                rgb,
                gap_mark_box(
                    detection,
                    observation,
                    image_width,
                    image_height,
                ),
                scale,
                colors.get(observation.method, (255, 255, 255)),
                debug_gap.hard_line_width,
            )
            continue
        if any(
            abs(observation.center - center) <= overlap_tolerance
            for center in hard_centers
        ):
            continue
        for tick in gap_tick_boxes(
            detection,
            observation,
            debug_gap,
            image_width,
            image_height,
        ):
            draw_preview_line(
                rgb,
                tick,
                scale,
                colors.get(observation.method, (255, 255, 255)),
                debug_gap.model_line_width,
            )
    exposure_overlap = detection.require_trace().exposure_overlap
    records = {record.index: record for record in exposure_overlap.gaps}
    for observation in detection.separator_observations:
        record = records.get(observation.index)
        if record is None:
            continue
        color = None
        if record.hard_trust in {
            "suspect_internal_edge",
            "suspect_frame_border",
            "nearby_separator_conflict",
            "geometry_conflict",
        }:
            color = (255, 0, 220)
        elif record.exposure_overlap_like:
            color = (0, 220, 255)
        if color is None:
            continue
        for tick in gap_tick_boxes(
            detection,
            observation,
            debug_gap,
            image_width,
            image_height,
        ):
            draw_preview_line(
                rgb,
                tick,
                scale,
                color,
                debug_gap.diagnostic_line_width,
            )
