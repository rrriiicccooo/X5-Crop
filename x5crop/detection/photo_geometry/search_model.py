"""Bounded physical search corridor and sequence-domain contracts."""

from __future__ import annotations

from dataclasses import dataclass

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
    provenance: str = "compiled_template_search_corridor"

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
            or self.provenance != "compiled_template_search_corridor"
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
class SequenceAnchorWindow:
    window_id: str
    core_px: FiniteInterval
    measurement_px: FiniteInterval

    def __post_init__(self) -> None:
        if (
            not self.window_id
            or self.core_px.maximum <= self.core_px.minimum
            or self.measurement_px.minimum > self.core_px.minimum
            or self.measurement_px.maximum + PIXEL_CENTER_EXTENT_PX
            < self.core_px.maximum
        ):
            raise ValueError("sequence anchor window is invalid")


@dataclass(frozen=True)
class SequenceAnchorDiscoveryDomain:
    domain_id: str
    lane_id: str
    long_axis_extent_px: int
    support_interval_px: FiniteInterval
    authoritative_sequence_length: int
    windows: tuple[SequenceAnchorWindow, ...]
    query_execution_order: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.domain_id
            or not self.lane_id
            or self.long_axis_extent_px <= 0
            or not isinstance(self.support_interval_px, FiniteInterval)
            or self.support_interval_px.minimum < 0.0
            or self.support_interval_px.maximum > self.long_axis_extent_px - 1
            or self.authoritative_sequence_length <= 0
            or not self.windows
        ):
            raise ValueError("sequence anchor discovery domain is invalid")
        window_ids = tuple(item.window_id for item in self.windows)
        if len(set(window_ids)) != len(window_ids):
            raise ValueError("sequence anchor windows must be unique")
        if set(self.query_execution_order) != set(window_ids):
            raise ValueError("query order must cover every anchor window")
        ordered = sorted(self.windows, key=lambda item: item.core_px.minimum)
        for left, right in zip(ordered, ordered[1:]):
            if left.core_px.maximum > right.core_px.minimum:
                raise ValueError("sequence anchor windows must not overlap")
        if any(
            item.measurement_px.minimum < self.support_interval_px.minimum
            or item.measurement_px.maximum > self.support_interval_px.maximum
            for item in ordered
        ):
            raise ValueError("anchor window leaves coarse support")
