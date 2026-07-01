from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

from ..domain import Box, OuterCandidate
from ..policies.runtime_policy import OuterCandidateDetectionPolicy
from ..utils import clamp_int


def smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return values.astype(np.float32, copy=False)
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def runs_from_mask(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: Optional[int] = None
    for i, flag in enumerate(mask.astype(bool)):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def bbox_from_mask(mask: np.ndarray, min_row_fraction: float = 0.01, min_col_fraction: float = 0.01) -> Optional[Box]:
    if mask.size == 0:
        return None
    row_has = mask.mean(axis=1) >= min_row_fraction
    col_has = mask.mean(axis=0) >= min_col_fraction
    rows = np.flatnonzero(row_has)
    cols = np.flatnonzero(col_has)
    if rows.size == 0 or cols.size == 0:
        return None
    return Box(int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def first_content_index(border_mask: np.ndarray, min_run: int) -> int:
    if border_mask.size == 0:
        return 0
    content = ~border_mask.astype(bool)
    runs = runs_from_mask(content)
    for start, end in runs:
        if end - start >= min_run:
            return int(start)
    candidates = np.flatnonzero(content)
    return int(candidates[0]) if candidates.size else 0


def detect_outer(
    gray: np.ndarray,
    policy: OuterCandidateDetectionPolicy | None = None,
) -> Box:
    policy = policy or OuterCandidateDetectionPolicy()
    h, w = gray.shape
    not_white = gray < policy.bw_not_white_threshold
    dark = gray < policy.bw_dark_threshold
    mask = not_white | dark
    box = bbox_from_mask(
        mask,
        min_row_fraction=policy.bw_min_fraction,
        min_col_fraction=policy.bw_min_fraction,
    )
    if (
        box is None
        or box.width < max(policy.min_width_px, w * policy.bw_min_width_ratio)
        or box.height < max(policy.min_height_px, h * policy.bw_min_height_ratio)
    ):
        return Box(0, 0, w, h)

    margin_x = max(policy.bw_margin_min, int(round(w * policy.bw_margin_ratio)))
    margin_y = max(policy.bw_margin_min, int(round(h * policy.bw_margin_ratio)))
    return box.expand(margin_x, margin_y, w, h)


def detect_outer_white_x(
    gray: np.ndarray,
    policy: OuterCandidateDetectionPolicy | None = None,
) -> Box:
    policy = policy or OuterCandidateDetectionPolicy()
    h, w = gray.shape
    min_run_y = clamp_int(h * policy.white_run_ratio, policy.white_run_min, policy.white_run_max)
    min_run_x = clamp_int(w * policy.white_run_ratio, policy.white_run_min, policy.white_run_max)
    y_background = (gray <= policy.white_dark_threshold) | (gray >= policy.white_light_threshold)
    x_background = gray >= policy.white_light_threshold
    row_border = y_background.mean(axis=1) >= policy.white_border_ratio
    col_border = x_background.mean(axis=0) >= policy.white_border_ratio
    top = first_content_index(row_border, min_run_y)
    bottom = h - first_content_index(row_border[::-1], min_run_y)
    left = first_content_index(col_border, min_run_x)
    right = w - first_content_index(col_border[::-1], min_run_x)
    margin_x = max(policy.white_margin_min, int(round(w * policy.white_margin_ratio)))
    margin_y = max(policy.white_margin_min, int(round(h * policy.white_margin_ratio)))
    box = Box(left, top, right, bottom).expand(margin_x, margin_y, w, h)
    if (
        not box.valid()
        or box.width < max(policy.min_width_px, w * policy.white_min_width_ratio)
        or box.height < max(policy.min_height_px, h * policy.white_min_height_ratio)
    ):
        return Box(0, 0, w, h)
    return box


def unique_outer_candidates(candidates: Iterable[OuterCandidate]) -> list[OuterCandidate]:
    seen: set[tuple[int, int, int, int]] = set()
    out: list[OuterCandidate] = []
    for candidate in candidates:
        box = candidate.box
        key = (box.left, box.top, box.right, box.bottom)
        if key in seen or not box.valid():
            continue
        seen.add(key)
        out.append(candidate)
    return out


def detect_outer_candidates(
    gray: np.ndarray,
    policy: OuterCandidateDetectionPolicy | None = None,
) -> list[OuterCandidate]:
    policy = policy or OuterCandidateDetectionPolicy()
    h, w = gray.shape
    bw = detect_outer(gray, policy)
    white_x = detect_outer_white_x(gray, policy)
    candidates = [OuterCandidate("bw", bw, "base_outer")]
    if white_x.valid():
        max_reasonable = max(
            float(bw.width) * policy.white_x_width_multiplier,
            float(bw.width) + w * policy.white_x_extra_ratio,
        )
        if white_x.width >= bw.width and white_x.width <= max_reasonable:
            candidates.append(OuterCandidate("white_x", white_x, "base_outer"))
    for profile in policy.mask_profiles:
        mask = np.ones_like(gray, dtype=bool)
        if profile.low is not None:
            mask &= gray > int(profile.low)
        if profile.high is not None:
            mask &= gray < int(profile.high)
        box = bbox_from_mask(mask, min_row_fraction=profile.min_row_fraction, min_col_fraction=profile.min_col_fraction)
        if box is None:
            continue
        if (
            box.width < max(policy.min_width_px, w * policy.min_width_ratio)
            or box.height < max(policy.min_height_px, h * policy.min_height_ratio)
        ):
            continue
        candidates.append(
            OuterCandidate(
                profile.name,
                box.expand(
                    max(policy.bw_margin_min, int(w * policy.mask_expand_ratio)),
                    max(policy.bw_margin_min, int(h * policy.mask_expand_ratio)),
                    w,
                    h,
                ),
                "base_outer",
            )
        )
    unique = unique_outer_candidates(candidates)
    canvas_area = float(w * h)
    non_full = [
        candidate for candidate in unique
        if (candidate.box.width * candidate.box.height) / max(1.0, canvas_area) <= policy.candidate_max_area
    ]
    if non_full:
        return non_full
    return unique or [OuterCandidate("full_canvas", Box(0, 0, w, h), "base_outer")]
