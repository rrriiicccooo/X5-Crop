from __future__ import annotations

import numpy as np

from ..detection.candidate.model import AssessedCandidate
from ..detection.physical.model import DualLaneSolution, SequenceSolution
from ..configuration.diagnostics import DebugStyleParameters, SeparatorOverlayParameters
from ..domain import Box, FrameBoundarySource, SeparatorBandObservation
from ..geometry.boxes import map_work_box
from .canvas import draw_preview_line, draw_preview_mark


def separator_mark_box(
    observation: SeparatorBandObservation,
    corridor: Box,
    long_axis_offset: int,
    image_width: int,
    image_height: int,
    layout: str,
) -> Box:
    start = int(round(observation.start + long_axis_offset))
    end = max(start + 1, int(round(observation.end + long_axis_offset)))
    return map_work_box(
        Box(start, corridor.top, end, corridor.bottom),
        layout,
        image_width,
        image_height,
    )


def _boundary_ticks(
    corridor: Box,
    center: float,
    overlay: SeparatorOverlayParameters,
    image_width: int,
    image_height: int,
    layout: str,
) -> tuple[Box, Box]:
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
        map_work_box(
            box,
            layout,
            image_width,
            image_height,
        )
        for box in work_ticks
    )


def _draw_sequence_overlay(
    rgb: np.ndarray,
    solution: SequenceSolution,
    corridor: Box,
    lane_index: int | None,
    long_axis_offset: int,
    overlap_boundaries: set[tuple[int | None, int]],
    scale: float,
    overlay: SeparatorOverlayParameters,
    style: DebugStyleParameters,
    image_width: int,
    image_height: int,
    layout: str,
) -> None:
    accepted = {
        id(assignment.observation)
        for assignment in solution.separator_assignments
        if assignment.used_for_boundary and assignment.independent
    }
    for observation in solution.separator_observations:
        draw_preview_mark(
            rgb,
            separator_mark_box(
                observation,
                corridor,
                long_axis_offset,
                image_width,
                image_height,
                layout,
            ),
            scale,
            (
                style.accepted_separator_color
                if id(observation) in accepted
                else style.unselected_separator_color
            ),
            overlay.observed_line_width,
        )
    for boundary in solution.frame_boundaries:
        identity = (lane_index, boundary.boundary_index)
        overlap = identity in overlap_boundaries
        if boundary.source == FrameBoundarySource.OBSERVED_SEPARATOR and not overlap:
            continue
        for tick in _boundary_ticks(
            corridor,
            boundary.coordinate + long_axis_offset,
            overlay,
            image_width,
            image_height,
            layout,
        ):
            draw_preview_line(
                rgb,
                tick,
                scale,
                (
                    style.overlap_boundary_color
                    if overlap
                    else style.dimension_boundary_color
                ),
                (
                    overlay.overlap_line_width
                    if overlap
                    else overlay.dimension_line_width
                ),
            )


def draw_separator_overlay(
    rgb: np.ndarray,
    selected_candidate: AssessedCandidate,
    scale: float,
    overlay: SeparatorOverlayParameters,
    style: DebugStyleParameters,
    image_width: int,
    image_height: int,
) -> None:
    geometry = selected_candidate.geometry
    overlap_boundaries = {
        (
            spacing.boundary.lane_index,
            spacing.boundary.boundary_index,
        )
        for spacing in geometry.inter_frame_spacings
        if spacing.kind == "overlap"
    }
    if isinstance(geometry, SequenceSolution):
        _draw_sequence_overlay(
            rgb,
            geometry,
            geometry.crop_envelope.box,
            None,
            0,
            overlap_boundaries,
            scale,
            overlay,
            style,
            image_width,
            image_height,
            geometry.layout,
        )
    elif isinstance(geometry, DualLaneSolution):
        for lane_index, (lane, lane_solution, lane_envelope) in enumerate(
            zip(
                geometry.lane_boxes,
                geometry.lane_solutions,
                geometry.lane_crop_envelopes,
                strict=True,
            ),
            start=1,
        ):
            _draw_sequence_overlay(
                rgb,
                lane_solution,
                lane_envelope.box,
                lane_index,
                lane.left,
                overlap_boundaries,
                scale,
                overlay,
                style,
                image_width,
                image_height,
                geometry.layout,
            )
