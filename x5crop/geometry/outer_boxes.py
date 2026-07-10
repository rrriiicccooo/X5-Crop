from __future__ import annotations

import numpy as np

from ..domain import Box
from ..utils import bbox_from_mask, clamp_int, runs_from_mask
from .detection_parameters import OuterBoxDetectionParameters, OuterMaskProfileParameters


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
    config: OuterBoxDetectionParameters,
) -> Box:
    h, w = gray.shape
    not_white = gray < config.bw_not_white_threshold
    dark = gray < config.bw_dark_threshold
    mask = not_white | dark
    box = bbox_from_mask(
        mask,
        min_row_fraction=config.bw_min_fraction,
        min_col_fraction=config.bw_min_fraction,
    )
    if (
        box is None
        or box.width < max(config.min_width_px, w * config.bw_min_width_ratio)
        or box.height < max(config.min_height_px, h * config.bw_min_height_ratio)
    ):
        return Box(0, 0, w, h)

    margin_x = max(config.bw_margin_min, int(round(w * config.bw_margin_ratio)))
    margin_y = max(config.bw_margin_min, int(round(h * config.bw_margin_ratio)))
    return box.expand(margin_x, margin_y, w, h)


def detect_outer_white_x(
    gray: np.ndarray,
    config: OuterBoxDetectionParameters,
) -> Box:
    h, w = gray.shape
    min_run_y = clamp_int(h * config.white_run_ratio, config.white_run_min, config.white_run_max)
    min_run_x = clamp_int(w * config.white_run_ratio, config.white_run_min, config.white_run_max)
    y_background = (gray <= config.white_dark_threshold) | (gray >= config.white_light_threshold)
    x_background = gray >= config.white_light_threshold
    row_border = y_background.mean(axis=1) >= config.white_border_ratio
    col_border = x_background.mean(axis=0) >= config.white_border_ratio
    top = first_content_index(row_border, min_run_y)
    bottom = h - first_content_index(row_border[::-1], min_run_y)
    left = first_content_index(col_border, min_run_x)
    right = w - first_content_index(col_border[::-1], min_run_x)
    margin_x = max(config.white_margin_min, int(round(w * config.white_margin_ratio)))
    margin_y = max(config.white_margin_min, int(round(h * config.white_margin_ratio)))
    box = Box(left, top, right, bottom).expand(margin_x, margin_y, w, h)
    if (
        not box.valid()
        or box.width < max(config.min_width_px, w * config.white_min_width_ratio)
        or box.height < max(config.min_height_px, h * config.white_min_height_ratio)
    ):
        return Box(0, 0, w, h)
    return box


def detect_mask_profile_outer(
    gray: np.ndarray,
    profile: OuterMaskProfileParameters,
    config: OuterBoxDetectionParameters,
) -> Box | None:
    h, w = gray.shape
    mask = np.ones_like(gray, dtype=bool)
    if profile.low is not None:
        mask &= gray > int(profile.low)
    if profile.high is not None:
        mask &= gray < int(profile.high)
    box = bbox_from_mask(mask, min_row_fraction=profile.min_row_fraction, min_col_fraction=profile.min_col_fraction)
    if box is None:
        return None
    if (
        box.width < max(config.min_width_px, w * config.min_width_ratio)
        or box.height < max(config.min_height_px, h * config.min_height_ratio)
    ):
        return None
    return box.expand(
        max(config.bw_margin_min, int(w * config.mask_expand_ratio)),
        max(config.bw_margin_min, int(h * config.mask_expand_ratio)),
        w,
        h,
    )
