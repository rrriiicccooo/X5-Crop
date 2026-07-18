from __future__ import annotations

import numpy as np

from ..configuration.diagnostics import DebugStyleParameters, SeparatorOverlayParameters
from ..detection.candidate.model import AssessedCandidate
from ..detection.physical.model import (
    DualLaneFrameSolution,
    FrameSequenceSolution,
    FrameBoundarySource,
    ResolvedFrameBoundary,
    SharedShortAxisBasis,
)
from ..domain import (
    BoundaryAxis,
    BoundarySide,
    Box,
    GrayBoundaryPathObservation,
    SeparatorBandObservation,
)
from ..geometry.boxes import map_work_box
from .canvas import draw_preview_dashed_line, draw_preview_line, draw_preview_mark


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
    start = int(round(observation.leading_edge.midpoint))
    end = max(start + 1, int(round(observation.trailing_edge.midpoint)))
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
    side: BoundarySide,
    boundary: ResolvedFrameBoundary,
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
            side,
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


def _selected_boundary_paths(
    solution: FrameSequenceSolution,
) -> tuple[GrayBoundaryPathObservation, ...]:
    selected_ids = {
        *(
            path.provenance.observation_id
            for boundary in solution.holder_safety.boundaries
            for path in boundary.supporting_paths
        ),
        *(
            assignment.observation.provenance.observation_id
            for assignment in solution.long_axis_assignments
        ),
    }
    return tuple(
        path
        for path in solution.raw_boundary_paths
        if path.provenance.observation_id in selected_ids
    )


def _selected_separator_observations(
    solution: FrameSequenceSolution,
) -> tuple[SeparatorBandObservation, ...]:
    return tuple(
        assignment.observation for assignment in solution.separator_assignments
    )


def _draw_sequence_overlay(
    rgb: np.ndarray,
    solution: FrameSequenceSolution,
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
    for path in _selected_boundary_paths(solution):
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
            style.raw_observation_color,
            overlay.observed_line_width,
        )
    for holder_boundary in solution.holder_safety.boundaries:
        draw_preview_dashed_line(
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
            dash_length=style.line_dash_length,
            dash_gap=style.line_dash_gap,
        )
    for observation in _selected_separator_observations(solution):
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
            style.raw_observation_color,
            overlay.observed_line_width,
        )
    for side, position in (
        (BoundarySide.TOP, solution.shared_short_axis.top),
        (BoundarySide.BOTTOM, solution.shared_short_axis.bottom),
    ):
        mark = _boundary_mark_box(
            side,
            position.midpoint,
            corridor,
            x_offset=x_offset,
            y_offset=y_offset,
            image_width=image_width,
            image_height=image_height,
            layout=layout,
        )
        if solution.shared_short_axis.basis == SharedShortAxisBasis.PHOTO_EDGE_BOUNDED:
            draw_preview_line(
                rgb,
                mark,
                scale,
                style.measured_boundary_color,
                overlay.observed_line_width,
            )
        else:
            draw_preview_dashed_line(
                rgb,
                mark,
                scale,
                style.holder_boundary_color,
                overlay.observed_line_width,
                dash_length=style.line_dash_length,
                dash_gap=style.line_dash_gap,
            )
    for slot in solution.frame_slots:
        for side, boundary in (
            (BoundarySide.LEADING, slot.leading),
            (BoundarySide.TRAILING, slot.trailing),
        ):
            if boundary.source in {
                FrameBoundarySource.DIMENSION_CONSTRAINED,
                FrameBoundarySource.HOLDER_OCCLUSION_INFERENCE,
                FrameBoundarySource.EXTERNAL_SAFETY_ENVELOPE,
                FrameBoundarySource.SEQUENCE_INFERENCE,
            }:
                draw_preview_dashed_line(
                    rgb,
                    _boundary_mark_box(
                        side,
                        boundary.position.midpoint,
                        corridor,
                        x_offset=x_offset,
                        y_offset=y_offset,
                        image_width=image_width,
                        image_height=image_height,
                        layout=layout,
                    ),
                    scale,
                    (
                        style.sequence_inferred_slot_color
                        if boundary.source
                        == FrameBoundarySource.SEQUENCE_INFERENCE
                        else (
                            style.frame_crop_envelope_color
                            if boundary.source
                            == FrameBoundarySource.EXTERNAL_SAFETY_ENVELOPE
                            else style.dimension_hypothesis_color
                        )
                    ),
                    (
                        style.sequence_inferred_slot_line_width
                        if boundary.source
                        == FrameBoundarySource.SEQUENCE_INFERENCE
                        else overlay.dimension_line_width
                    ),
                    dash_length=style.line_dash_length,
                    dash_gap=style.line_dash_gap,
                )
            elif boundary.independently_observed:
                _draw_boundary(
                    rgb,
                    side,
                    boundary,
                    corridor,
                    x_offset=x_offset,
                    y_offset=y_offset,
                    scale=scale,
                    color=style.measured_boundary_color,
                    width=overlay.observed_line_width,
                    image_width=image_width,
                    image_height=image_height,
                    layout=layout,
                )
    for index, spacing in enumerate(solution.inter_frame_spacings):
        if not spacing.supports_output_protection:
            continue
        left = solution.frame_slots[index]
        right = solution.frame_slots[index + 1]
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
            style.corroborated_overlap_color,
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
    if isinstance(geometry, FrameSequenceSolution):
        _draw_sequence_overlay(
            rgb,
            geometry,
            geometry.holder_safety.box,
            x_offset=0,
            y_offset=0,
            scale=scale,
            overlay=overlay,
            style=style,
            image_width=image_width,
            image_height=image_height,
            layout=geometry.layout,
        )
    elif isinstance(geometry, DualLaneFrameSolution):
        for lane, lane_solution in zip(
            geometry.lane_boxes,
            geometry.lane_solutions,
            strict=True,
        ):
            _draw_sequence_overlay(
                rgb,
                lane_solution,
                lane_solution.holder_safety.box,
                x_offset=lane.left,
                y_offset=lane.top,
                scale=scale,
                overlay=overlay,
                style=style,
                image_width=image_width,
                image_height=image_height,
                layout=geometry.layout,
            )
