"""Registered canonical source domain for terminal phase admission."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import Box, FiniteInterval, WorkspaceExtent
from .axis_layout import axis_interval
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import AuthoritySide, BoundaryAxis
from .output_model import sampling_authority_bounds, source_boundary_sides
from .template_model import SequenceFit


@dataclass(frozen=True)
class PhaseSourceDomain:
    """TIFF and lane identity, without coordinate or clipping authority."""

    lane_id: str
    sampling_authority_box: Box
    source_extent: WorkspaceExtent
    width_axis: BoundaryAxis

    def __post_init__(self) -> None:
        if (
            not isinstance(self.lane_id, str)
            or not self.lane_id
            or not isinstance(self.width_axis, BoundaryAxis)
        ):
            raise ValueError("phase source domain identity is invalid")
        if not isinstance(self.sampling_authority_box, Box):
            raise TypeError("phase source domain requires a sampling box")
        if not isinstance(self.source_extent, WorkspaceExtent) or any(
            type(value) is not int
            for value in (self.source_extent.width, self.source_extent.height)
        ):
            raise ValueError("phase source domain requires canonical integer dimensions")
        source_boundary_sides(self.sampling_authority_box, self.source_extent)

    def validate_registration(
        self,
        holder_span_px: FiniteInterval | None,
        measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    ) -> None:
        if any(
            not isinstance(item, PhotoBoundaryMeasurementSet)
            for item in measurement_sets
        ):
            raise TypeError("phase source domain requires typed measurement sets")
        if holder_span_px != axis_interval(
            self.sampling_authority_box,
            self.width_axis,
        ):
            raise ValueError("phase holder span differs from its canonical source domain")
        if any(
            item.query.lane_id != self.lane_id
            or item.query.boundary_axis != self.width_axis
            for item in measurement_sets
        ):
            raise ValueError("phase queries differ from their canonical source domain")


def source_clipped_terminal_roles(
    fit: SequenceFit,
    domain: PhaseSourceDomain,
) -> tuple[int, ...] | None:
    """Return true source-clipped terminals, or None for invalid lane geometry.

    An empty tuple is valid geometry without source clipping. Coordinates are
    read unchanged; this classification grants no role or placement authority.
    The scan visits at most R coordinates of one already fitted candidate.
    """

    if not isinstance(domain, PhaseSourceDomain):
        raise TypeError("terminal source classification requires a typed domain")
    positions = fit.model_role_positions_px
    bounds = sampling_authority_bounds(
        domain.sampling_authority_box,
        domain.source_extent,
    )
    sides = source_boundary_sides(
        domain.sampling_authority_box,
        domain.source_extent,
    )
    low, high = (
        (bounds[0], bounds[2])
        if domain.width_axis == BoundaryAxis.X
        else (bounds[1], bounds[3])
    )
    low_side, high_side = (
        (AuthoritySide.LEFT, AuthoritySide.RIGHT)
        if domain.width_axis == BoundaryAxis.X
        else (AuthoritySide.TOP, AuthoritySide.BOTTOM)
    )
    if any(not low <= position <= high for position in positions[1:-1]):
        return None
    low_terminal = 0 if fit.template.direction == 1 else len(positions) - 1
    high_terminal = len(positions) - 1 - low_terminal
    clipped = []
    for index in (0, len(positions) - 1):
        if positions[index] < low:
            if index != low_terminal or low_side not in sides:
                return None
            clipped.append(index)
        if positions[index] > high:
            if index != high_terminal or high_side not in sides:
                return None
            clipped.append(index)
    if any(
        fit.template.direction * (end - start) <= 0.0
        or min(max(start, end), high) <= max(min(start, end), low)
        for start, end in zip(positions[::2], positions[1::2], strict=True)
    ):
        return None
    return tuple(clipped)
