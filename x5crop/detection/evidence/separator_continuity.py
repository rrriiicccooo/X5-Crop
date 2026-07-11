from __future__ import annotations

from dataclasses import dataclass, replace
import numpy as np

from ...domain import Box, SeparatorBandObservation
from ...gap_methods import is_hard_gap_method
from ...geometry.detection_parameters import HardGapTrustParameters
from ...geometry.gap_trust import hard_gap_pixel_signals, hard_gap_signal_flags
from .state import EvidenceState


@dataclass(frozen=True)
class SeparatorContinuityRecord:
    index: int
    method: str
    measured: bool
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


def supported_hard_separator_observations(
    evidence: SeparatorContinuityEvidence,
) -> tuple[SeparatorBandObservation, ...]:
    supported = {
        (record.index, record.method)
        for record in evidence.records
        if record.state == EvidenceState.SUPPORTED
    }
    return tuple(
        observation
        for observation in evidence.observations
        if is_hard_gap_method(observation.method)
        and (observation.index, observation.method) in supported
    )

def separator_cross_axis_continuity_evidence(
    gray_work: np.ndarray,
    outer: Box,
    observations: tuple[SeparatorBandObservation, ...],
    pitch: float,
    parameters: HardGapTrustParameters,
) -> SeparatorContinuityEvidence:
    if pitch <= 0.0:
        return SeparatorContinuityEvidence(
            state=EvidenceState.UNAVAILABLE,
            reason="invalid_pitch",
            records=(),
            observations=observations,
            minimum_coverage_ratio=float(parameters.cross_axis_coverage_min),
            minimum_continuity_ratio=float(parameters.cross_axis_continuity_min),
        )
    records: list[SeparatorContinuityRecord] = []
    enriched: list[SeparatorBandObservation] = []
    for observation in observations:
        if not is_hard_gap_method(observation.method):
            enriched.append(observation)
            continue
        signals = hard_gap_pixel_signals(
            gray_work,
            outer,
            observation,
            pitch,
            parameters,
        )
        if signals is None:
            records.append(
                SeparatorContinuityRecord(
                    index=observation.index,
                    method=observation.method,
                    measured=False,
                    state=EvidenceState.UNAVAILABLE,
                    coverage_ratio=None,
                    continuity_ratio=None,
                    break_count=None,
                    straightness=None,
                    reason="missing_separator_edges",
                )
            )
            enriched.append(observation)
            continue
        flags = hard_gap_signal_flags(signals, parameters)
        weak = bool(flags and flags.cross_axis_continuity_weak)
        state = EvidenceState.CONTRADICTED if weak else EvidenceState.SUPPORTED
        records.append(
            SeparatorContinuityRecord(
                index=observation.index,
                method=observation.method,
                measured=True,
                state=state,
                coverage_ratio=float(signals.cross_axis_coverage_ratio),
                continuity_ratio=float(signals.cross_axis_continuity_ratio),
                break_count=int(signals.cross_axis_break_count),
                straightness=float(signals.separator_band_straightness),
                reason=(
                    "separator_cross_axis_continuity_weak" if weak else "supported"
                ),
            )
        )
        enriched.append(
            replace(
                observation,
                continuity=float(signals.cross_axis_continuity_ratio),
            )
        )
    supported_count = sum(
        record.state == EvidenceState.SUPPORTED for record in records
    )
    contradicted_count = sum(
        record.state == EvidenceState.CONTRADICTED for record in records
    )
    if records and supported_count == len(records):
        state = EvidenceState.SUPPORTED
        reason = "supported"
    elif records and contradicted_count == len(records):
        state = EvidenceState.CONTRADICTED
        reason = "separator_cross_axis_continuity_weak"
    elif supported_count:
        state = EvidenceState.UNAVAILABLE
        reason = "separator_cross_axis_continuity_mixed"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "hard_separator_continuity_unavailable"
    return SeparatorContinuityEvidence(
        state=state,
        reason=reason,
        records=tuple(records),
        observations=tuple(enriched),
        minimum_coverage_ratio=float(parameters.cross_axis_coverage_min),
        minimum_continuity_ratio=float(parameters.cross_axis_continuity_min),
    )
