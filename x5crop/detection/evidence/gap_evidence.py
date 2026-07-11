from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ...domain import Box, SeparatorBandObservation
from ...gap_methods import (
    gap_method_role,
    is_hard_gap_method,
    is_model_gap_method,
)
from ...geometry.gap_trust import (
    HardGapPixelSignals,
    diagnostic_hard_gap_trust_assessment,
    hard_gap_pixel_signals,
    hard_gap_tonal_separator_like,
    hard_gap_width_ratio,
)
from ...policies.parameters.exposure_overlap import ExposureOverlapEvidenceParameters
from ...policies.runtime.separator import SeparatorPolicy
from ...utils import clamp_int

if TYPE_CHECKING:
    from ..geometry import CandidateGeometry


@dataclass(frozen=True)
class GapEvidenceRecord:
    index: int
    method: str
    role: str
    center: float
    expected_center: float
    score: float
    width_px: float
    hard_trust: str
    exposure_overlap_class: str
    exposure_overlap_like: bool
    signal_window: tuple[int, int] | None
    pixel_signals: HardGapPixelSignals | None

def _gap_work_outer(
    geometry: CandidateGeometry,
    observation: SeparatorBandObservation,
) -> Box:
    return observation.lane_box or geometry.film_span.box


def gap_evidence_record(
    gray_work: np.ndarray,
    geometry: CandidateGeometry,
    observation: SeparatorBandObservation,
    *,
    separator_policy: SeparatorPolicy,
    exposure_overlap_policy: ExposureOverlapEvidenceParameters,
) -> GapEvidenceRecord:
    work_outer = _gap_work_outer(geometry, observation).clamp(
        gray_work.shape[1],
        gray_work.shape[0],
    )
    pitch = float(geometry.pitch)
    expected = (
        float(geometry.origin) + pitch * float(observation.index)
        if pitch > 0.0
        else float(observation.center)
    )
    unavailable = GapEvidenceRecord(
        index=observation.index,
        method=observation.method,
        role=gap_method_role(observation.method),
        center=float(observation.center),
        expected_center=expected,
        score=float(observation.score),
        width_px=float(observation.width),
        hard_trust="not_measured",
        exposure_overlap_class="none",
        exposure_overlap_like=False,
        signal_window=None,
        pixel_signals=None,
    )
    if not work_outer.valid() or pitch <= 0.0:
        return unavailable
    if observation.start is not None and observation.end is not None:
        start = int(
            round(work_outer.left + min(observation.start, observation.end))
        )
        end = int(
            round(work_outer.left + max(observation.start, observation.end))
        )
    else:
        half = clamp_int(
            pitch * exposure_overlap_policy.model_gap_window_ratio,
            exposure_overlap_policy.model_gap_window_min_px,
            exposure_overlap_policy.model_gap_window_max_px,
        )
        center = int(round(work_outer.left + observation.center))
        start, end = center - half, center + half + 1
    start = max(work_outer.left, min(work_outer.right, start))
    end = max(start + 1, min(work_outer.right, end))
    measured = SeparatorBandObservation(
        index=observation.index,
        center=observation.center,
        score=observation.score,
        method=observation.method,
        provenance=observation.provenance,
        start=float(start - work_outer.left),
        end=float(end - work_outer.left),
        lane_box=observation.lane_box,
        continuity=observation.continuity,
        tonal_evidence=observation.tonal_evidence,
    )
    signals = hard_gap_pixel_signals(
        gray_work,
        work_outer,
        measured,
        pitch,
        separator_policy.hard_gap_trust,
    )
    if signals is None:
        return unavailable
    hard_trust = "not_hard_separator"
    overlap_class = "none"
    if is_hard_gap_method(observation.method):
        trust = diagnostic_hard_gap_trust_assessment(
            observation,
            pitch,
            separator_policy.hard_gap_trust,
            width_ratio=hard_gap_width_ratio(observation, pitch),
            model_delta_ratio=abs(observation.center - expected) / max(1.0, pitch),
            nearby_separator_conflict=False,
            signals=signals,
        )
        hard_trust = trust.trust
    elif is_model_gap_method(observation.method) and not hard_gap_tonal_separator_like(
        signals,
        separator_policy.hard_gap_trust,
    ):
        if (
            signals.continuity >= exposure_overlap_policy.strong_continuity
            and signals.core_activity >= exposure_overlap_policy.strong_activity
            and signals.core_mean >= exposure_overlap_policy.mean_min
        ):
            overlap_class = "strong"
        elif (
            signals.continuity >= exposure_overlap_policy.medium_continuity
            and signals.core_activity >= exposure_overlap_policy.medium_activity
            and signals.core_mean >= exposure_overlap_policy.mean_min
        ):
            overlap_class = "medium"
        elif (
            signals.continuity >= exposure_overlap_policy.weak_continuity
            and signals.core_activity >= exposure_overlap_policy.weak_activity
            and signals.core_mean >= exposure_overlap_policy.mean_min
        ):
            overlap_class = "weak"
    return GapEvidenceRecord(
        index=observation.index,
        method=observation.method,
        role=gap_method_role(observation.method),
        center=float(observation.center),
        expected_center=expected,
        score=float(observation.score),
        width_px=float(observation.width),
        hard_trust=hard_trust,
        exposure_overlap_class=overlap_class,
        exposure_overlap_like=overlap_class in {"medium", "strong"},
        signal_window=(int(signals.start), int(signals.end)),
        pixel_signals=signals,
    )
