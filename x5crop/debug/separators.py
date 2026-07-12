from __future__ import annotations

from typing import Any

import numpy as np

from ..detection.decision.model import FinalDetection
from ..detection.candidate.model import AssessedCandidate
from x5crop.domain import SeparatorBandObservation
from ..domain import Box
from ..geometry.boxes import map_work_box
from ..configuration.diagnostics import DebugStyleParameters
from .canvas import draw_preview_line, draw_preview_mark


def _work_corridor(
    selected_candidate: AssessedCandidate,
    observation: SeparatorBandObservation,
) -> Box:
    return observation.lane_box or selected_candidate.geometry.crop_envelope.box


def separator_mark_box(
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    observation: SeparatorBandObservation,
    image_width: int,
    image_height: int,
) -> Box:
    corridor = _work_corridor(selected_candidate, observation)
    start = int(round(observation.start))
    end = max(start + 1, int(round(observation.end)))
    return map_work_box(
        Box(start, corridor.top, end, corridor.bottom),
        detection.layout,
        image_width,
        image_height,
    )


def _boundary_ticks(
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    center: float,
    overlay: Any,
    image_width: int,
    image_height: int,
) -> tuple[Box, Box]:
    corridor = selected_candidate.geometry.crop_envelope.box
    tick = max(
        int(overlay.tick_length_min),
        int(round(corridor.height * float(overlay.tick_length_ratio))),
    )
    x = int(round(center))
    work_ticks = (
        Box(x, corridor.top, x + 1, min(corridor.bottom, corridor.top + tick)),
        Box(x, max(corridor.top, corridor.bottom - tick), x + 1, corridor.bottom),
    )
    return tuple(
        map_work_box(box, detection.layout, image_width, image_height)
        for box in work_ticks
    )


def draw_separator_overlay(
    rgb: np.ndarray,
    detection: FinalDetection,
    selected_candidate: AssessedCandidate,
    scale: float,
    overlay: Any,
    style: DebugStyleParameters,
) -> None:
    image_height = max(
        1,
        int(round(rgb.shape[0] / max(scale, style.separator_scale_floor))),
    )
    image_width = max(
        1,
        int(round(rgb.shape[1] / max(scale, style.separator_scale_floor))),
    )
    geometry = selected_candidate.geometry
    accepted = {
        id(assignment.observation)
        for assignment in geometry.separator_assignments
        if assignment.used_for_boundary and assignment.independent
    }
    for observation in geometry.separator_observations:
        draw_preview_mark(
            rgb,
            separator_mark_box(
                detection,
                selected_candidate,
                observation,
                image_width,
                image_height,
            ),
            scale,
            (
                style.accepted_separator_color
                if id(observation) in accepted
                else style.unselected_separator_color
            ),
            overlay.observed_line_width,
        )
    overlap_indexes = {
        spacing.index
        for spacing in selected_candidate.assessment.evidence.frame_sequence.spacings
        if spacing.kind == "overlap"
    }
    for boundary in geometry.frame_boundaries:
        if boundary.source == "observed_separator" and boundary.boundary_index not in overlap_indexes:
            continue
        color = (
            style.overlap_boundary_color
            if boundary.boundary_index in overlap_indexes
            else style.dimension_boundary_color
        )
        for tick in _boundary_ticks(
            detection,
            selected_candidate,
            boundary.coordinate,
            overlay,
            image_width,
            image_height,
        ):
            draw_preview_line(
                rgb,
                tick,
                scale,
                color,
                (
                    overlay.overlap_line_width
                    if boundary.boundary_index in overlap_indexes
                    else overlay.dimension_line_width
                ),
            )
