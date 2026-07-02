from __future__ import annotations

from typing import Optional

import numpy as np

from ..constants import HARD_GAP_METHODS
from ..domain import Gap
from ..utils import clamp_float, clamp_int, runs_from_mask
from .detection_parameters import GapSearchConfig, RobustGridConfig


def find_gap(
    profile: np.ndarray,
    expected: float,
    pitch: float,
    index: int,
    format_name: str,
    max_width_ratio_override: Optional[float] = None,
    gap_search: GapSearchConfig | None = None,
) -> Gap:
    config = gap_search or GapSearchConfig()
    radius = clamp_int(pitch * config.radius_ratio, config.radius_min, config.radius_max)
    lo = max(1, int(round(expected)) - radius)
    hi = min(len(profile) - 1, int(round(expected)) + radius + 1)
    if hi <= lo:
        return Gap(index, float(expected), 0.0, "equal")
    local = profile[lo:hi]
    local_max = float(local.max()) if local.size else 0.0
    min_score = config.min_score
    if local.size == 0 or local_max < min_score:
        return Gap(index, float(expected), local_max, "equal")

    normal_max_gap_w = clamp_int(pitch * config.max_width_ratio, config.max_width_min, config.max_width_max)
    max_width_ratio = config.max_width_ratio if max_width_ratio_override is None else max_width_ratio_override
    max_gap_w = clamp_int(pitch * max_width_ratio, config.max_width_min, config.max_width_max)
    min_gap_w = clamp_int(pitch * config.min_width_ratio, config.min_width_min, config.min_width_max)
    guard_w = clamp_int(pitch * config.guard_ratio, config.guard_min, config.guard_max)
    peak_threshold = max(min_score, local_max * config.peak_multiplier)
    band_threshold = max(min_score * 0.86, local_max * config.band_multiplier)
    candidates: list[tuple[float, float, float, float, float, float, str]] = []

    for run_start, run_end in runs_from_mask(local >= peak_threshold):
        band_start, band_end = run_start, run_end
        while band_start > 0 and local[band_start - 1] >= band_threshold and (band_end - (band_start - 1)) <= max_gap_w:
            band_start -= 1
        while band_end < len(local) and local[band_end] >= band_threshold and ((band_end + 1) - band_start) <= max_gap_w:
            band_end += 1
        band_width = band_end - band_start
        if band_width < min_gap_w or band_width > max_gap_w:
            continue

        left_guard = local[max(0, band_start - guard_w):band_start]
        right_guard = local[band_end:min(len(local), band_end + guard_w)]
        if left_guard.size == 0 or right_guard.size == 0:
            continue
        mean_score = float(local[band_start:band_end].mean())
        side_score = max(float(left_guard.mean()), float(right_guard.mean()))
        prominence = mean_score - side_score
        if prominence < 0.08 and mean_score < 0.95:
            continue
        method = "detected"
        if max_width_ratio_override is not None and band_width > normal_max_gap_w:
            if mean_score < config.wide_min_mean or prominence < config.wide_min_prominence:
                continue
            method = "wide-separator"

        center = float(lo + (band_start + band_end - 1) / 2.0)
        start = float(lo + band_start)
        end = float(lo + band_end)
        distance = abs(center - expected) / max(1.0, pitch)
        quality = mean_score + 0.8 * prominence
        candidates.append((distance, -quality, -mean_score, center, start, end, method))

    if candidates:
        _, neg_quality, _, center, start, end, method = sorted(candidates)[0]
        return Gap(index, center, float(-neg_quality), method, start, end)

    return Gap(index, float(expected), local_max, "equal")


def constrain_gap_to_geometry(
    gap: Gap,
    expected: float,
    pitch: float,
    strip_mode: str,
    robust_grid: RobustGridConfig | None = None,
) -> Gap:
    if gap.method not in HARD_GAP_METHODS:
        return Gap(gap.index, float(expected), gap.score, "equal")
    config = robust_grid or RobustGridConfig()
    max_shift = clamp_float(
        pitch * (config.constrain_full_shift_ratio if strip_mode == "full" else config.constrain_partial_shift_ratio),
        config.constrain_shift_min,
        config.constrain_shift_max,
    )
    shift = max(-max_shift, min(max_shift, gap.center - expected))
    center = float(expected + shift)
    method = gap.method
    if gap.start is not None and gap.end is not None:
        delta = center - float(gap.center)
        start = float(gap.start + delta)
        end = float(gap.end + delta)
    else:
        start = None
        end = None
    return Gap(gap.index, center, gap.score, method, start, end)


def gap_width_cv(gaps: list[Gap], origin: float, pitch: float, count: int) -> float:
    if count <= 1:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    widths = np.diff(np.array(cuts, dtype=np.float64))
    if widths.size != count or np.any(widths <= 1):
        return 1.0
    return float(widths.std() / max(1.0, widths.mean()))


def local_gap_geometry_error(gaps: list[Gap], gap_index: int, origin: float, pitch: float, count: int) -> float:
    if count <= 1 or gap_index < 1 or gap_index >= count:
        return 0.0
    cuts = [float(origin)] + [float(gap.center) for gap in gaps] + [float(origin + pitch * count)]
    left_w = cuts[gap_index] - cuts[gap_index - 1]
    right_w = cuts[gap_index + 1] - cuts[gap_index]
    if left_w <= 1 or right_w <= 1:
        return float("inf")
    return abs(left_w - pitch) + abs(right_w - pitch)
