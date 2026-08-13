"""Bounded physical search corridor and sequence-domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import FiniteInterval
from .model import BoundaryAxis, BoundaryRole
from .trace_support import PIXEL_CENTER_EXTENT_PX


@dataclass(frozen=True)
class PhotoEdgeSearchCorridor:
    corridor_id: str
    lane_id: str
    role: BoundaryRole
    boundary_axis: BoundaryAxis
    trace_positions_px: tuple[int, ...]
    core_intervals_px: tuple[FiniteInterval, ...]
    measurement_intervals_px: tuple[FiniteInterval, ...]
    measurement_halo_px: int
    provenance: str = "scan_canvas_format_search_proposal"

    def __post_init__(self) -> None:
        count = len(self.trace_positions_px)
        if (
            not self.corridor_id
            or not self.lane_id
            or self.role not in {BoundaryRole.TOP, BoundaryRole.BOTTOM}
            or count == 0
            or len(self.core_intervals_px) != count
            or len(self.measurement_intervals_px) != count
            or self.measurement_halo_px <= 0
            or self.provenance != "scan_canvas_format_search_proposal"
        ):
            raise ValueError("photo-edge search corridor is invalid")
        for core, measured in zip(
            self.core_intervals_px,
            self.measurement_intervals_px,
            strict=True,
        ):
            if (
                measured.minimum > core.minimum
                or measured.maximum < core.maximum
            ):
                raise ValueError(
                    "measurement halo must contain corridor core"
                )


@dataclass(frozen=True)
class SequenceAnchorTile:
    tile_id: str
    core_px: FiniteInterval
    measurement_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.tile_id
            or self.core_px.maximum <= self.core_px.minimum
            or self.measurement_px.minimum > self.core_px.minimum
            or self.measurement_px.maximum + PIXEL_CENTER_EXTENT_PX
            < self.core_px.maximum
        ):
            raise ValueError("sequence anchor tile is invalid")


@dataclass(frozen=True)
class SequenceAnchorDiscoveryDomain:
    domain_id: str
    lane_id: str
    long_axis_extent_px: int
    authoritative_sequence_length: int
    tiles: tuple[SequenceAnchorTile, ...]
    query_execution_order: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.domain_id
            or not self.lane_id
            or self.long_axis_extent_px <= 0
            or self.authoritative_sequence_length <= 0
            or not self.tiles
        ):
            raise ValueError("sequence anchor discovery domain is invalid")
        tile_ids = tuple(item.tile_id for item in self.tiles)
        if len(set(tile_ids)) != len(tile_ids):
            raise ValueError("sequence anchor tiles must be unique")
        if set(self.query_execution_order) != set(tile_ids):
            raise ValueError("query order must cover every anchor tile")
        ordered = sorted(self.tiles, key=lambda item: item.core_px.minimum)
        if ordered[0].core_px.minimum > 0.0:
            raise ValueError("anchor tiles must begin at lane authority")
        if ordered[-1].core_px.maximum < self.long_axis_extent_px:
            raise ValueError("anchor tiles must end at lane authority")
        for left, right in zip(ordered, ordered[1:]):
            if not math.isclose(
                left.core_px.maximum,
                right.core_px.minimum,
                abs_tol=1.0e-9,
            ):
                raise ValueError("anchor tile cores must be seamless")
