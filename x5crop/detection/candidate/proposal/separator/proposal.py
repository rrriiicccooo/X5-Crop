from __future__ import annotations

from typing import Optional

import numpy as np

from .....domain import Box, Gap
from .....formats import FormatSpec
from .....geometry.detection_parameters import GapSearchParameters
from .....geometry.gap_search import find_gap
from .....policies.registry import get_detection_policy
from .....policies.runtime.policy import DetectionPolicy
from .....utils import clamp_int, runs_from_mask, sampled_percentile, smooth_1d


def propose_standard_separator_gaps(
    profile: np.ndarray,
    origin: float,
    pitch: float,
    count: int,
    format_name: str,
    max_width_ratio_override: Optional[float],
    gap_search: GapSearchParameters,
) -> list[Gap]:
    return [
        find_gap(
            profile,
            origin + pitch * index,
            pitch,
            index,
            format_name,
            max_width_ratio_override,
            gap_search,
        )
        for index in range(1, count)
    ]


def propose_separator_width_profile_gaps(
    gray_work: np.ndarray,
    outer: Box,
    count: int,
    fmt: FormatSpec,
    policy: Optional[DetectionPolicy] = None,
) -> list[Gap]:
    policy = policy or get_detection_policy(fmt.name, "full")
    separator_width_profile = policy.outer.proposal.geometry.separator.width_profile
    required_count = int(separator_width_profile.required_count)
    if (
        separator_width_profile.mode == "off"
        or count <= 1
        or (required_count > 0 and count != required_count)
        or not outer.valid()
    ):
        return []
    crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if crop.size == 0:
        return []
    sample = crop[:: max(1, crop.shape[0] // 500), :: max(1, crop.shape[1] // 2000)]
    p01, p99 = sampled_percentile(sample, [1, 99])
    span = max(1.0, float(p99 - p01))
    threshold = float(p01) + span * separator_width_profile.threshold_span_ratio
    width_profile = (crop <= threshold).mean(axis=0).astype(np.float32)
    width_profile = smooth_1d(
        width_profile,
        max(
            separator_width_profile.profile_smooth_min,
            int(round(outer.height * separator_width_profile.profile_smooth_short_axis_ratio)),
        ),
    )
    pitch = outer.width / float(max(1, count))
    min_width = clamp_int(
        outer.height * separator_width_profile.min_width_ratio,
        separator_width_profile.min_width_min,
        separator_width_profile.min_width_max,
    )
    max_width = clamp_int(
        outer.height * separator_width_profile.max_width_ratio,
        min_width + 1,
        max(separator_width_profile.max_width_floor, int(outer.height * separator_width_profile.max_width_cap_ratio)),
    )
    gaps: list[Gap] = []
    for index in range(1, count):
        expected = pitch * index
        window = clamp_int(pitch * 0.28, 260, max(300, int(pitch * 0.38)))
        lo = max(0, int(round(expected - window)))
        hi = min(len(width_profile), int(round(expected + window)))
        best: Optional[tuple[float, int, int]] = None
        for run_start, run_end in runs_from_mask(width_profile[lo:hi] >= 0.42):
            start = lo + int(run_start)
            end = lo + int(run_end)
            width = end - start
            if width < min_width or width > max_width:
                continue
            mean_score = float(width_profile[start:end].mean())
            center = (start + end - 1) * 0.5
            distance_penalty = abs(center - expected) / max(1.0, pitch)
            score = mean_score - 0.35 * distance_penalty
            if best is None or score > best[0]:
                best = (score, start, end)
        if best is None:
            continue
        score, start, end = best
        center = (start + end - 1) * 0.5
        max_core_width = max(min_width, outer.height * separator_width_profile.core_width_cap_ratio)
        if (end - start) > max_core_width:
            half_width = max_core_width * 0.5
            start = int(round(max(0.0, center - half_width)))
            end = int(round(min(float(len(width_profile)), center + half_width)))
        gaps.append(Gap(index, float(center), float(1.0 + max(0.0, score)), "detected", float(start), float(end)))
    return gaps


__all__ = [
    "propose_separator_width_profile_gaps",
    "propose_standard_separator_gaps",
]
