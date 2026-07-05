from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Box, Gap
from ..cache import AnalysisCache
from ..utils import clamp_float, clamp_int
from .detection_parameters import EdgePairParameters, EdgeRefineProfileParameters
from .separator_cache import cached_edge_refine_profiles
from .separator_profile import edge_refine_profiles, interval_mean, local_edge_peaks


def edge_pair_parameters_from_config(config: Any) -> EdgePairParameters:
    if isinstance(config, EdgePairParameters):
        return config
    return EdgePairParameters(
        window_ratio=float(getattr(config, "window_ratio")),
        min_gutter_ratio=float(getattr(config, "min_gutter_ratio")),
        max_gutter_ratio=float(getattr(config, "max_gutter_ratio")),
        min_strength=float(getattr(config, "min_strength")),
        min_background=float(getattr(config, "min_background")),
        min_quality_for_model_gap=float(getattr(config, "min_quality_for_model_gap")),
        min_quality_for_hard_gap=float(getattr(config, "min_quality_for_hard_gap")),
        hard_gap_quality_ratio=float(getattr(config, "hard_gap_quality_ratio")),
        max_hard_shift_ratio=float(getattr(config, "max_hard_shift_ratio")),
    )


def edge_pair_can_replace_hard_gap(gap: Gap, edge_gap: Gap, pitch: float, params: EdgePairParameters) -> bool:
    delta = abs(edge_gap.center - gap.center)
    if params.max_hard_shift_ratio <= 0.0:
        return delta <= max(clamp_float(pitch * 0.001, 4.0, 20.0), edge_gap.width)
    shift_limit = max(edge_gap.width * 2.0, clamp_float(pitch * params.max_hard_shift_ratio, 15.0, 220.0))
    if delta > shift_limit:
        return False
    min_quality = max(params.min_quality_for_hard_gap, gap.score * params.hard_gap_quality_ratio)
    if edge_gap.score >= min_quality:
        return True
    return delta <= max(4.0, edge_gap.width * 1.5)


def edge_pair_search_limits(pitch: float, params: EdgePairParameters) -> tuple[int, int, int]:
    window = clamp_int(pitch * params.window_ratio, 8, 520)
    min_gutter = clamp_int(pitch * params.min_gutter_ratio, 2, 40)
    max_gutter = max(min_gutter + 1, clamp_int(pitch * params.max_gutter_ratio, 8, 420))
    return window, min_gutter, max_gutter


def edge_pair_candidates_for_gap(
    edge: np.ndarray,
    background: np.ndarray,
    gap: Gap,
    pitch: float,
    params: EdgePairParameters,
    window: int,
    min_gutter: int,
    max_gutter: int,
) -> list[tuple[float, float, float, int, int]]:
    width = len(edge)
    x0 = int(round(gap.center))
    lo = max(1, x0 - window)
    hi = min(width - 1, x0 + window)
    peaks = local_edge_peaks(edge, lo, hi, params.min_strength)
    candidates: list[tuple[float, float, float, int, int]] = []
    for i, a in enumerate(peaks):
        for b in peaks[i + 1:]:
            gutter_w = b - a
            if gutter_w < min_gutter or gutter_w > max_gutter:
                continue
            center = (a + b) / 2.0
            if abs(center - x0) > window:
                continue
            bg_between = interval_mean(background, a, b + 1)
            if bg_between < params.min_background:
                continue
            strength = (float(edge[a]) + float(edge[b])) / 2.0
            quality = strength + 0.6 * bg_between
            distance = abs(center - x0) / max(1.0, pitch)
            candidates.append((distance, -quality, -bg_between, int(a), int(b)))
    return candidates


def best_edge_pair_gap(
    gap: Gap,
    candidates: list[tuple[float, float, float, int, int]],
) -> Gap | None:
    if not candidates:
        return None
    _distance, neg_quality, _neg_bg, a, b = sorted(candidates)[0]
    center = (a + b) / 2.0
    return Gap(gap.index, float(center), float(-neg_quality), "edge-pair", float(a), float(b + 1))


def edge_pair_can_replace_gap(gap: Gap, edge_gap: Gap, pitch: float, params: EdgePairParameters) -> bool:
    if gap.method not in HARD_GAP_METHODS:
        return edge_gap.score >= params.min_quality_for_model_gap
    if gap.method in {"detected", "enhanced-detected"}:
        return edge_pair_can_replace_hard_gap(gap, edge_gap, pitch, params)
    return True


def refine_gaps_by_edge_pairs(
    crop: np.ndarray,
    gaps: list[Gap],
    count: int,
    format_name: str,
    cache: Optional[AnalysisCache] = None,
    outer: Optional[Box] = None,
    edge_pair_config: Optional[Any] = None,
    edge_refine_config: EdgeRefineProfileParameters | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    h, w = crop.shape
    if count <= 1 or w <= 1 or not gaps:
        return gaps, {"used": False, "reason": "empty"}
    edge, background, _activity = (
        cached_edge_refine_profiles(cache, crop, outer, format_name, edge_refine_config)
        if outer is not None
        else edge_refine_profiles(crop, edge_refine_config)
    )
    pitch = w / float(max(1, count))
    if edge_pair_config is None:
        raise ValueError("edge_pair config is required")
    params = edge_pair_parameters_from_config(edge_pair_config)
    window, min_gutter, max_gutter = edge_pair_search_limits(pitch, params)
    refined: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for gap in gaps:
        edge_gap = best_edge_pair_gap(
            gap,
            edge_pair_candidates_for_gap(
                edge,
                background,
                gap,
                pitch,
                params,
                window,
                min_gutter,
                max_gutter,
            ),
        )
        if edge_gap is None:
            refined.append(gap)
            rejected += 1
            continue
        if not edge_pair_can_replace_gap(gap, edge_gap, pitch, params):
            refined.append(gap)
            rejected += 1
            continue
        refined.append(edge_gap)
        accepted.append(
            {
                "index": int(gap.index),
                "center": float(edge_gap.center),
                "width": float(edge_gap.width),
                "score": float(edge_gap.score),
                "replaced_method": gap.method,
            }
        )
    return refined, {
        "used": True,
        "format": format_name,
        "params": asdict(params),
        "accepted": accepted,
        "accepted_count": len(accepted),
        "rejected_count": rejected,
    }
