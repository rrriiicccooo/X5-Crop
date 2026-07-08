from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from ..domain import Gap
from ..gap_methods import is_hard_gap_method
from ..utils import clamp_float, clamp_int, runs_from_mask
from .gap_geometry import gap_width_cv, local_gap_geometry_error
from .gap_refinement_detail import gap_refinement_batch_detail
from .detection_parameters import NearbySeparatorRefinementParameters
from .separator_profile import interval_mean


@dataclass(frozen=True)
class NearbySeparatorSearchContext:
    current_start: int
    current_end: int
    window: int
    exclude: int
    lo: int
    hi: int
    current_score: float
    threshold: float


@dataclass(frozen=True)
class NearbySeparatorCandidate:
    center: float
    start: int
    end: int
    width_px: int
    score: float
    distance_px: float

    def rank_key(self) -> tuple[float, float]:
        return (float(self.score), -abs(float(self.distance_px)))

    def detail(self, *, absolute_center_offset: float | None = None) -> dict[str, Any]:
        detail = {
            "center": float(self.center),
            "start": int(self.start),
            "end": int(self.end),
            "width_px": int(self.width_px),
            "score": float(self.score),
            "distance_px": float(self.distance_px),
        }
        if absolute_center_offset is not None:
            detail["absolute_center"] = float(absolute_center_offset + float(self.center))
        return detail


@dataclass(frozen=True)
class NearbySeparatorSearchResult:
    context: NearbySeparatorSearchContext
    candidates: list[NearbySeparatorCandidate]
    best_candidate: NearbySeparatorCandidate | None
    stronger_found: bool
    absolute_center_offset: float | None = None

    def detail(self) -> dict[str, Any]:
        return {
            "searched": True,
            "window_px": int(self.context.window),
            "current_profile_score": float(self.context.current_score),
            "candidate_count": len(self.candidates),
            "stronger_found": bool(self.stronger_found),
            "best": (
                None
                if self.best_candidate is None
                else self.best_candidate.detail(absolute_center_offset=self.absolute_center_offset)
            ),
        }


@dataclass(frozen=True)
class NearbySeparatorReplacementAssessment:
    accepted: bool
    reason: str
    replacement: dict[str, Any] | None
    search_detail: dict[str, Any]

    def detail(self, gap: Gap) -> dict[str, Any]:
        return {
            "index": int(gap.index),
            "reason": self.reason,
            "accepted": bool(self.accepted),
            "searched": bool(self.search_detail.get("searched", False)),
            "stronger_found": bool(self.search_detail.get("stronger_found", False)),
            "candidate_count": int(self.search_detail.get("candidate_count", 0) or 0),
            "best": self.search_detail.get("best"),
            "search": self.search_detail,
        }


@dataclass(frozen=True)
class NearbySeparatorRefinementResult:
    gaps: list[Gap]
    detail: dict[str, Any]


class NearbySeparatorSearchConfig(Protocol):
    window_ratio: float
    window_min: int
    window_max: int
    exclude_ratio: float
    exclude_min: int
    exclude_max: int
    max_width_ratio: float
    max_width_min: int
    max_width_max: int


def nearby_separator_search_context(
    profile: np.ndarray,
    gap: Gap,
    pitch: float,
    config: NearbySeparatorSearchConfig,
) -> NearbySeparatorSearchContext | None:
    center = int(round(gap.center))
    current_start = max(0, min(len(profile), int(round(min(gap.start, gap.end)))))
    current_end = max(current_start + 1, min(len(profile), int(round(max(gap.start, gap.end)))))
    window = clamp_int(pitch * config.window_ratio, config.window_min, config.window_max)
    exclude = max(
        config.exclude_min,
        clamp_int(
            max(float(current_end - current_start), pitch * config.exclude_ratio),
            config.exclude_min,
            config.exclude_max,
        ),
    )
    lo = max(0, center - window)
    hi = min(len(profile), center + window + 1)
    if hi <= lo:
        return None
    return NearbySeparatorSearchContext(
        current_start=int(current_start),
        current_end=int(current_end),
        window=int(window),
        exclude=int(exclude),
        lo=int(lo),
        hi=int(hi),
        current_score=float(interval_mean(profile, current_start, current_end)),
        threshold=max(0.22, float(np.percentile(profile[lo:hi], 82))),
    )


def nearby_separator_candidates(
    profile: np.ndarray,
    gap: Gap,
    pitch: float,
    config: NearbySeparatorSearchConfig,
    context: NearbySeparatorSearchContext,
) -> list[NearbySeparatorCandidate]:
    candidates: list[NearbySeparatorCandidate] = []
    for run_start, run_end in runs_from_mask(profile[context.lo:context.hi] >= context.threshold):
        abs_start = context.lo + run_start
        abs_end = context.lo + run_end
        if abs_end <= abs_start:
            continue
        if abs_start < context.current_end + context.exclude and abs_end > context.current_start - context.exclude:
            continue
        width = abs_end - abs_start
        if width > clamp_int(pitch * config.max_width_ratio, config.max_width_min, config.max_width_max):
            continue
        score = interval_mean(profile, abs_start, abs_end)
        candidate_center = (abs_start + abs_end - 1) / 2.0
        distance = candidate_center - gap.center
        distance_ratio = getattr(config, "distance_ratio", None)
        if distance_ratio is not None:
            if abs(distance) > clamp_float(
                pitch * float(distance_ratio),
                float(config.window_min),
                float(config.window_max),
            ):
                continue
        candidates.append(
            NearbySeparatorCandidate(
                center=float(candidate_center),
                start=int(abs_start),
                end=int(abs_end),
                width_px=int(width),
                score=float(score),
                distance_px=float(distance),
            )
        )
    candidates.sort(key=lambda item: item.rank_key(), reverse=True)
    return candidates


def nearby_separator_best_candidate(candidates: list[NearbySeparatorCandidate]) -> NearbySeparatorCandidate | None:
    return candidates[0] if candidates else None


def nearby_separator_candidate_is_stronger(
    candidate: NearbySeparatorCandidate | None,
    current_score: float,
    score_add: float,
    score_multiplier: float,
) -> bool:
    return bool(
        candidate
        and float(candidate.score) >= max(
            current_score + score_add,
            current_score * score_multiplier,
        )
    )


def nearby_separator_search_result(
    profile: np.ndarray,
    gap: Gap,
    pitch: float,
    config: NearbySeparatorSearchConfig,
    *,
    score_add: float,
    score_multiplier: float,
    absolute_center_offset: float | None = None,
) -> NearbySeparatorSearchResult | None:
    context = nearby_separator_search_context(profile, gap, pitch, config)
    if context is None:
        return None
    candidates = nearby_separator_candidates(profile, gap, pitch, config, context)
    best = nearby_separator_best_candidate(candidates)
    stronger = nearby_separator_candidate_is_stronger(
        best,
        context.current_score,
        score_add,
        score_multiplier,
    )
    return NearbySeparatorSearchResult(
        context=context,
        candidates=candidates,
        best_candidate=best,
        stronger_found=bool(stronger),
        absolute_center_offset=absolute_center_offset,
    )


def nearby_separator_search_detail(
    profile: np.ndarray,
    gap: Gap,
    pitch: float,
    config: NearbySeparatorSearchConfig,
    *,
    score_add: float,
    score_multiplier: float,
    absolute_center_offset: float | None = None,
) -> dict[str, Any] | None:
    result = nearby_separator_search_result(
        profile,
        gap,
        pitch,
        config,
        score_add=score_add,
        score_multiplier=score_multiplier,
        absolute_center_offset=absolute_center_offset,
    )
    return None if result is None else result.detail()


def nearby_separator_replacement_assessment(
    profile: np.ndarray,
    gap: Gap,
    pitch: float,
    refinement_config: NearbySeparatorRefinementParameters,
) -> NearbySeparatorReplacementAssessment:
    if not is_hard_gap_method(gap.method):
        return NearbySeparatorReplacementAssessment(
            False,
            "not_hard_gap",
            None,
            {"searched": False, "reason": "not_hard_gap"},
        )
    if pitch <= 0:
        return NearbySeparatorReplacementAssessment(
            False,
            "invalid_pitch",
            None,
            {"searched": False, "reason": "invalid_pitch"},
        )
    if gap.start is None or gap.end is None:
        return NearbySeparatorReplacementAssessment(
            False,
            "missing_gap_span",
            None,
            {"searched": False, "reason": "missing_gap_span"},
        )
    result = nearby_separator_search_result(
        profile,
        gap,
        pitch,
        refinement_config,
        score_add=refinement_config.score_add,
        score_multiplier=refinement_config.score_multiplier,
    )
    if result is None:
        return NearbySeparatorReplacementAssessment(
            False,
            "empty_search_window",
            None,
            {"searched": False, "reason": "empty_search_window"},
        )
    detail = result.detail()
    if detail.get("best") is None:
        return NearbySeparatorReplacementAssessment(False, "no_candidate", None, detail)
    if not detail.get("stronger_found"):
        return NearbySeparatorReplacementAssessment(False, "candidate_not_stronger", None, detail)
    return NearbySeparatorReplacementAssessment(True, "stronger_candidate", detail, detail)


def nearby_separator_gap_from_candidate(gap: Gap, candidate: dict[str, Any]) -> Gap:
    return Gap(
        gap.index,
        float(candidate["center"]),
        float(candidate["score"]),
        gap.method,
        float(candidate["start"]),
        float(candidate["end"]),
        gap.lane_box,
    )


def nearby_separator_reject_detail(
    gap: Gap,
    reason: str,
    candidate: dict[str, Any],
    before_local: float | None = None,
    after_local: float | None = None,
    before_cv: float | None = None,
    after_cv: float | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {"index": int(gap.index), "reason": reason, "candidate": candidate}
    if before_local is not None:
        detail["before_local_error"] = float(before_local)
    if after_local is not None:
        detail["after_local_error"] = float(after_local)
    if before_cv is not None:
        detail["before_width_cv"] = float(before_cv)
    if after_cv is not None:
        detail["after_width_cv"] = float(after_cv)
    return detail


def nearby_separator_accept_detail(
    gap: Gap,
    proposed_gap: Gap,
    replacement: dict[str, Any],
    before_local: float,
    after_local: float,
    before_cv: float,
    after_cv: float,
) -> dict[str, Any]:
    return {
        "index": int(gap.index),
        "from_center": float(gap.center),
        "to_center": float(proposed_gap.center),
        "delta_px": float(proposed_gap.center - gap.center),
        "from_score": float(gap.score),
        "to_score": float(proposed_gap.score),
        "from_method": gap.method,
        "to_method": proposed_gap.method,
        "before_local_error": float(before_local),
        "after_local_error": float(after_local),
        "before_width_cv": float(before_cv),
        "after_width_cv": float(after_cv),
        "nearby_separator_candidate": replacement,
    }


def nearby_separator_geometry_is_better(
    before_local: float,
    after_local: float,
    before_cv: float,
    after_cv: float,
    original_cv: float,
    pitch: float,
    config: NearbySeparatorRefinementParameters,
) -> bool:
    local_gain = before_local - after_local
    local_ok = local_gain >= clamp_float(
        pitch * config.local_gain_ratio,
        config.local_gain_min,
        config.local_gain_max,
    )
    cv_ok = after_cv <= before_cv + config.width_cv_slack and after_cv <= original_cv + config.width_cv_slack
    return local_ok and cv_ok


def apply_nearby_separator_refinement(
    profile: np.ndarray,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    count: int,
    refinement_config: NearbySeparatorRefinementParameters,
) -> NearbySeparatorRefinementResult:
    if not refinement_config.enabled or count <= 1 or len(gaps) != count - 1:
        return NearbySeparatorRefinementResult(gaps, {"used": False, "reason": "not_applicable"})
    if profile.size == 0:
        return NearbySeparatorRefinementResult(gaps, {"used": False, "reason": "empty_profile"})
    original_cv = gap_width_cv(gaps, origin, pitch, count)
    corrected = list(gaps)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    searched: list[dict[str, Any]] = []
    for pos, gap in enumerate(list(corrected)):
        assessment = nearby_separator_replacement_assessment(profile, gap, pitch, refinement_config)
        searched.append(assessment.detail(gap))
        replacement = assessment.replacement
        if replacement is None:
            continue
        best = replacement["best"]
        proposed_gap = nearby_separator_gap_from_candidate(gap, best)
        proposed = list(corrected)
        proposed[pos] = proposed_gap
        if any(b.center <= a.center for a, b in zip(proposed[:-1], proposed[1:])):
            rejected.append(nearby_separator_reject_detail(gap, "non_monotonic", best))
            continue
        before_local = local_gap_geometry_error(corrected, gap.index, origin, pitch, count)
        after_local = local_gap_geometry_error(proposed, gap.index, origin, pitch, count)
        before_cv = gap_width_cv(corrected, origin, pitch, count)
        after_cv = gap_width_cv(proposed, origin, pitch, count)
        if not nearby_separator_geometry_is_better(
            before_local,
            after_local,
            before_cv,
            after_cv,
            original_cv,
            pitch,
            refinement_config,
        ):
            rejected.append(
                nearby_separator_reject_detail(
                    gap,
                    "geometry_not_better",
                    best,
                    before_local,
                    after_local,
                    before_cv,
                    after_cv,
                )
            )
            continue
        corrected = proposed
        accepted.append(
            nearby_separator_accept_detail(
                gap,
                proposed_gap,
                replacement,
                before_local,
                after_local,
                before_cv,
                after_cv,
            )
        )
    return NearbySeparatorRefinementResult(
        corrected,
        {
            "used": True,
            "reason": "ok",
            **gap_refinement_batch_detail(
                searched=searched,
                accepted=accepted,
                rejected=rejected,
            ),
            "original_width_cv": float(original_cv),
            "final_width_cv": float(gap_width_cv(corrected, origin, pitch, count)),
        },
    )
