"""Flat numeric indexes over candidate-independent 2-D content topology."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ...domain import Box, FiniteInterval, ObservationId
from ..evidence.content_occupancy_model import ContentOccupancyObservationSet
from .trace_support import PIXEL_CENTER_EXTENT_PX


def source_axis_intervals(
    box: Box,
    layout: str,
) -> tuple[FiniteInterval, FiniteInterval]:
    if layout == "horizontal":
        return (
            FiniteInterval(float(box.left), float(box.right - 1)),
            FiniteInterval(float(box.top), float(box.bottom - 1)),
        )
    if layout == "vertical":
        return (
            FiniteInterval(float(box.top), float(box.bottom - 1)),
            FiniteInterval(float(box.left), float(box.right - 1)),
        )
    raise ValueError("unsupported content-veto layout")


def _merged_intervals(
    values: tuple[FiniteInterval, ...],
) -> tuple[FiniteInterval, ...]:
    if not values:
        return ()
    ordered = sorted(values, key=lambda item: (item.minimum, item.maximum))
    merged = [ordered[0]]
    for interval in ordered[1:]:
        previous = merged[-1]
        if (
            interval.minimum
            <= previous.maximum + PIXEL_CENTER_EXTENT_PX
        ):
            merged[-1] = FiniteInterval(
                previous.minimum,
                max(previous.maximum, interval.maximum),
            )
        else:
            merged.append(interval)
    return tuple(merged)


@dataclass(frozen=True)
class ContentSpanIndex:
    """Aligned numeric rows retaining the originating component identity."""

    coordinate_minimum: np.ndarray
    coordinate_maximum: np.ndarray
    orthogonal_minimum: np.ndarray
    orthogonal_maximum: np.ndarray
    coordinate_support_depth_px: np.ndarray
    support_depth_px: np.ndarray
    observation_ids: tuple[ObservationId, ...]

    def __post_init__(self) -> None:
        size = len(self.observation_ids)
        if any(
            value.ndim != 1 or value.size != size
            for value in (
                self.coordinate_minimum,
                self.coordinate_maximum,
                self.orthogonal_minimum,
                self.orthogonal_maximum,
                self.coordinate_support_depth_px,
                self.support_depth_px,
            )
        ):
            raise ValueError("content span index arrays are not aligned")

    @classmethod
    def empty(cls) -> "ContentSpanIndex":
        empty = np.empty(0, dtype=np.float64)
        return cls(empty, empty, empty, empty, empty, empty, ())


@dataclass(frozen=True)
class ContentTopologyIndex:
    """Two flat strip-axis indexes over exact SciPy-labelled cells."""

    by_sequence: ContentSpanIndex
    by_cross: ContentSpanIndex

    @classmethod
    def empty(cls) -> "ContentTopologyIndex":
        return cls(ContentSpanIndex.empty(), ContentSpanIndex.empty())


def _span_index(
    values: dict[
        tuple[float, float],
        dict[ObservationId, list[FiniteInterval]],
    ],
    *,
    coordinate_support_depth_px: float,
    orthogonal_support_depth_px: float,
) -> ContentSpanIndex:
    coordinate_minimum: list[float] = []
    coordinate_maximum: list[float] = []
    orthogonal_minimum: list[float] = []
    orthogonal_maximum: list[float] = []
    observation_ids: list[ObservationId] = []
    for (minimum, maximum), by_component in sorted(values.items()):
        for identity, intervals in sorted(
            by_component.items(),
            key=lambda item: str(item[0]),
        ):
            for interval in _merged_intervals(tuple(intervals)):
                coordinate_minimum.append(minimum)
                coordinate_maximum.append(maximum)
                orthogonal_minimum.append(interval.minimum)
                orthogonal_maximum.append(interval.maximum)
                observation_ids.append(identity)
    size = len(observation_ids)
    return ContentSpanIndex(
        coordinate_minimum=np.asarray(coordinate_minimum, dtype=np.float64),
        coordinate_maximum=np.asarray(coordinate_maximum, dtype=np.float64),
        orthogonal_minimum=np.asarray(orthogonal_minimum, dtype=np.float64),
        orthogonal_maximum=np.asarray(orthogonal_maximum, dtype=np.float64),
        coordinate_support_depth_px=np.full(
            size,
            coordinate_support_depth_px,
            dtype=np.float64,
        ),
        support_depth_px=np.full(
            size,
            orthogonal_support_depth_px,
            dtype=np.float64,
        ),
        observation_ids=tuple(observation_ids),
    )


def build_content_topology_index(
    observations: ContentOccupancyObservationSet,
    *,
    layout: str,
) -> ContentTopologyIndex:
    if (
        observations.long_support_depth_px is None
        or observations.cross_support_depth_px is None
    ):
        return ContentTopologyIndex.empty()
    if layout == "horizontal":
        sequence_support_depth_px = float(observations.long_support_depth_px)
        cross_support_depth_px = float(observations.cross_support_depth_px)
    elif layout == "vertical":
        sequence_support_depth_px = float(observations.cross_support_depth_px)
        cross_support_depth_px = float(observations.long_support_depth_px)
    else:
        raise ValueError("unsupported content-veto layout")

    sequence_values: dict[
        tuple[float, float],
        dict[ObservationId, list[FiniteInterval]],
    ] = {}
    cross_values: dict[
        tuple[float, float],
        dict[ObservationId, list[FiniteInterval]],
    ] = {}
    for observation in observations.observations:
        for cell in observation.source_cells:
            sequence, cross = source_axis_intervals(cell, layout)
            sequence_values.setdefault(
                (sequence.minimum, sequence.maximum), {}
            ).setdefault(observation.observation_id, []).append(cross)
            cross_values.setdefault(
                (cross.minimum, cross.maximum), {}
            ).setdefault(observation.observation_id, []).append(sequence)
    return ContentTopologyIndex(
        by_sequence=_span_index(
            sequence_values,
            coordinate_support_depth_px=sequence_support_depth_px,
            orthogonal_support_depth_px=cross_support_depth_px,
        ),
        by_cross=_span_index(
            cross_values,
            coordinate_support_depth_px=cross_support_depth_px,
            orthogonal_support_depth_px=sequence_support_depth_px,
        ),
    )
