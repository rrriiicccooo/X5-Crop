from __future__ import annotations

import math

from ...domain import FiniteInterval
from .model import (
    BoundaryAxis,
    BoundaryRole,
    FrameBoundaryGeometry,
    SharedStripDirection,
    SourceCoordinateLine,
)


def canonical_boundary_line(
    direction: SharedStripDirection,
    *,
    boundary_axis: BoundaryAxis,
    source_axis_long: BoundaryAxis,
    trace_coordinate_px: float,
    position_px: float,
    support_projection_px: FiniteInterval,
) -> SourceCoordinateLine:
    angle = math.radians(direction.canonical_angle_degrees)
    if boundary_axis == source_axis_long:
        normal_x, normal_y = (
            (math.cos(angle), math.sin(angle))
            if source_axis_long == BoundaryAxis.X
            else (math.sin(angle), math.cos(angle))
        )
    else:
        normal_x, normal_y = (
            (-math.sin(angle), math.cos(angle))
            if source_axis_long == BoundaryAxis.X
            else (math.cos(angle), -math.sin(angle))
        )
    offset = (
        normal_x * position_px + normal_y * trace_coordinate_px
        if boundary_axis == BoundaryAxis.X
        else normal_x * trace_coordinate_px + normal_y * position_px
    )
    return SourceCoordinateLine(
        normal_x=normal_x,
        normal_y=normal_y,
        offset_px=offset,
        support_projection_px=support_projection_px,
        source_axis_long=source_axis_long,
    )


def canonical_source_cross_axis_slope(
    direction: SharedStripDirection,
    cross_axis: BoundaryAxis,
) -> float:
    del cross_axis
    tangent = math.tan(math.radians(direction.canonical_angle_degrees))
    return tangent


def canonical_source_sequence_axis_slope(
    direction: SharedStripDirection,
    sequence_axis: BoundaryAxis,
) -> float:
    del sequence_axis
    tangent = math.tan(math.radians(direction.canonical_angle_degrees))
    return -tangent


def source_cross_axis_slope_interval(
    direction: SharedStripDirection,
    cross_axis: BoundaryAxis,
) -> FiniteInterval:
    del cross_axis
    values = tuple(
        math.tan(math.radians(angle))
        for angle in (
            direction.full_angle_interval_degrees.minimum,
            direction.full_angle_interval_degrees.maximum,
        )
    )
    return FiniteInterval(min(values), max(values))


def source_sequence_axis_slope_interval(
    direction: SharedStripDirection,
    sequence_axis: BoundaryAxis,
) -> FiniteInterval:
    del sequence_axis
    values = tuple(
        -math.tan(math.radians(angle))
        for angle in (
            direction.full_angle_interval_degrees.minimum,
            direction.full_angle_interval_degrees.maximum,
        )
    )
    return FiniteInterval(min(values), max(values))


def canonical_boundary_line_at_position(
    boundary: FrameBoundaryGeometry,
    position_px: float,
    canonical_side_line: SourceCoordinateLine,
) -> SourceCoordinateLine:
    source_axis_long = canonical_side_line.source_axis_long
    if boundary.line.source_axis_long != source_axis_long:
        raise ValueError("frame boundary source axes disagree")
    if boundary.role in {BoundaryRole.START, BoundaryRole.END}:
        boundary_axis = source_axis_long
        normal_x = canonical_side_line.normal_x
        normal_y = canonical_side_line.normal_y
    else:
        boundary_axis = (
            BoundaryAxis.Y
            if source_axis_long == BoundaryAxis.X
            else BoundaryAxis.X
        )
        normal_x, normal_y = (
            (-canonical_side_line.normal_y, canonical_side_line.normal_x)
            if source_axis_long == BoundaryAxis.X
            else (canonical_side_line.normal_y, -canonical_side_line.normal_x)
        )
    offset_px = (
        normal_x * position_px + normal_y * boundary.reference_trace_px
        if boundary_axis == BoundaryAxis.X
        else normal_x * boundary.reference_trace_px + normal_y * position_px
    )
    return SourceCoordinateLine(
        normal_x=normal_x,
        normal_y=normal_y,
        offset_px=offset_px,
        support_projection_px=boundary.line.support_projection_px,
        source_axis_long=source_axis_long,
    )
