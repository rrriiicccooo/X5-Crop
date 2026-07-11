from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..constants import GAP_DETECTED
from ..domain import MeasurementProvenance, SeparatorBandObservation
from ..gap_methods import is_model_gap_method
from ..utils import clamp_float, clamp_int, runs_from_mask
from .detection_parameters import NearbySeparatorRefinementParameters
from .separator_profile import interval_mean


@dataclass(frozen=True)
class _NearbySeparatorCandidate:
    center: float
    start: int
    end: int
    score: float
    distance_px: float

    def rank_key(self) -> tuple[float, float]:
        return (self.score, -abs(self.distance_px))


@dataclass(frozen=True)
class _NearbySeparatorSearchContext:
    current_start: int
    current_end: int
    exclude: int
    lower: int
    upper: int
    current_score: float
    threshold: float


def _search_context(
    profile: np.ndarray,
    gap: SeparatorBandObservation,
    pitch: float,
    parameters: NearbySeparatorRefinementParameters,
) -> _NearbySeparatorSearchContext | None:
    center = int(round(gap.center))
    current_start = max(0, min(len(profile), int(round(min(gap.start, gap.end)))))
    current_end = max(
        current_start + 1,
        min(len(profile), int(round(max(gap.start, gap.end)))),
    )
    window = clamp_int(
        pitch * parameters.window_ratio,
        parameters.window_min,
        parameters.window_max,
    )
    exclude = max(
        parameters.exclude_min,
        clamp_int(
            max(
                float(current_end - current_start),
                pitch * parameters.exclude_ratio,
            ),
            parameters.exclude_min,
            parameters.exclude_max,
        ),
    )
    lower = max(0, center - window)
    upper = min(len(profile), center + window + 1)
    if upper <= lower:
        return None
    return _NearbySeparatorSearchContext(
        current_start=current_start,
        current_end=current_end,
        exclude=exclude,
        lower=lower,
        upper=upper,
        current_score=float(interval_mean(profile, current_start, current_end)),
        threshold=max(
            parameters.candidate_threshold_floor,
            float(
                np.percentile(
                    profile[lower:upper],
                    parameters.candidate_threshold_percentile,
                )
            ),
        ),
    )


def _candidates(
    profile: np.ndarray,
    gap: SeparatorBandObservation,
    pitch: float,
    parameters: NearbySeparatorRefinementParameters,
    context: _NearbySeparatorSearchContext,
) -> list[_NearbySeparatorCandidate]:
    candidates: list[_NearbySeparatorCandidate] = []
    for start, end in runs_from_mask(
        profile[context.lower : context.upper] >= context.threshold
    ):
        absolute_start = context.lower + start
        absolute_end = context.lower + end
        if absolute_end <= absolute_start:
            continue
        if (
            absolute_start < context.current_end + context.exclude
            and absolute_end > context.current_start - context.exclude
        ):
            continue
        width = absolute_end - absolute_start
        if width > clamp_int(
            pitch * parameters.max_width_ratio,
            parameters.max_width_min,
            parameters.max_width_max,
        ):
            continue
        center = (absolute_start + absolute_end - 1) / 2.0
        distance = center - gap.center
        if abs(distance) > clamp_float(
            pitch * parameters.distance_ratio,
            float(parameters.window_min),
            float(parameters.window_max),
        ):
            continue
        candidates.append(
            _NearbySeparatorCandidate(
                center=float(center),
                start=int(absolute_start),
                end=int(absolute_end),
                score=float(interval_mean(profile, absolute_start, absolute_end)),
                distance_px=float(distance),
            )
        )
    return candidates


def _replacement(
    profile: np.ndarray,
    gap: SeparatorBandObservation,
    pitch: float,
    parameters: NearbySeparatorRefinementParameters,
) -> SeparatorBandObservation | None:
    if not is_model_gap_method(gap.method) or pitch <= 0:
        return None
    if gap.start is None or gap.end is None:
        return None
    context = _search_context(profile, gap, pitch, parameters)
    if context is None:
        return None
    candidates = _candidates(profile, gap, pitch, parameters, context)
    if not candidates:
        return None
    best = max(candidates, key=lambda item: item.rank_key())
    if best.score < max(
        context.current_score + parameters.score_add,
        context.current_score * parameters.score_multiplier,
    ):
        return None
    return SeparatorBandObservation(
        index=gap.index,
        center=best.center,
        score=best.score,
        method=GAP_DETECTED,
        provenance=MeasurementProvenance(
            root_measurement="separator_profile",
            source="nearby_observed_band",
            dependencies=(gap.provenance.root_measurement,),
        ),
        start=float(best.start),
        end=float(best.end),
        lane_box=gap.lane_box,
        tonal_evidence=best.score,
    )


def apply_nearby_separator_refinement(
    profile: np.ndarray,
    gaps: list[SeparatorBandObservation],
    pitch: float,
    count: int,
    parameters: NearbySeparatorRefinementParameters,
) -> list[SeparatorBandObservation]:
    if count <= 1 or len(gaps) != count - 1 or profile.size == 0:
        return list(gaps)
    refined = list(gaps)
    for position, gap in enumerate(tuple(refined)):
        replacement = _replacement(profile, gap, pitch, parameters)
        if replacement is None:
            continue
        proposed = list(refined)
        proposed[position] = replacement
        if any(
            right.center <= left.center
            for left, right in zip(proposed[:-1], proposed[1:])
        ):
            continue
        refined = proposed
    return refined
