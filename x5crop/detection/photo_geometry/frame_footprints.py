"""Exact continuous footprints for one fixed-format frame."""

from __future__ import annotations

from ...geometry.convex import ConvexPolygon, convex_hull
from .boundary_geometry import (
    boundary_line_at_state,
    canonical_boundary_line_at_position,
)
from .chains import CompleteFormatChain, FixedFormatFrame


def _boundary_polygon(
    frame: FixedFormatFrame,
    *,
    top_position_px: float,
    bottom_position_px: float,
    start_position_px: float,
    end_position_px: float,
) -> tuple[tuple[float, float], ...]:
    top = canonical_boundary_line_at_position(
        frame.top,
        top_position_px,
        frame.start.line,
    )
    bottom = canonical_boundary_line_at_position(
        frame.bottom,
        bottom_position_px,
        frame.start.line,
    )
    start = canonical_boundary_line_at_position(
        frame.start,
        start_position_px,
        frame.start.line,
    )
    end = canonical_boundary_line_at_position(
        frame.end,
        end_position_px,
        frame.start.line,
    )
    return (
        top.intersection(start),
        top.intersection(end),
        bottom.intersection(end),
        bottom.intersection(start),
    )


def format_placement_frame_footprint(
    placement: CompleteFormatChain,
    lane_ordinal: int,
) -> ConvexPolygon:
    index = lane_ordinal - 1
    if index < 0 or index >= placement.output_slot_count:
        raise ValueError("complete-chain ordinal is out of range")
    frame = placement.fixed_frames.frames[index]
    return convex_hull(
        _boundary_polygon(
            frame,
            top_position_px=placement.cross.top_canonical_positions_px[index],
            bottom_position_px=(
                placement.cross.bottom_canonical_positions_px[index]
            ),
            start_position_px=placement.sequence.canonical_positions_px[index * 2],
            end_position_px=(
                placement.sequence.canonical_positions_px[index * 2 + 1]
            ),
        )
    )


def retained_frame_safety_footprint(
    placement: CompleteFormatChain,
    lane_ordinal: int,
) -> ConvexPolygon:
    """Envelope the selected frame's retained line states exactly once."""

    index = lane_ordinal - 1
    if index < 0 or index >= placement.output_slot_count:
        raise ValueError("complete-chain ordinal is out of range")
    frame = placement.fixed_frames.frames[index]
    # A selected frame is one fixed-format rectangle in one shared lane
    # direction.  Direction uncertainty therefore produces a finite family of
    # complete rectangles, not four independently rotating edges.  Retain the
    # two direction endpoints, materialize every boundary at the same endpoint
    # and envelope those complete physical states.  Per-boundary outward
    # position uncertainty is still consumed exactly once.
    points: list[tuple[float, float]] = []
    for angle in tuple(
        dict.fromkeys(
            (
                placement.lane_geometry.direction
                .full_angle_interval_degrees.minimum,
                placement.lane_geometry.direction
                .full_angle_interval_degrees.maximum,
            )
        )
    ):
        top = boundary_line_at_state(
            frame.top,
            position_px=frame.top.full_position_interval_px.minimum,
            angle_degrees=angle,
        )
        bottom = boundary_line_at_state(
            frame.bottom,
            position_px=frame.bottom.full_position_interval_px.maximum,
            angle_degrees=angle,
        )
        start = boundary_line_at_state(
            frame.start,
            position_px=frame.start.full_position_interval_px.minimum,
            angle_degrees=angle,
        )
        end = boundary_line_at_state(
            frame.end,
            position_px=frame.end.full_position_interval_px.maximum,
            angle_degrees=angle,
        )
        points.extend(
            (
                top.intersection(start),
                top.intersection(end),
                bottom.intersection(end),
                bottom.intersection(start),
            )
        )
    return convex_hull(tuple(points))
