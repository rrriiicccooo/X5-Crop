from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Iterable, Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Box, Detection, Gap, OuterCandidate
from ..formats import FormatSpec
from ..image.evidence import make_separator_evidence_gray
from ..policies.runtime_policy import (
    EnhancedSeparatorPolicy,
    EdgeRefineProfilePolicy,
    GapSearchPolicy,
    RobustGridPolicy,
    SeparatorProfilePolicy,
)
from ..policies.parameter_types import EdgePairParams
from ..runtime import AnalysisCache
from ..utils import clamp_float, clamp_int

from .boxes import (
    box_cache_key,
    crop_work_outer,
    full_work_box,
    is_full_work_box,
    map_work_box,
    original_box_to_work,
)
from .gaps import (
    apply_nearby_separator_corrections,
    apply_robust_grid,
    constrain_gap_to_geometry,
    find_gap,
    gap_width_cv,
    light_hard_gap_trust,
    local_gap_geometry_error,
    nearby_separator_replacement,
)
from .layout import infer_layout, make_analysis_cache, work_gray
from .outer_boxes import (
    bbox_from_mask,
    detect_outer,
    detect_outer_candidates,
    detect_outer_white_x,
    first_content_index,
    runs_from_mask,
    smooth_1d,
    unique_outer_candidates,
)
from .frame_fit import (
    fit_boxes_by_edge_evidence,
    fit_cuts_by_geometry,
    fit_frame_boxes_from_gaps,
    frame_boxes_from_gaps,
    frame_edge_weight,
    relative_ranges_from_gaps,
    weighted_median,
)
from .separator_profile import (
    edge_refine_profiles,
    interval_mean,
    local_edge_peaks,
    normalize_profile,
    separator_profile,
)
from .output_adjustment import (
    apply_approved_geometry_adjustment,
    apply_edge_bleed_protection,
    apply_output_bleed,
    detection_geometry_config,
    detection_has_overlap_bleed_risk,
    output_bleed_config_for_detection,
    reapply_cached_output_bleed,
)
def cached_full_separator_evidence(cache: Optional[AnalysisCache], gray_work: np.ndarray) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(gray_work)
    if cache.separator_evidence_work_full is None:
        cache.separator_evidence_work_full = make_separator_evidence_gray(cache.gray_work)
        cache.separator_evidence_crops[box_cache_key(full_work_box(cache.gray_work))] = cache.separator_evidence_work_full
    return cache.separator_evidence_work_full


def separator_profile_cache_key(
    format_name: str,
    outer: Box,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> tuple[Any, ...]:
    return (str(format_name), profile_policy or SeparatorProfilePolicy(), *box_cache_key(outer))


def separator_profile_full_cache_key(
    format_name: str,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> tuple[Any, ...]:
    return (str(format_name), profile_policy or SeparatorProfilePolicy())


def edge_refine_profile_cache_key(
    format_name: str,
    outer: Box,
    edge_refine_policy: EdgeRefineProfilePolicy | None = None,
) -> tuple[Any, ...]:
    return (str(format_name), edge_refine_policy or EdgeRefineProfilePolicy(), *box_cache_key(outer))


def cached_separator_profile(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    format_name: str,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> np.ndarray:
    if cache is None:
        return separator_profile(crop_work_outer(gray_work, outer), profile_policy)
    if is_full_work_box(cache.gray_work, outer):
        full_key = separator_profile_full_cache_key(format_name, profile_policy)
        profile = cache.separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(cache.gray_work, profile_policy)
            cache.separator_profiles_full[full_key] = profile
            cache.separator_profiles[separator_profile_cache_key(format_name, full_work_box(cache.gray_work), profile_policy)] = profile
        return profile
    key = separator_profile_cache_key(format_name, outer, profile_policy)
    profile = cache.separator_profiles.get(key)
    if profile is None:
        profile = separator_profile(crop_work_outer(cache.gray_work, outer), profile_policy)
        cache.separator_profiles[key] = profile
    return profile


def cached_enhanced_separator_profile(
    cache: Optional[AnalysisCache],
    gray_work: np.ndarray,
    outer: Box,
    format_name: str,
    profile_policy: SeparatorProfilePolicy | None = None,
) -> np.ndarray:
    if cache is None:
        crop = crop_work_outer(gray_work, outer)
        return separator_profile(make_separator_evidence_gray(crop), profile_policy)
    if is_full_work_box(cache.gray_work, outer):
        full_key = separator_profile_full_cache_key(format_name, profile_policy)
        profile = cache.enhanced_separator_profiles_full.get(full_key)
        if profile is None:
            profile = separator_profile(cached_full_separator_evidence(cache, cache.gray_work), profile_policy)
            cache.enhanced_separator_profiles_full[full_key] = profile
            cache.enhanced_separator_profiles[
                separator_profile_cache_key(format_name, full_work_box(cache.gray_work), profile_policy)
            ] = profile
        return profile
    key = separator_profile_cache_key(format_name, outer, profile_policy)
    profile = cache.enhanced_separator_profiles.get(key)
    if profile is None:
        crop = crop_work_outer(cache.gray_work, outer)
        profile = separator_profile(make_separator_evidence_gray(crop), profile_policy)
        cache.enhanced_separator_profiles[key] = profile
    return profile


def cached_separator_evidence_crop(cache: Optional[AnalysisCache], gray_work: np.ndarray, outer: Box) -> np.ndarray:
    if cache is None:
        return make_separator_evidence_gray(crop_work_outer(gray_work, outer))
    if is_full_work_box(cache.gray_work, outer):
        return cached_full_separator_evidence(cache, cache.gray_work)
    key = box_cache_key(outer)
    evidence = cache.separator_evidence_crops.get(key)
    if evidence is None:
        evidence = make_separator_evidence_gray(crop_work_outer(cache.gray_work, outer))
        cache.separator_evidence_crops[key] = evidence
    return evidence


def cached_edge_refine_profiles(
    cache: Optional[AnalysisCache],
    crop: np.ndarray,
    outer: Box,
    format_name: str,
    edge_refine_policy: EdgeRefineProfilePolicy | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if cache is None:
        return edge_refine_profiles(crop, edge_refine_policy)
    key = edge_refine_profile_cache_key(format_name, outer, edge_refine_policy)
    profiles = cache.edge_refine_profiles.get(key)
    if profiles is None:
        profiles = edge_refine_profiles(crop_work_outer(cache.gray_work, outer), edge_refine_policy)
        cache.edge_refine_profiles[key] = profiles
    return profiles


def edge_pair_params_from_policy(policy: Any) -> EdgePairParams:
    if isinstance(policy, EdgePairParams):
        return policy
    return EdgePairParams(
        window_ratio=float(getattr(policy, "window_ratio")),
        min_gutter_ratio=float(getattr(policy, "min_gutter_ratio")),
        max_gutter_ratio=float(getattr(policy, "max_gutter_ratio")),
        min_strength=float(getattr(policy, "min_strength")),
        min_background=float(getattr(policy, "min_background")),
        min_quality_for_model_gap=float(getattr(policy, "min_quality_for_model_gap")),
        min_quality_for_hard_gap=float(getattr(policy, "min_quality_for_hard_gap")),
        hard_gap_quality_ratio=float(getattr(policy, "hard_gap_quality_ratio")),
        max_hard_shift_ratio=float(getattr(policy, "max_hard_shift_ratio")),
    )


def edge_pair_can_replace_hard_gap(gap: Gap, edge_gap: Gap, pitch: float, params: EdgePairParams) -> bool:
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


def refine_gaps_by_edge_pairs(
    crop: np.ndarray,
    gaps: list[Gap],
    count: int,
    format_name: str,
    cache: Optional[AnalysisCache] = None,
    outer: Optional[Box] = None,
    edge_pair_policy: Optional[Any] = None,
    edge_refine_policy: EdgeRefineProfilePolicy | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    h, w = crop.shape
    if count <= 1 or w <= 1 or not gaps:
        return gaps, {"used": False, "reason": "empty"}
    edge, background, _activity = (
        cached_edge_refine_profiles(cache, crop, outer, format_name, edge_refine_policy)
        if outer is not None
        else edge_refine_profiles(crop, edge_refine_policy)
    )
    pitch = w / float(max(1, count))
    if edge_pair_policy is None:
        raise ValueError("edge_pair_policy is required")
    params = edge_pair_params_from_policy(edge_pair_policy)
    window = clamp_int(pitch * params.window_ratio, 8, 520)
    min_gutter = clamp_int(pitch * params.min_gutter_ratio, 2, 40)
    max_gutter = max(min_gutter + 1, clamp_int(pitch * params.max_gutter_ratio, 8, 420))
    refined: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for gap in gaps:
        x0 = int(round(gap.center))
        lo = max(1, x0 - window)
        hi = min(w - 1, x0 + window)
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
        if not candidates:
            refined.append(gap)
            rejected += 1
            continue
        _distance, neg_quality, _neg_bg, a, b = sorted(candidates)[0]
        center = (a + b) / 2.0
        edge_gap = Gap(gap.index, float(center), float(-neg_quality), "edge-pair", float(a), float(b + 1))
        if gap.method not in HARD_GAP_METHODS and edge_gap.score < params.min_quality_for_model_gap:
            refined.append(gap)
            rejected += 1
            continue
        if gap.method in {"detected", "enhanced-detected", "wide-separator"} and not edge_pair_can_replace_hard_gap(gap, edge_gap, pitch, params):
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


def find_enhanced_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    format_name: str,
    gap_search: GapSearchPolicy | None = None,
    enhanced_policy: EnhancedSeparatorPolicy | None = None,
) -> Gap:
    policy = enhanced_policy or EnhancedSeparatorPolicy()
    gap = find_gap(profile, expected, pitch, index, format_name, gap_search=gap_search)
    if gap.method != "detected":
        return gap
    if gap.score < policy.min_score:
        return Gap(index, float(expected), gap.score, "equal")
    if gap.start is None or gap.end is None:
        return Gap(index, float(expected), gap.score, "equal")
    width = abs(float(gap.end) - float(gap.start))
    if width <= 0 or width > clamp_float(pitch * policy.max_width_ratio, policy.max_width_min, policy.max_width_max):
        return Gap(index, float(expected), gap.score, "equal")
    if abs(gap.center - expected) > clamp_float(pitch * policy.max_shift_ratio, policy.max_shift_min, policy.max_shift_max):
        return Gap(index, float(expected), gap.score, "equal")
    return Gap(index, gap.center, gap.score, "enhanced-detected", gap.start, gap.end)


def enhanced_separator_merge_cache_key(
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    format_name: str,
    policy_key: tuple[Any, ...] = (),
) -> tuple[Any, ...]:
    return (
        str(format_name),
        str(strip_mode),
        policy_key,
        box_cache_key(outer),
        round(float(origin), 4),
        round(float(pitch), 4),
        tuple(
            (
                int(gap.index),
                str(gap.method),
                round(float(gap.center), 4),
                round(float(gap.score), 6),
                None if gap.start is None else round(float(gap.start), 4),
                None if gap.end is None else round(float(gap.end), 4),
            )
            for gap in gaps
        ),
    )


def merge_enhanced_separator_gaps(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    origin: float,
    pitch: float,
    strip_mode: str,
    format_name: str,
    cache: Optional[AnalysisCache] = None,
    robust_grid: RobustGridPolicy | None = None,
    gap_search: GapSearchPolicy | None = None,
    profile_policy: SeparatorProfilePolicy | None = None,
    enhanced_policy: EnhancedSeparatorPolicy | None = None,
) -> tuple[list[Gap], dict[str, Any]]:
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0 or outer.width <= 0 or outer.height <= 0:
        return gaps, {"used": False, "reason": "empty_outer"}
    cache_key: Optional[tuple[Any, ...]] = None
    if cache is not None:
        policy_key = (
            robust_grid or RobustGridPolicy(),
            gap_search or GapSearchPolicy(),
            profile_policy or SeparatorProfilePolicy(),
            enhanced_policy or EnhancedSeparatorPolicy(),
        )
        cache_key = enhanced_separator_merge_cache_key(outer, gaps, origin, pitch, strip_mode, format_name, policy_key)
        cached = cache.enhanced_separator_merges.get(cache_key)
        if cached is not None:
            cached_gaps, cached_detail = cached
            return list(cached_gaps), copy.deepcopy(cached_detail)
    profile = cached_enhanced_separator_profile(cache, gray_work, outer, format_name, profile_policy)
    merged: list[Gap] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for gap in gaps:
        if gap.method in HARD_GAP_METHODS:
            merged.append(gap)
            continue
        expected = origin + pitch * gap.index
        enhanced = find_enhanced_gap(profile, expected, pitch, gap.index, format_name, gap_search, enhanced_policy)
        if enhanced.method == "enhanced-detected":
            merged.append(enhanced)
            accepted.append(
                {
                    "index": int(gap.index),
                    "center": float(enhanced.center),
                    "score": float(enhanced.score),
                    "replaced_method": gap.method,
                }
            )
        else:
            merged.append(gap)
            rejected.append(
                {
                    "index": int(gap.index),
                    "score": float(enhanced.score),
                    "method": enhanced.method,
                    "kept_method": gap.method,
                }
            )
    constrained = [
        constrain_gap_to_geometry(gap, origin + pitch * gap.index, pitch, strip_mode, robust_grid)
        if gap.method == "enhanced-detected" else gap
        for gap in merged
    ]
    detail = {
        "used": True,
        "accepted": accepted,
        "rejected": rejected[:8],
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }
    if cache_key is not None and cache is not None:
        cache.enhanced_separator_merges[cache_key] = (list(constrained), copy.deepcopy(detail))
    return constrained, detail


def should_run_enhanced_separator_analysis(
    analysis: str,
    gaps: list[Gap],
    count: int,
    enhanced_policy: EnhancedSeparatorPolicy | None = None,
) -> bool:
    policy = enhanced_policy or EnhancedSeparatorPolicy()
    if analysis == "off":
        return False
    if analysis == "always":
        return True
    expected = max(0, count - 1)
    if expected <= 0:
        return False
    hard = [gap for gap in gaps if gap.method in HARD_GAP_METHODS]
    model_only = [gap for gap in gaps if gap.method in {"equal", "grid"}]
    low_score_hard = any(gap.score < policy.auto_low_score for gap in hard)
    return len(hard) < expected or bool(model_only) or low_score_hard
