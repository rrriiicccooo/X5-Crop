from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ...domain import Box
from ...image.statistics import ImageMeasurementStatistics
from ..physical.model import SequenceSolution
from x5crop.domain import SeparatorBandObservation
from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class SeparatorContinuityRecord:
    start: float
    end: float
    state: EvidenceState
    coverage_ratio: float | None
    continuity_ratio: float | None
    break_count: int | None
    straightness: float | None
    reason: str


@dataclass(frozen=True)
class SeparatorContinuityEvidence:
    state: EvidenceState
    reason: str
    records: tuple[SeparatorContinuityRecord, ...]
    observations: tuple[SeparatorBandObservation, ...]


def _longest_true_run(mask: np.ndarray) -> int:
    longest = 0
    current = 0
    for value in mask.astype(bool):
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _break_count(mask: np.ndarray) -> int:
    transitions = np.diff(mask.astype(np.int8), prepend=0, append=0)
    return int(max(0, np.count_nonzero(transitions == 1) - 1))


def _cross_axis_path_exists(mask: np.ndarray) -> bool:
    if mask.ndim != 2 or not mask.shape[0] or not mask.shape[1]:
        return False
    reachable = mask[0].astype(bool, copy=True)
    for row in mask[1:]:
        adjacent = reachable.copy()
        adjacent[1:] |= reachable[:-1]
        adjacent[:-1] |= reachable[1:]
        reachable = row.astype(bool, copy=False) & adjacent
        if not reachable.any():
            return False
    return bool(reachable.any())


def _measurement_corridor(
    geometry: SequenceSolution,
    observation: SeparatorBandObservation,
) -> Box:
    if observation.lane_box is not None:
        return observation.lane_box
    holder = geometry.holder_span.box
    crop = geometry.crop_envelope.box
    return Box(
        holder.left,
        max(holder.top, crop.top),
        holder.right,
        min(holder.bottom, crop.bottom),
    )


def separator_cross_axis_continuity_evidence(
    gray_work: np.ndarray,
    geometry: SequenceSolution,
    statistics: ImageMeasurementStatistics,
) -> SeparatorContinuityEvidence:
    records: list[SeparatorContinuityRecord] = []
    enriched: list[SeparatorBandObservation] = []
    for observation in geometry.separator_observations:
        corridor = _measurement_corridor(geometry, observation).clamp(
            gray_work.shape[1],
            gray_work.shape[0],
        )
        start = max(corridor.left, int(np.floor(observation.start)))
        end = min(corridor.right, int(np.ceil(observation.end)))
        if not corridor.valid() or end <= start:
            records.append(
                SeparatorContinuityRecord(
                    observation.start,
                    observation.end,
                    EvidenceState.UNAVAILABLE,
                    None,
                    None,
                    None,
                    None,
                    "separator_band_outside_measurement_corridor",
                )
            )
            enriched.append(observation)
            continue
        band = gray_work[corridor.top:corridor.bottom, start:end]
        if statistics.intensity_high <= statistics.intensity_low:
            records.append(
                SeparatorContinuityRecord(
                    observation.start,
                    observation.end,
                    EvidenceState.UNAVAILABLE,
                    None,
                    None,
                    None,
                    None,
                    "separator_tonal_reference_unavailable",
                )
            )
            enriched.append(observation)
            continue
        extreme = (band <= float(statistics.intensity_low)) | (
            band >= float(statistics.intensity_high)
        )
        row_support = extreme.any(axis=1)
        coverage = float(row_support.mean()) if row_support.size else 0.0
        continuity = (
            float(_longest_true_run(row_support)) / float(max(1, len(row_support)))
        )
        breaks = _break_count(row_support)
        row_centers = []
        for row in extreme:
            positions = np.flatnonzero(row)
            if positions.size:
                row_centers.append(float(positions.mean()))
        straightness = (
            max(
                0.0,
                1.0
                - float(np.std(row_centers)) / max(1.0, float(end - start)),
            )
            if row_centers
            else 0.0
        )
        supported = _cross_axis_path_exists(extreme)
        records.append(
            SeparatorContinuityRecord(
                observation.start,
                observation.end,
                EvidenceState.SUPPORTED if supported else EvidenceState.CONTRADICTED,
                coverage,
                continuity,
                breaks,
                straightness,
                "supported" if supported else "cross_axis_continuity_weak",
            )
        )
        enriched.append(replace(observation, continuity=continuity))
    selected_keys = {
        (
            boundary.assignment.observation.start,
            boundary.assignment.observation.end,
        )
        for boundary in geometry.frame_boundaries
        if boundary.assignment is not None
        and boundary.assignment.used_for_boundary
        and boundary.assignment.independent
    }
    selected_records = tuple(
        record
        for record in records
        if (record.start, record.end) in selected_keys
    )
    supported_count = sum(
        record.state == EvidenceState.SUPPORTED for record in selected_records
    )
    contradicted_count = sum(
        record.state == EvidenceState.CONTRADICTED for record in selected_records
    )
    if selected_records and supported_count == len(selected_records):
        state = EvidenceState.SUPPORTED
        reason = "selected_separator_bands_cross_short_axis"
    elif selected_records and contradicted_count == len(selected_records):
        state = EvidenceState.CONTRADICTED
        reason = "selected_separator_bands_lack_cross_axis_continuity"
    elif supported_count:
        state = EvidenceState.UNAVAILABLE
        reason = "selected_separator_band_continuity_mixed"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "selected_separator_continuity_unavailable"
    return SeparatorContinuityEvidence(
        state,
        reason,
        tuple(records),
        tuple(enriched),
    )


def continuity_state_for_observation(
    evidence: SeparatorContinuityEvidence,
    observation: SeparatorBandObservation,
) -> EvidenceState:
    for record in evidence.records:
        if record.start == observation.start and record.end == observation.end:
            return record.state
    return EvidenceState.UNAVAILABLE
