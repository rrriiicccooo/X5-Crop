"""Candidate-independent spatial index for one lane's observations."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from ...domain import FiniteInterval, ObservationId
from .line_observations import PhotoBoundaryObservation
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation


@dataclass(frozen=True)
class _IntervalEntry:
    observation_id: ObservationId
    interval: FiniteInterval


@dataclass(frozen=True)
class ObservationIntervalIndex:
    """Query exact interval relations without rescanning every observation."""

    entries: tuple[_IntervalEntry, ...]
    _by_minimum: tuple[_IntervalEntry, ...] = field(init=False, repr=False)
    _minimums: tuple[float, ...] = field(init=False, repr=False)
    _by_maximum: tuple[_IntervalEntry, ...] = field(init=False, repr=False)
    _maximums: tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len({item.observation_id for item in self.entries}) != len(self.entries):
            raise ValueError("interval index observation ids must be unique")
        by_minimum = tuple(
            sorted(
                self.entries,
                key=lambda item: (
                    item.interval.minimum,
                    item.interval.maximum,
                    str(item.observation_id),
                ),
            )
        )
        by_maximum = tuple(
            sorted(
                self.entries,
                key=lambda item: (
                    item.interval.maximum,
                    item.interval.minimum,
                    str(item.observation_id),
                ),
            )
        )
        object.__setattr__(self, "_by_minimum", by_minimum)
        object.__setattr__(
            self,
            "_minimums",
            tuple(item.interval.minimum for item in by_minimum),
        )
        object.__setattr__(self, "_by_maximum", by_maximum)
        object.__setattr__(
            self,
            "_maximums",
            tuple(item.interval.maximum for item in by_maximum),
        )

    def intersecting(self, interval: FiniteInterval) -> tuple[ObservationId, ...]:
        stop = bisect_right(self._minimums, interval.maximum)
        return tuple(
            item.observation_id
            for item in self._by_minimum[:stop]
            if item.interval.maximum >= interval.minimum
        )

    def strictly_inside(self, interval: FiniteInterval) -> tuple[ObservationId, ...]:
        start = bisect_right(self._minimums, interval.minimum)
        stop = bisect_left(self._minimums, interval.maximum)
        return tuple(
            item.observation_id
            for item in self._by_minimum[start:stop]
            if item.interval.maximum < interval.maximum
        )

    def entirely_before(self, coordinate: float) -> tuple[ObservationId, ...]:
        stop = bisect_left(self._maximums, coordinate)
        return tuple(item.observation_id for item in self._by_maximum[:stop])

    def entirely_after(self, coordinate: float) -> tuple[ObservationId, ...]:
        start = bisect_right(self._minimums, coordinate)
        return tuple(item.observation_id for item in self._by_minimum[start:])


@dataclass(frozen=True)
class ChainObservationSpatialIndex:
    """One immutable lookup owner shared by every chain in a lane."""

    sequence_edges: tuple[BoundaryEdgeObservation, ...]
    separator_bands: tuple[SeparatorBandObservation, ...]
    top_bottom_observations: tuple[PhotoBoundaryObservation, ...]
    edge_intervals: ObservationIntervalIndex
    edge_by_id: dict[ObservationId, BoundaryEdgeObservation] = field(
        repr=False,
        compare=False,
    )
    raw_observation_ids: tuple[ObservationId, ...]


def build_chain_observation_spatial_index(
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    top_bottom_observations: tuple[PhotoBoundaryObservation, ...],
) -> ChainObservationSpatialIndex:
    edge_by_id = {item.observation_id: item for item in sequence_edges}
    if len(edge_by_id) != len(sequence_edges):
        raise ValueError("sequence edge observation ids must be unique")
    raw_ids = tuple(
        sorted(
            {
                *(item.observation_id for item in sequence_edges),
                *(item.observation_id for item in separator_bands),
                *(item.observation_id for item in top_bottom_observations),
            },
            key=str,
        )
    )
    return ChainObservationSpatialIndex(
        sequence_edges=sequence_edges,
        separator_bands=separator_bands,
        top_bottom_observations=top_bottom_observations,
        edge_intervals=ObservationIntervalIndex(
            tuple(
                _IntervalEntry(item.observation_id, item.coordinate_interval_px)
                for item in sequence_edges
            )
        ),
        edge_by_id=edge_by_id,
        raw_observation_ids=raw_ids,
    )
