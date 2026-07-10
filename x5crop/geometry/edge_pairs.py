from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from ..constants import GAP_EDGE_PAIR
from ..domain import Gap
from ..gap_methods import is_detected_gap_method, is_hard_gap_method
from ..utils import clamp_float, clamp_int
from .detection_parameters import EdgePairParameters
from .edge_refine_profile import local_edge_peaks
from .gap_refinement_detail import gap_refinement_batch_detail
from .separator_profile import interval_mean


@dataclass(frozen=True)
class EdgePairCandidate:
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

    def detail(self) -> dict[str, Any]:
        center = (int(self.left) + int(self.right)) / 2.0
        return {
            "left": int(self.left),
            "right": int(self.right),
            "center": float(center),
            "width": int(self.right - self.left + 1),
            "distance": float(self.distance),
            "quality": float(self.quality),
            "background_score": float(self.background_score),
            "rank_key": [
                float(self.distance),
                float(-self.quality),
                float(-self.background_score),
                int(self.left),
                int(self.right),
            ],
        }


@dataclass(frozen=True)
class EdgePairSearchLimits:
    window: int
    min_gutter: int
    max_gutter: int


@dataclass(frozen=True)
class EdgePairSearchResult:
    gap: Gap
    candidates: list[EdgePairCandidate]
    selected_candidate: EdgePairCandidate | None
    selected_gap: Gap | None

    def detail(self, *, candidate_limit: int = 5) -> dict[str, Any]:
        return {
            "index": int(self.gap.index),
            "input_method": self.gap.method,
            "input_center": float(self.gap.center),
            "candidate_count": len(self.candidates),
            "selected": (
                None
                if self.selected_candidate is None
                else self.selected_candidate.detail()
            ),
            "candidates": [
                candidate.detail()
                for candidate in sorted(self.candidates, key=lambda item: item.rank_key())[:candidate_limit]
            ],
        }


@dataclass(frozen=True)
class EdgePairReplacementAssessment:
    ok: bool
    reason: str
    delta_px: float
    shift_limit: float | None = None
    min_quality: float | None = None
    close_shift_limit: float | None = None

    def detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": bool(self.ok),
            "reason": self.reason,
            "delta_px": float(self.delta_px),
        }
        if self.shift_limit is not None:
            out["shift_limit"] = float(self.shift_limit)
        if self.min_quality is not None:
            out["min_quality"] = float(self.min_quality)
        if self.close_shift_limit is not None:
            out["close_shift_limit"] = float(self.close_shift_limit)
        return out


@dataclass(frozen=True)
class EdgePairRefinementResult:
    gaps: list[Gap]
    detail: dict[str, Any]


def assess_edge_pair_hard_gap_replacement(
    gap: Gap,
    edge_gap: Gap,
    pitch: float,
    params: EdgePairParameters,
) -> EdgePairReplacementAssessment:
    delta = abs(edge_gap.center - gap.center)
    if params.max_hard_shift_ratio <= 0.0:
        shift_limit = max(
            clamp_float(
                pitch * params.zero_hard_shift_ratio,
                params.zero_hard_shift_limit_min,
                params.zero_hard_shift_limit_max,
            ),
            edge_gap.width,
        )
        return EdgePairReplacementAssessment(
            ok=delta <= shift_limit,
            reason="hard_shift_ok" if delta <= shift_limit else "hard_shift_too_large",
            delta_px=float(delta),
            shift_limit=float(shift_limit),
        )
    shift_limit = max(
        edge_gap.width * params.hard_shift_edge_width_multiplier,
        clamp_float(
            pitch * params.max_hard_shift_ratio,
            params.hard_shift_limit_min,
            params.hard_shift_limit_max,
        ),
    )
    if delta > shift_limit:
        return EdgePairReplacementAssessment(
            ok=False,
            reason="hard_shift_too_large",
            delta_px=float(delta),
            shift_limit=float(shift_limit),
        )
    min_quality = max(params.min_quality_for_hard_gap, gap.score * params.hard_gap_quality_ratio)
    if edge_gap.score >= min_quality:
        return EdgePairReplacementAssessment(
            ok=True,
            reason="hard_quality_ok",
            delta_px=float(delta),
            shift_limit=float(shift_limit),
            min_quality=float(min_quality),
        )
    close_shift_limit = max(
        params.close_shift_limit_min,
        edge_gap.width * params.close_shift_edge_width_multiplier,
    )
    close_shift_ok = delta <= close_shift_limit
    return EdgePairReplacementAssessment(
        ok=close_shift_ok,
        reason="hard_close_shift_ok" if close_shift_ok else "hard_quality_weak",
        delta_px=float(delta),
        shift_limit=float(shift_limit),
        min_quality=float(min_quality),
        close_shift_limit=float(close_shift_limit),
    )


def assess_edge_pair_replacement(
    gap: Gap,
    edge_gap: Gap,
    pitch: float,
    params: EdgePairParameters,
) -> EdgePairReplacementAssessment:
    delta = abs(edge_gap.center - gap.center)
    if not is_hard_gap_method(gap.method):
        ok = edge_gap.score >= params.min_quality_for_model_gap
        return EdgePairReplacementAssessment(
            ok=ok,
            reason="model_quality_ok" if ok else "model_quality_weak",
            delta_px=float(delta),
            min_quality=float(params.min_quality_for_model_gap),
        )
    if is_detected_gap_method(gap.method):
        return assess_edge_pair_hard_gap_replacement(gap, edge_gap, pitch, params)
    return EdgePairReplacementAssessment(
        ok=True,
        reason="edge_pair_refresh",
        delta_px=float(delta),
    )


def edge_pair_replacement_role(gap: Gap) -> str:
    if not is_hard_gap_method(gap.method):
        return "model_gap_promotion"
    if is_detected_gap_method(gap.method):
        return "hard_gap_refresh"
    return "edge_pair_refresh"


def edge_pair_replacement_evidence_role_detail(gap: Gap, edge_gap: Gap) -> dict[str, Any]:
    role = edge_pair_replacement_role(gap)
    return {
        "replacement_role": role,
        "source_method": gap.method,
        "result_method": edge_gap.method,
        "promoted_from_model_gap": bool(role == "model_gap_promotion"),
        "refreshed_hard_gap": bool(role in {"hard_gap_refresh", "edge_pair_refresh"}),
    }


def edge_pair_search_limits(pitch: float, params: EdgePairParameters) -> EdgePairSearchLimits:
    window = clamp_int(pitch * params.window_ratio, params.search_window_min, params.search_window_max)
    min_gutter = clamp_int(pitch * params.min_gutter_ratio, params.min_gutter_min, params.min_gutter_max)
    max_gutter = max(
        min_gutter + 1,
        clamp_int(pitch * params.max_gutter_ratio, params.max_gutter_min, params.max_gutter_max),
    )
    return EdgePairSearchLimits(int(window), int(min_gutter), int(max_gutter))


def edge_pair_candidates_for_gap(
    edge: np.ndarray,
    background: np.ndarray,
    gap: Gap,
    pitch: float,
    params: EdgePairParameters,
    limits: EdgePairSearchLimits,
) -> list[EdgePairCandidate]:
    width = len(edge)
    x0 = int(round(gap.center))
    lo = max(1, x0 - limits.window)
    hi = min(width - 1, x0 + limits.window)
    peaks = local_edge_peaks(edge, lo, hi, params.min_strength)
    candidates: list[EdgePairCandidate] = []
    for i, a in enumerate(peaks):
        for b in peaks[i + 1:]:
            gutter_w = b - a
            if gutter_w < limits.min_gutter or gutter_w > limits.max_gutter:
                continue
            center = (a + b) / 2.0
            if abs(center - x0) > limits.window:
                continue
            bg_between = interval_mean(background, a, b + 1)
            if bg_between < params.min_background:
                continue
            strength = (float(edge[a]) + float(edge[b])) / 2.0
            quality = strength + params.background_quality_weight * bg_between
            distance = abs(center - x0) / max(1.0, pitch)
            candidates.append(
                EdgePairCandidate(
                    distance=float(distance),
                    quality=float(quality),
                    background_score=float(bg_between),
                    left=int(a),
                    right=int(b),
                )
            )
    return candidates


def edge_pair_gap_from_candidate(
    gap: Gap,
    candidate: EdgePairCandidate,
) -> Gap:
    center = (candidate.left + candidate.right) / 2.0
    return Gap(
        gap.index,
        float(center),
        float(candidate.quality),
        GAP_EDGE_PAIR,
        float(candidate.left),
        float(candidate.right + 1),
    )


def best_edge_pair_candidate(candidates: list[EdgePairCandidate]) -> EdgePairCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=lambda item: item.rank_key())


def edge_pair_search_result_for_gap(
    edge: np.ndarray,
    background: np.ndarray,
    gap: Gap,
    pitch: float,
    params: EdgePairParameters,
    limits: EdgePairSearchLimits,
) -> EdgePairSearchResult:
    candidates = edge_pair_candidates_for_gap(
        edge,
        background,
        gap,
        pitch,
        params,
        limits,
    )
    selected_candidate = best_edge_pair_candidate(candidates)
    selected_gap = (
        None
        if selected_candidate is None
        else edge_pair_gap_from_candidate(gap, selected_candidate)
    )
    return EdgePairSearchResult(
        gap=gap,
        candidates=candidates,
        selected_candidate=selected_candidate,
        selected_gap=selected_gap,
    )


def refine_gaps_with_edge_profiles(
    edge: np.ndarray,
    background: np.ndarray,
    gaps: list[Gap],
    count: int,
    edge_pair_parameters: EdgePairParameters,
) -> EdgePairRefinementResult:
    width = len(edge)
    if count <= 1 or width <= 1 or background.size <= 0 or not gaps:
        return EdgePairRefinementResult(gaps, {"used": False, "reason": "empty"})
    pitch = width / float(max(1, count))
    params = edge_pair_parameters
    search_limits = edge_pair_search_limits(pitch, params)
    refined: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for gap in gaps:
        search = edge_pair_search_result_for_gap(
            edge,
            background,
            gap,
            pitch,
            params,
            search_limits,
        )
        edge_gap = search.selected_gap
        if edge_gap is None:
            refined.append(gap)
            rejected.append(
                {
                    "index": int(gap.index),
                    "reason": "no_edge_pair_candidate",
                    "kept_method": gap.method,
                    "search": search.detail(),
                }
            )
            continue
        assessment = assess_edge_pair_replacement(gap, edge_gap, pitch, params)
        if not assessment.ok:
            refined.append(gap)
            rejected_detail = {
                "index": int(gap.index),
                "center": float(edge_gap.center),
                "width": float(edge_gap.width),
                "score": float(edge_gap.score),
                "kept_method": gap.method,
                "search": search.detail(),
            }
            rejected_detail.update(edge_pair_replacement_evidence_role_detail(gap, edge_gap))
            rejected_detail.update(assessment.detail())
            rejected.append(rejected_detail)
            continue
        refined.append(edge_gap)
        accepted_detail = {
            "index": int(gap.index),
            "center": float(edge_gap.center),
            "width": float(edge_gap.width),
            "score": float(edge_gap.score),
            "replaced_method": gap.method,
            "search": search.detail(),
            "replacement": assessment.detail(),
        }
        accepted_detail.update(edge_pair_replacement_evidence_role_detail(gap, edge_gap))
        accepted.append(accepted_detail)
    model_promotion_count = sum(1 for item in accepted if item.get("promoted_from_model_gap"))
    hard_refresh_count = sum(1 for item in accepted if item.get("refreshed_hard_gap"))
    return EdgePairRefinementResult(
        refined,
        {
            "used": True,
            "params": asdict(params),
            "model_gap_promotion_count": int(model_promotion_count),
            "hard_gap_refresh_count": int(hard_refresh_count),
            "search_limits": {
                "pitch": float(pitch),
                "window_px": int(search_limits.window),
                "min_gutter_px": int(search_limits.min_gutter),
                "max_gutter_px": int(search_limits.max_gutter),
            },
            **gap_refinement_batch_detail(accepted=accepted, rejected=rejected),
        },
    )


__all__ = [
    "EdgePairCandidate",
    "EdgePairRefinementResult",
    "EdgePairReplacementAssessment",
    "EdgePairSearchLimits",
    "EdgePairSearchResult",
    "assess_edge_pair_hard_gap_replacement",
    "assess_edge_pair_replacement",
    "best_edge_pair_candidate",
    "edge_pair_gap_from_candidate",
    "edge_pair_candidates_for_gap",
    "edge_pair_replacement_evidence_role_detail",
    "edge_pair_replacement_role",
    "edge_pair_search_result_for_gap",
    "edge_pair_search_limits",
    "refine_gaps_with_edge_profiles",
]
