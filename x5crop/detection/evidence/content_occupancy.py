from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

import numpy as np

from ...domain import (
    Box,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
)


MAX_CONTENT_SAMPLES_LONG = 256
MAX_CONTENT_SAMPLES_CROSS = 64
MAX_CONTENT_OBSERVATIONS_PER_LANE = 64
MAX_CONTENT_CELL_RUNS_PER_LANE = 1024


def _stable_id(
    lane_id: str,
    cells: tuple[Box, ...],
    reliability: float,
) -> ObservationId:
    payload = "\x1f".join(
        (
            lane_id,
            *(str(value) for cell in cells for value in (
                cell.left,
                cell.top,
                cell.right,
                cell.bottom,
            )),
            reliability.hex(),
        )
    ).encode("utf-8")
    return ObservationId(f"content:{sha256(payload).hexdigest()[:24]}")


@dataclass(frozen=True)
class ContentOccupancyObservation:
    observation_id: ObservationId
    lane_id: str
    source_box: Box
    source_cells: tuple[Box, ...]
    reliability: float
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or not self.source_box.valid()
            or not self.source_cells
            or any(not cell.valid() for cell in self.source_cells)
            or min(cell.left for cell in self.source_cells) < self.source_box.left
            or min(cell.top for cell in self.source_cells) < self.source_box.top
            or max(cell.right for cell in self.source_cells) > self.source_box.right
            or max(cell.bottom for cell in self.source_cells) > self.source_box.bottom
            or not math.isfinite(self.reliability)
            or not 0.0 < self.reliability <= 1.0
            or self.provenance.root_measurement
            != MeasurementIdentity.CONTENT_OCCUPANCY
            or self.provenance.observation_id != self.observation_id
        ):
            raise ValueError("content occupancy observation is invalid")


@dataclass(frozen=True)
class ContentOccupancyObservationSet:
    lane_id: str
    observations: tuple[ContentOccupancyObservation, ...]
    long_sample_count: int
    cross_sample_count: int
    proposed_observation_count: int
    proposed_cell_run_count: int
    overflowed: bool

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.long_sample_count <= 0
            or self.cross_sample_count <= 0
            or self.long_sample_count > MAX_CONTENT_SAMPLES_LONG
            or self.cross_sample_count > MAX_CONTENT_SAMPLES_CROSS
            or self.proposed_observation_count < len(self.observations)
            or self.proposed_cell_run_count
            < sum(len(item.source_cells) for item in self.observations)
            or len(self.observations) > MAX_CONTENT_OBSERVATIONS_PER_LANE
            or sum(len(item.source_cells) for item in self.observations)
            > MAX_CONTENT_CELL_RUNS_PER_LANE
            or any(item.lane_id != self.lane_id for item in self.observations)
            or self.overflowed
            != (
                self.proposed_observation_count
                > MAX_CONTENT_OBSERVATIONS_PER_LANE
                or self.proposed_cell_run_count
                > MAX_CONTENT_CELL_RUNS_PER_LANE
            )
        ):
            raise ValueError("content occupancy observation set is invalid")

    @property
    def producer_excess_count(self) -> int:
        return max(
            0,
            self.proposed_observation_count
            - MAX_CONTENT_OBSERVATIONS_PER_LANE,
            self.proposed_cell_run_count
            - MAX_CONTENT_CELL_RUNS_PER_LANE,
        )


def _source_box_from_work_box(box: Box, layout: str) -> Box:
    if layout == "horizontal":
        return box
    if layout == "vertical":
        return Box(box.top, box.left, box.bottom, box.right)
    raise ValueError(f"unsupported content-observation layout: {layout}")


def _sample_edges(indices: np.ndarray, extent: int) -> np.ndarray:
    edges = np.empty(indices.size + 1, dtype=np.int64)
    edges[0] = 0
    edges[-1] = extent
    if indices.size > 1:
        edges[1:-1] = (indices[:-1] + indices[1:] + 1) // 2
    return edges


def _components(mask: np.ndarray) -> tuple[tuple[tuple[int, int], ...], ...]:
    visited = np.zeros(mask.shape, dtype=np.bool_)
    values: list[tuple[tuple[int, int], ...]] = []
    height, width = mask.shape
    for row in range(height):
        for column in range(width):
            if not mask[row, column] or visited[row, column]:
                continue
            pending = [(row, column)]
            visited[row, column] = True
            component: list[tuple[int, int]] = []
            while pending:
                current_row, current_column = pending.pop()
                component.append((current_row, current_column))
                for next_row, next_column in (
                    (current_row - 1, current_column),
                    (current_row + 1, current_column),
                    (current_row, current_column - 1),
                    (current_row, current_column + 1),
                ):
                    if (
                        0 <= next_row < height
                        and 0 <= next_column < width
                        and mask[next_row, next_column]
                        and not visited[next_row, next_column]
                    ):
                        visited[next_row, next_column] = True
                        pending.append((next_row, next_column))
            values.append(tuple(sorted(component)))
    return tuple(values)


def _component_work_cells(
    component: tuple[tuple[int, int], ...],
    *,
    lane_work_box: Box,
    long_edges: np.ndarray,
    cross_edges: np.ndarray,
) -> tuple[Box, ...]:
    by_row: dict[int, list[int]] = {}
    for row, column in component:
        by_row.setdefault(row, []).append(column)
    cells: list[Box] = []
    for row, columns in sorted(by_row.items()):
        ordered = sorted(columns)
        start = ordered[0]
        previous = start
        for column in (*ordered[1:], ordered[-1] + 2):
            if column != previous + 1:
                cells.append(
                    Box(
                        lane_work_box.left + int(long_edges[start]),
                        lane_work_box.top + int(cross_edges[row]),
                        lane_work_box.left + int(long_edges[previous + 1]),
                        lane_work_box.top + int(cross_edges[row + 1]),
                    )
                )
                start = column
            previous = column
    return tuple(cells)


def observe_content_occupancy(
    gray_work: np.ndarray,
    *,
    lane_id: str,
    lane_work_box: Box,
    layout: str,
) -> ContentOccupancyObservationSet:
    if gray_work.ndim != 2 or not lane_work_box.valid():
        raise ValueError("content occupancy requires a valid gray lane")
    lane = gray_work[
        lane_work_box.top : lane_work_box.bottom,
        lane_work_box.left : lane_work_box.right,
    ]
    long_count = min(MAX_CONTENT_SAMPLES_LONG, lane.shape[1])
    cross_count = min(MAX_CONTENT_SAMPLES_CROSS, lane.shape[0])
    long_indices = np.linspace(
        0,
        lane.shape[1] - 1,
        num=long_count,
        dtype=np.int64,
    )
    cross_indices = np.linspace(
        0,
        lane.shape[0] - 1,
        num=cross_count,
        dtype=np.int64,
    )
    sampled = lane[np.ix_(cross_indices, long_indices)].astype(
        np.float32,
        copy=False,
    )
    horizontal = np.zeros(sampled.shape, dtype=np.float32)
    vertical = np.zeros(sampled.shape, dtype=np.float32)
    horizontal[:, 1:] = np.abs(np.diff(sampled, axis=1))
    vertical[1:, :] = np.abs(np.diff(sampled, axis=0))
    activity = np.maximum(horizontal, vertical)
    center = float(np.median(activity))
    mad = float(np.median(np.abs(activity - center)))
    threshold = center + max(4.0, 4.0 * 1.4826 * mad)
    occupied = activity > threshold
    components = _components(occupied)
    long_edges = _sample_edges(long_indices, lane.shape[1])
    cross_edges = _sample_edges(cross_indices, lane.shape[0])
    component_cells = tuple(
        _component_work_cells(
            component,
            lane_work_box=lane_work_box,
            long_edges=long_edges,
            cross_edges=cross_edges,
        )
        for component in components
    )
    proposed_cell_run_count = sum(len(value) for value in component_cells)
    overflowed = (
        len(components) > MAX_CONTENT_OBSERVATIONS_PER_LANE
        or proposed_cell_run_count > MAX_CONTENT_CELL_RUNS_PER_LANE
    )
    observations: list[ContentOccupancyObservation] = []
    retained_components = () if overflowed else components
    retained_cells = () if overflowed else component_cells
    for component, work_cells in zip(
        retained_components,
        retained_cells,
        strict=True,
    ):
        source_cells = tuple(
            _source_box_from_work_box(cell, layout) for cell in work_cells
        )
        source_box = Box(
            min(cell.left for cell in source_cells),
            min(cell.top for cell in source_cells),
            max(cell.right for cell in source_cells),
            max(cell.bottom for cell in source_cells),
        )
        peak = max(float(activity[row, column]) for row, column in component)
        reliability = min(
            1.0,
            max(1.0e-9, (peak - threshold) / max(8.0, threshold)),
        )
        identity = _stable_id(lane_id, source_cells, reliability)
        observations.append(
            ContentOccupancyObservation(
                observation_id=identity,
                lane_id=lane_id,
                source_box=source_box,
                source_cells=source_cells,
                reliability=reliability,
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.CONTENT_OCCUPANCY,
                    observation_id=identity,
                    dependencies=(MeasurementIdentity.BASE_GRAY,),
                    description=(
                        "bounded candidate-independent source content occupancy"
                    ),
                ),
            )
        )
    return ContentOccupancyObservationSet(
        lane_id=lane_id,
        observations=tuple(observations),
        long_sample_count=long_count,
        cross_sample_count=cross_count,
        proposed_observation_count=len(components),
        proposed_cell_run_count=proposed_cell_run_count,
        overflowed=overflowed,
    )
