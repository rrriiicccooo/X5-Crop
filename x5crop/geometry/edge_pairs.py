from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..constants import GAP_EDGE_PAIR
from ..domain import MeasurementProvenance, SeparatorBandObservation
from ..gap_methods import is_detected_gap_method, is_hard_gap_method
from ..utils import clamp_float, clamp_int
from .detection_parameters import EdgePairParameters
from .edge_refine_profile import local_edge_peaks
from .separator_profile import interval_mean


@dataclass(frozen=True)
class _EdgePairCandidate:
    distance: float
    quality: float
    background_score: float
    left: int
    right: int

    def rank_key(self) -> tuple[float, float, float, int, int]:
        return (
            self.distance,
            -self.quality,
            -self.background_score,
            self.left,
            self.right,
        )


@dataclass(frozen=True)
class _EdgePairSearchLimits:
    window: int
    min_gutter: int
    max_gutter: int


def _hard_gap_replacement_allowed(
    gap: SeparatorBandObservation,
    edge_gap: SeparatorBandObservation,
    pitch: float,
    parameters: EdgePairParameters,
) -> bool:
    if (
        gap.start is not None
        and gap.end is not None
        and (
            edge_gap.start is None
            or edge_gap.end is None
            or float(edge_gap.start) < float(gap.start)
            or float(edge_gap.end) > float(gap.end)
        )
    ):
        return False
    delta = abs(edge_gap.center - gap.center)
    if parameters.max_hard_shift_ratio <= 0.0:
        shift_limit = max(
            clamp_float(
                pitch * parameters.zero_hard_shift_ratio,
                parameters.zero_hard_shift_limit_min,
                parameters.zero_hard_shift_limit_max,
            ),
            edge_gap.width,
        )
        return delta <= shift_limit
    shift_limit = max(
        edge_gap.width * parameters.hard_shift_edge_width_multiplier,
        clamp_float(
            pitch * parameters.max_hard_shift_ratio,
            parameters.hard_shift_limit_min,
            parameters.hard_shift_limit_max,
        ),
    )
    if delta > shift_limit:
        return False
    minimum_quality = max(
        parameters.min_quality_for_hard_gap,
        gap.score * parameters.hard_gap_quality_ratio,
    )
    if edge_gap.score >= minimum_quality:
        return True
    close_shift_limit = max(
        parameters.close_shift_limit_min,
        edge_gap.width * parameters.close_shift_edge_width_multiplier,
    )
    return delta <= close_shift_limit


def _replacement_allowed(
    gap: SeparatorBandObservation,
    edge_gap: SeparatorBandObservation,
    pitch: float,
    parameters: EdgePairParameters,
) -> bool:
    if not is_hard_gap_method(gap.method):
        return edge_gap.score >= parameters.min_quality_for_model_gap
    if is_detected_gap_method(gap.method):
        return _hard_gap_replacement_allowed(gap, edge_gap, pitch, parameters)
    return True


def _search_limits(
    pitch: float,
    parameters: EdgePairParameters,
) -> _EdgePairSearchLimits:
    minimum = clamp_int(
        pitch * parameters.min_gutter_ratio,
        parameters.min_gutter_min,
        parameters.min_gutter_max,
    )
    return _EdgePairSearchLimits(
        window=clamp_int(
            pitch * parameters.window_ratio,
            parameters.search_window_min,
            parameters.search_window_max,
        ),
        min_gutter=minimum,
        max_gutter=max(
            minimum + 1,
            clamp_int(
                pitch * parameters.max_gutter_ratio,
                parameters.max_gutter_min,
                parameters.max_gutter_max,
            ),
        ),
    )


def _candidates_for_gap(
    edge: np.ndarray,
    background: np.ndarray,
    gap: SeparatorBandObservation,
    pitch: float,
    parameters: EdgePairParameters,
    limits: _EdgePairSearchLimits,
) -> list[_EdgePairCandidate]:
    width = len(edge)
    expected = int(round(gap.center))
    lower = max(1, expected - limits.window)
    upper = min(width - 1, expected + limits.window)
    peaks = local_edge_peaks(
        edge,
        lower,
        upper,
        parameters.min_strength,
        parameters.candidate_peak_percentile,
        parameters.candidate_peak_min_distance_px,
    )
    candidates: list[_EdgePairCandidate] = []
    for position, left in enumerate(peaks):
        for right in peaks[position + 1 :]:
            width_px = right - left
            if width_px < limits.min_gutter or width_px > limits.max_gutter:
                continue
            center = (left + right) / 2.0
            if abs(center - expected) > limits.window:
                continue
            background_score = interval_mean(background, left, right + 1)
            if background_score < parameters.min_background:
                continue
            strength = (float(edge[left]) + float(edge[right])) / 2.0
            candidates.append(
                _EdgePairCandidate(
                    distance=float(abs(center - expected) / max(1.0, pitch)),
                    quality=float(
                        strength
                        + parameters.background_quality_weight * background_score
                    ),
                    background_score=float(background_score),
                    left=int(left),
                    right=int(right),
                )
            )
    return candidates


def _gap_from_candidate(
    gap: SeparatorBandObservation,
    candidate: _EdgePairCandidate,
) -> SeparatorBandObservation:
    return SeparatorBandObservation(
        index=gap.index,
        center=float((candidate.left + candidate.right) / 2.0),
        score=float(candidate.quality),
        method=GAP_EDGE_PAIR,
        provenance=MeasurementProvenance(
            root_measurement="edge_refine_profiles",
            source="edge_pair",
            dependencies=(gap.provenance.root_measurement,),
        ),
        start=float(candidate.left),
        end=float(candidate.right + 1),
        lane_box=gap.lane_box,
        tonal_evidence=float(candidate.quality),
    )


def refine_gaps_with_edge_profiles(
    edge: np.ndarray,
    background: np.ndarray,
    gaps: list[SeparatorBandObservation],
    count: int,
    parameters: EdgePairParameters,
) -> list[SeparatorBandObservation]:
    if count <= 1 or len(edge) <= 1 or background.size <= 0 or not gaps:
        return list(gaps)
    pitch = len(edge) / float(count)
    limits = _search_limits(pitch, parameters)
    refined: list[SeparatorBandObservation] = []
    for gap in gaps:
        candidates = _candidates_for_gap(
            edge,
            background,
            gap,
            pitch,
            parameters,
            limits,
        )
        if not candidates:
            refined.append(gap)
            continue
        edge_gap = _gap_from_candidate(
            gap,
            min(candidates, key=lambda item: item.rank_key()),
        )
        refined.append(
            edge_gap
            if _replacement_allowed(gap, edge_gap, pitch, parameters)
            else gap
        )
    return refined
