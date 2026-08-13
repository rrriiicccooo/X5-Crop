from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import FiniteInterval
from .line_observations import SourceCoordinateLine
from .model import (
    BoundaryAxis,
    BoundaryRole,
)
from .output_model import FrameBoundaryGeometry, SharedStripDirection


@dataclass(frozen=True)
class OutwardBoundaryProjection:
    """Cheap exact projection of one retained discard-edge family."""

    outward_position_px: float
    reference_trace_px: float
    slopes: tuple[float, float]

    def coordinate_bounds(
        self,
        orthogonal_minimum_px: float,
        orthogonal_maximum_px: float,
    ) -> tuple[float, float]:
        values = tuple(
            self.outward_position_px
            + slope * (orthogonal - self.reference_trace_px)
            for slope in self.slopes
            for orthogonal in (
                orthogonal_minimum_px,
                orthogonal_maximum_px,
            )
        )
        return min(values), max(values)

    def coordinate_interval(
        self,
        orthogonal_interval_px: FiniteInterval,
    ) -> FiniteInterval:
        return FiniteInterval(
            *self.coordinate_bounds(
                orthogonal_interval_px.minimum,
                orthogonal_interval_px.maximum,
            )
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
    if not isinstance(cross_axis, BoundaryAxis):
        raise TypeError("cross axis must be canonical source x or y")
    tangent = math.tan(math.radians(direction.canonical_angle_degrees))
    return tangent


def canonical_source_sequence_axis_slope(
    direction: SharedStripDirection,
    sequence_axis: BoundaryAxis,
) -> float:
    if not isinstance(sequence_axis, BoundaryAxis):
        raise TypeError("sequence axis must be canonical source x or y")
    tangent = math.tan(math.radians(direction.canonical_angle_degrees))
    return -tangent


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


def boundary_line_at_state(
    boundary: FrameBoundaryGeometry,
    *,
    position_px: float,
    angle_degrees: float,
) -> SourceCoordinateLine:
    """Materialize one retained position/direction state for a boundary."""

    source_axis_long = boundary.line.source_axis_long
    boundary_axis = (
        source_axis_long
        if boundary.role in {BoundaryRole.START, BoundaryRole.END}
        else (
            BoundaryAxis.Y
            if source_axis_long == BoundaryAxis.X
            else BoundaryAxis.X
        )
    )
    angle = math.radians(angle_degrees)
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


def outward_boundary_projection(
    boundary: FrameBoundaryGeometry,
) -> OutwardBoundaryProjection:
    """Compile the final safe discard edge into strip-coordinate slopes.

    SafeCropEnvelope retains the outward position endpoint and both retained
    direction endpoints.  The compiled projection is reused across all exact
    content cells queried for that boundary.
    """

    outward_position = (
        boundary.full_position_interval_px.minimum
        if boundary.role in {BoundaryRole.TOP, BoundaryRole.START}
        else boundary.full_position_interval_px.maximum
    )
    cross_boundary = boundary.role in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
    sign = 1.0 if cross_boundary else -1.0
    return OutwardBoundaryProjection(
        outward_position_px=outward_position,
        reference_trace_px=boundary.reference_trace_px,
        slopes=tuple(
            sign * math.tan(math.radians(angle))
            for angle in (
                boundary.full_direction_interval_degrees.minimum,
                boundary.full_direction_interval_degrees.maximum,
            )
        ),
    )
