from __future__ import annotations

import numpy as np

from ..configuration.diagnostics import DebugStyleParameters, SeparatorOverlayParameters
from ..detection.candidate.model import AssessedCandidate
from ..detection.physical.model import DualLanePhotoSolution, PhotoSequenceSolution
from ..domain import (
    BoundaryAxis,
    BoundarySide,
    Box,
    PhotoApertureBoundaryResolution,
    PhotoApertureEdgeSource,
    SeparatorBandObservation,
)
from ..geometry.boxes import map_work_box
from .canvas import draw_preview_line, draw_preview_mark


def _mapped_work_mark(
    work_box: Box,
    *,
    x_offset: int,
    y_offset: int,
    image_width: int,
    image_height: int,
    layout: str,
) -> Box:
    return map_work_box(
        Box(
            work_box.left + x_offset,
            work_box.top + y_offset,
            work_box.right + x_offset,
            work_box.bottom + y_offset,
        ),
        layout,
        image_width,
        image_height,
    )


def separator_mark_box(
    observation: SeparatorBandObservation,
    corridor: Box,
    x_offset: int,
    y_offset: int,
    image_width: int,
    image_height: int,
    layout: str,
) -> Box:
    start = int(round(observation.start))
    end = max(start + 1, int(round(observation.end)))
    return _mapped_work_mark(
        Box(start, corridor.top, end, corridor.bottom),
        x_offset=x_offset,
        y_offset=y_offset,
        image_width=image_width,
        image_height=image_height,
        layout=layout,
    )


def _boundary_mark_box(
    side: BoundarySide,
    position: float,
    corridor: Box,
    *,
    x_offset: int,
    y_offset: int,
    image_width: int,
    image_height: int,
    layout: str,
) -> Box:
    coordinate = int(round(position))
    work_box = (
        Box(coordinate, corridor.top, coordinate + 1, corridor.bottom)
        if side in {BoundarySide.LEADING, BoundarySide.TRAILING}
        else Box(corridor.left, coordinate, corridor.right, coordinate + 1)
    )
    return _mapped_work_mark(
        work_box,
        x_offset=x_offset,
        y_offset=y_offset,
        image_width=image_width,
        image_height=image_height,
        layout=layout,
    )


def _axis_mark_box(
    axis: BoundaryAxis,
    position: float,
    corridor: Box,
    **mapping: int | str,
) -> Box:
    side = (
        BoundarySide.LEADING
        if axis == BoundaryAxis.LONG
        else BoundarySide.TOP
    )
    return _boundary_mark_box(side, position, corridor, **mapping)


def _draw_boundary(
    rgb: np.ndarray,
    boundary: PhotoApertureBoundaryResolution,
    corridor: Box,
    *,
    x_offset: int,
    y_offset: int,
    scale: float,
    color: tuple[int, int, int],
    width: int,
    image_width: int,
    image_height: int,
    layout: str,
) -> None:
    draw_preview_line(
        rgb,
        _boundary_mark_box(
            boundary.side,
            boundary.position.midpoint,
            corridor,
            x_offset=x_offset,
            y_offset=y_offset,
            image_width=image_width,
            image_height=image_height,
            layout=layout,
        ),
        scale,
        color,
        width,
    )


def _draw_sequence_overlay(
    rgb: np.ndarray,
    solution: PhotoSequenceSolution,
    corridor: Box,
    *,
    x_offset: int,
    y_offset: int,
    scale: float,
    overlay: SeparatorOverlayParameters,
    style: DebugStyleParameters,
    image_width: int,
    image_height: int,
    layout: str,
) -> None:
    for path in solution.raw_boundary_paths:
        draw_preview_line(
            rgb,
            _axis_mark_box(
                path.axis,
                path.position.midpoint,
                corridor,
                x_offset=x_offset,
                y_offset=y_offset,
                image_width=image_width,
                image_height=image_height,
                layout=layout,
            ),
            scale,
            style.unselected_separator_color,
            overlay.observed_line_width,
        )
    for holder_boundary in solution.holder_boundaries:
        draw_preview_line(
            rgb,
            _boundary_mark_box(
                holder_boundary.side,
                holder_boundary.position.midpoint,
                corridor,
                x_offset=x_offset,
                y_offset=y_offset,
                image_width=image_width,
                image_height=image_height,
                layout=layout,
            ),
            scale,
            style.holder_boundary_color,
            overlay.observed_line_width,
        )
    for observation in solution.separator_observations:
        draw_preview_mark(
            rgb,
            separator_mark_box(
                observation,
                corridor,
                x_offset,
                y_offset,
                image_width,
                image_height,
                layout,
            ),
            scale,
            style.unselected_separator_color,
            overlay.observed_line_width,
        )
    for aperture in solution.photo_apertures:
        for boundary in (
            aperture.leading,
            aperture.trailing,
            aperture.top,
            aperture.bottom,
        ):
            if boundary.source == PhotoApertureEdgeSource.DIMENSION_HYPOTHESIS:
                _draw_boundary(
                    rgb,
                    boundary,
                    corridor,
                    x_offset=x_offset,
                    y_offset=y_offset,
                    scale=scale,
                    color=style.dimension_boundary_color,
                    width=overlay.dimension_line_width,
                    image_width=image_width,
                    image_height=image_height,
                    layout=layout,
                )
            elif boundary.independently_observed:
                _draw_boundary(
                    rgb,
                    boundary,
                    corridor,
                    x_offset=x_offset,
                    y_offset=y_offset,
                    scale=scale,
                    color=style.accepted_separator_color,
                    width=overlay.observed_line_width,
                    image_width=image_width,
                    image_height=image_height,
                    layout=layout,
                )
    for index, spacing in enumerate(solution.inter_photo_spacings):
        if not spacing.supports_output_protection:
            continue
        left = solution.photo_apertures[index]
        right = solution.photo_apertures[index + 1]
        overlap_position = 0.5 * (
            left.trailing.position.midpoint + right.leading.position.midpoint
        )
        draw_preview_line(
            rgb,
            _boundary_mark_box(
                BoundarySide.TRAILING,
                overlap_position,
                corridor,
                x_offset=x_offset,
                y_offset=y_offset,
                image_width=image_width,
                image_height=image_height,
                layout=layout,
            ),
            scale,
            style.overlap_boundary_color,
            overlay.overlap_line_width,
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
    if isinstance(geometry, PhotoSequenceSolution):
        _draw_sequence_overlay(
            rgb,
            geometry,
            geometry.holder_span.box,
            x_offset=0,
            y_offset=0,
            scale=scale,
            overlay=overlay,
            style=style,
            image_width=image_width,
            image_height=image_height,
            layout=geometry.layout,
        )
    elif isinstance(geometry, DualLanePhotoSolution):
        for lane, lane_solution in zip(
            geometry.lane_boxes,
            geometry.lane_solutions,
            strict=True,
        ):
            _draw_sequence_overlay(
                rgb,
                lane_solution,
                lane_solution.holder_span.box,
                x_offset=lane.left,
                y_offset=lane.top,
                scale=scale,
                overlay=overlay,
                style=style,
                image_width=image_width,
                image_height=image_height,
                layout=geometry.layout,
            )
