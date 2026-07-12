from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ...domain import Box
from ...geometry.detection_parameters import SeparatorContinuityParameters
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
    minimum_coverage_ratio: float
    minimum_continuity_ratio: float


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
    parameters: SeparatorContinuityParameters,
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
        extreme = (band <= int(parameters.extreme_dark_threshold)) | (
            band >= int(parameters.extreme_light_threshold)
        )
        row_support = extreme.mean(axis=1) >= float(parameters.minimum_row_activity)
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
        supported = bool(
            coverage >= float(parameters.minimum_cross_axis_coverage)
            and continuity >= float(parameters.minimum_cross_axis_continuity)
        )
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
    supported_count = sum(
        record.state == EvidenceState.SUPPORTED for record in records
    )
    contradicted_count = sum(
        record.state == EvidenceState.CONTRADICTED for record in records
    )
    if records and supported_count == len(records):
        state = EvidenceState.SUPPORTED
        reason = "all_observed_bands_cross_short_axis"
    elif records and contradicted_count == len(records):
        state = EvidenceState.CONTRADICTED
        reason = "observed_bands_lack_cross_axis_continuity"
    elif supported_count:
        state = EvidenceState.UNAVAILABLE
        reason = "observed_band_continuity_mixed"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "separator_continuity_unavailable"
    return SeparatorContinuityEvidence(
        state,
        reason,
        tuple(records),
        tuple(enriched),
        float(parameters.minimum_cross_axis_coverage),
        float(parameters.minimum_cross_axis_continuity),
    )


def continuity_state_for_observation(
    evidence: SeparatorContinuityEvidence,
    observation: SeparatorBandObservation,
) -> EvidenceState:
    for record in evidence.records:
        if record.start == observation.start and record.end == observation.end:
            return record.state
    return EvidenceState.UNAVAILABLE
