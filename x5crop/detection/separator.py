from __future__ import annotations

from typing import Optional

import numpy as np

from ..domain import Box, Gap
from ..formats import FormatSpec
from ..geometry import (
    apply_nearby_separator_corrections,
    apply_robust_grid,
    find_enhanced_gap,
    find_gap,
    light_hard_gap_trust,
    merge_enhanced_separator_gaps,
    refine_gaps_by_edge_pairs,
    separator_profile,
    should_run_enhanced_separator_analysis,
)
from .gates import separator_hard_evidence_ok
from ..policies.base import DetectionPolicy
from ..policies.registry import get_detection_policy
from ..utils import clamp_int, runs_from_mask, sampled_percentile, smooth_1d

def dark_band_gaps_for_outer(
    gray_work: np.ndarray,
    outer: Box,
    count: int,
    fmt: FormatSpec,
    policy: Optional[DetectionPolicy] = None,
) -> list[Gap]:
    policy = policy or get_detection_policy(fmt.name, "full")
    dark_band = policy.outer.dark_band_outer
    if dark_band.mode == "off" or count <= 1 or count != dark_band.required_count or not outer.valid():
        return []
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0:
        return []
    sample = crop[:: max(1, crop.shape[0] // 500), :: max(1, crop.shape[1] // 2000)]
    p01, p99 = sampled_percentile(sample, [1, 99])
    span = max(1.0, float(p99 - p01))
    dark_threshold = float(p01) + span * dark_band.threshold_span_ratio
    dark_profile = (crop <= dark_threshold).mean(axis=0).astype(np.float32)
    dark_profile = smooth_1d(
        dark_profile,
        max(dark_band.profile_smooth_min, int(round(outer.height * dark_band.profile_smooth_short_axis_ratio))),
    )
    pitch = outer.width / float(max(1, count))
    min_width = clamp_int(
        outer.height * dark_band.min_width_ratio,
        dark_band.min_width_min,
        dark_band.min_width_max,
    )
    max_width = clamp_int(
        outer.height * dark_band.max_width_ratio,
        min_width + 1,
        max(dark_band.max_width_floor, int(outer.height * dark_band.max_width_cap_ratio)),
    )
    gaps: list[Gap] = []
    for index in range(1, count):
        expected = pitch * index
        window = clamp_int(pitch * 0.28, 260, max(300, int(pitch * 0.38)))
        lo = max(0, int(round(expected - window)))
        hi = min(len(dark_profile), int(round(expected + window)))
        best: Optional[tuple[float, int, int]] = None
        for run_start, run_end in runs_from_mask(dark_profile[lo:hi] >= 0.42):
            start = lo + int(run_start)
            end = lo + int(run_end)
            width = end - start
            if width < min_width or width > max_width:
                continue
            mean_score = float(dark_profile[start:end].mean())
            center = (start + end - 1) * 0.5
            distance_penalty = abs(center - expected) / max(1.0, pitch)
            score = mean_score - 0.35 * distance_penalty
            if best is None or score > best[0]:
                best = (score, start, end)
        if best is None:
            continue
        score, start, end = best
        center = (start + end - 1) * 0.5
        max_core_width = max(min_width, outer.height * dark_band.core_width_cap_ratio)
        if (end - start) > max_core_width:
            half_width = max_core_width * 0.5
            start = int(round(max(0.0, center - half_width)))
            end = int(round(min(float(len(dark_profile)), center + half_width)))
        gaps.append(Gap(index, float(center), float(1.0 + max(0.0, score)), "wide-separator", float(start), float(end)))
    return gaps

__all__ = [
    "apply_nearby_separator_corrections",
    "apply_robust_grid",
    "dark_band_gaps_for_outer",
    "find_enhanced_gap",
    "find_gap",
    "light_hard_gap_trust",
    "merge_enhanced_separator_gaps",
    "refine_gaps_by_edge_pairs",
    "separator_hard_evidence_ok",
    "separator_profile",
    "should_run_enhanced_separator_analysis",
]
