"""Typed contract for candidate-independent two-dimensional content evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import Box, ObservationId


@dataclass(frozen=True)
class ContentOccupancyMeasurementSpec:
    """Physical/statistical measurement settings, never crop tolerances."""

    cell_extent_mm: float = 0.25
    minimum_internal_gradient_signal_codes: float = 3.0
    minimum_second_eigenvalue_fraction: float = 0.10
    internal_subcells_per_axis: int = 4
    minimum_component_interior_radius_cells: int = 1

    def __post_init__(self) -> None:
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (
                self.cell_extent_mm,
                self.minimum_internal_gradient_signal_codes,
                self.minimum_second_eigenvalue_fraction,
            )
        ):
            raise ValueError("content-occupancy measurement spec must be positive")
        if (
            self.minimum_second_eigenvalue_fraction >= 1.0
            # A 3x3 Scharr footprint leaves a 2x2 set of gradient samples
            # wholly inside a four-by-four physical cell.  Smaller grids borrow
            # pixels from a neighbour and can turn a boundary into false 2-D
            # content.
            or self.internal_subcells_per_axis != 4
            or self.minimum_component_interior_radius_cells != 1
        ):
            raise ValueError("content-occupancy topology is not canonical")


CONTENT_OCCUPANCY_MEASUREMENT_SPEC = ContentOccupancyMeasurementSpec()


@dataclass(frozen=True)
class ContentOccupancyObservation:
    """One exact occupied component in source coordinates."""

    observation_id: ObservationId
    lane_id: str
    source_box: Box
    source_cells: tuple[Box, ...]
    reliability: float

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or not self.source_box.valid()
            or not self.source_cells
            or any(not cell.valid() for cell in self.source_cells)
            or len(set(self.source_cells)) != len(self.source_cells)
            or any(
                cell.left < self.source_box.left
                or cell.top < self.source_box.top
                or cell.right > self.source_box.right
                or cell.bottom > self.source_box.bottom
                for cell in self.source_cells
            )
            or not math.isfinite(self.reliability)
            or self.reliability <= 0.0
        ):
            raise ValueError("content occupancy observation is invalid")


@dataclass(frozen=True)
class ContentOccupancyObservationSet:
    lane_id: str
    observations: tuple[ContentOccupancyObservation, ...]
    long_step_px: int | None
    cross_step_px: int | None
    long_sample_count: int
    cross_sample_count: int
    occupied_cell_count: int
    long_support_depth_px: int | None
    cross_support_depth_px: int | None

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or (self.long_step_px is None) != (self.cross_step_px is None)
            or (self.long_support_depth_px is None)
            != (self.cross_support_depth_px is None)
            or (
                self.long_step_px is not None
                and (
                    self.long_step_px <= 0
                    or self.cross_step_px <= 0
                    or self.long_support_depth_px is None
                    or self.long_support_depth_px < self.long_step_px
                    or self.cross_support_depth_px is None
                    or self.cross_support_depth_px < self.cross_step_px
                )
            )
            or self.long_sample_count < 0
            or self.cross_sample_count < 0
            or self.occupied_cell_count < len(self.observations)
            or any(item.lane_id != self.lane_id for item in self.observations)
        ):
            raise ValueError("content occupancy observation set is invalid")
