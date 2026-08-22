"""Materialize source-axis crop boundaries and enclosing-support states."""

from __future__ import annotations

import math

from ...domain import FiniteInterval
from .line_observations import SourceCoordinateLine
from .model import (
    BoundaryAxis,
    BoundaryRole,
)
from .output_model import FrameBoundaryGeometry


def canonical_boundary_line(
    *,
    boundary_axis: BoundaryAxis,
    source_axis_long: BoundaryAxis,
    position_px: float,
    support_projection_px: FiniteInterval,
) -> SourceCoordinateLine:
    normal_x, normal_y = (
        (1.0, 0.0)
        if boundary_axis == BoundaryAxis.X
        else (0.0, 1.0)
    )
    return SourceCoordinateLine(
        normal_x=normal_x,
        normal_y=normal_y,
        offset_px=position_px,
        support_projection_px=support_projection_px,
        source_axis_long=source_axis_long,
    )


def boundary_line_at_state(
    boundary: FrameBoundaryGeometry,
    *,
    position_px: float,
    enclosing_support_slope: float | None = None,
) -> SourceCoordinateLine:
    """Materialize one boundary state without creating a placement angle.

    Only a directly observed enclosing support pair may retain its own local
    slope. Aperture and sequence boundaries remain source-axis aligned.
    """

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
    if enclosing_support_slope is None:
        normal_x = boundary.line.normal_x
        normal_y = boundary.line.normal_y
    else:
        if boundary.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}:
            raise ValueError("enclosing slope can only own cross boundaries")
        norm = math.hypot(1.0, enclosing_support_slope)
        normal_x, normal_y = (
            (-enclosing_support_slope / norm, 1.0 / norm)
            if source_axis_long == BoundaryAxis.X
            else (1.0 / norm, -enclosing_support_slope / norm)
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
