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


def _stable_id(lane_id: str, box: Box, reliability: float) -> ObservationId:
    payload = "\x1f".join(
        (
            lane_id,
            str(box.left),
            str(box.top),
            str(box.right),
            str(box.bottom),
            reliability.hex(),
        )
    ).encode("utf-8")
    return ObservationId(f"content:{sha256(payload).hexdigest()[:24]}")


@dataclass(frozen=True)
class ContentOccupancyObservation:
    observation_id: ObservationId
    lane_id: str
    source_box: Box
    reliability: float
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or not self.source_box.valid()
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
    overflowed: bool

    def __post_init__(self) -> None:
        if (
            not self.lane_id
            or self.long_sample_count <= 0
            or self.cross_sample_count <= 0
            or self.long_sample_count > MAX_CONTENT_SAMPLES_LONG
            or self.cross_sample_count > MAX_CONTENT_SAMPLES_CROSS
            or len(self.observations) > MAX_CONTENT_OBSERVATIONS_PER_LANE
            or any(item.lane_id != self.lane_id for item in self.observations)
        ):
            raise ValueError("content occupancy observation set is invalid")


def _source_box_from_work_box(box: Box, layout: str) -> Box:
    if layout == "horizontal":
        return box
    if layout == "vertical":
        return Box(box.top, box.left, box.bottom, box.right)
    raise ValueError(f"unsupported content-observation layout: {layout}")


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
    contrast = np.std(sampled, axis=0, dtype=np.float64)
    center = float(np.median(contrast))
    mad = float(np.median(np.abs(contrast - center)))
    threshold = center + max(4.0, 4.0 * 1.4826 * mad)
    occupied = contrast > threshold
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate((*occupied.tolist(), False)):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index))
            start = None
    overflowed = len(runs) > MAX_CONTENT_OBSERVATIONS_PER_LANE
    observations: list[ContentOccupancyObservation] = []
    for start, stop in runs[:MAX_CONTENT_OBSERVATIONS_PER_LANE]:
        left = lane_work_box.left + int(long_indices[start])
        right_index = min(stop, len(long_indices) - 1)
        right = lane_work_box.left + int(long_indices[right_index]) + 1
        work_box = Box(
            left,
            lane_work_box.top,
            min(lane_work_box.right, right),
            lane_work_box.bottom,
        )
        source_box = _source_box_from_work_box(work_box, layout)
        peak = float(np.max(contrast[start:stop]))
        reliability = min(1.0, max(1.0e-9, (peak - threshold) / 32.0))
        identity = _stable_id(lane_id, source_box, reliability)
        observations.append(
            ContentOccupancyObservation(
                observation_id=identity,
                lane_id=lane_id,
                source_box=source_box,
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
        overflowed=overflowed,
    )
