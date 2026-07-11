from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ....domain import Box
from ....geometry.detection_parameters import OuterBoxDetectionParameters
from ....utils import clamp_int, runs_from_mask


@dataclass(frozen=True)
class OuterSideBoundary:
    side: str
    boundary: int
    boundary_model: str
    reason: str
    holder_run: int

@dataclass(frozen=True)
class SideBoundaryOuterResult:
    box: Box | None
    sides: tuple[OuterSideBoundary, ...]
    reason: str

def _first_photo_footprint_index(holder_mask: np.ndarray, min_run: int) -> tuple[int, str, int]:
    if holder_mask.size == 0:
        return 0, "empty_profile", 0
    footprint = ~holder_mask.astype(bool)
    runs = runs_from_mask(footprint)
    for start, end in runs:
        if end - start >= min_run:
            holder_run = int(np.count_nonzero(holder_mask[:start]))
            return int(start), "holder_to_photo_footprint", holder_run
    candidates = np.flatnonzero(footprint)
    if candidates.size:
        first = int(candidates[0])
        return first, "weak_holder_to_photo_footprint", int(np.count_nonzero(holder_mask[:first]))
    return 0, "all_holder", int(np.count_nonzero(holder_mask))


def _inside_mean_for_axis(gray: np.ndarray, side: str, boundary: int, depth: int) -> float:
    h, w = gray.shape
    depth = max(1, int(depth))
    if side == "left":
        lo = max(0, min(w, boundary))
        hi = max(lo + 1, min(w, lo + depth))
        return float(gray[:, lo:hi].mean()) if hi > lo else 255.0
    if side == "right":
        hi = max(0, min(w, boundary))
        lo = max(0, hi - depth)
        return float(gray[:, lo:hi].mean()) if hi > lo else 255.0
    if side == "top":
        lo = max(0, min(h, boundary))
        hi = max(lo + 1, min(h, lo + depth))
        return float(gray[lo:hi, :].mean()) if hi > lo else 255.0
    hi = max(0, min(h, boundary))
    lo = max(0, hi - depth)
    return float(gray[lo:hi, :].mean()) if hi > lo else 255.0


def _inside_mean_for_boundary_box(gray: np.ndarray, side: str, box: Box, depth: int) -> float:
    h, w = gray.shape
    depth = max(1, int(depth))
    left = max(0, min(w, box.left))
    right = max(left + 1, min(w, box.right))
    top = max(0, min(h, box.top))
    bottom = max(top + 1, min(h, box.bottom))
    if side == "left":
        lo = left
        hi = max(lo + 1, min(right, lo + depth))
        return float(gray[top:bottom, lo:hi].mean())
    if side == "right":
        hi = right
        lo = max(left, hi - depth)
        return float(gray[top:bottom, lo:hi].mean())
    if side == "top":
        lo = top
        hi = max(lo + 1, min(bottom, lo + depth))
        return float(gray[lo:hi, left:right].mean())
    hi = bottom
    lo = max(top, hi - depth)
    return float(gray[lo:hi, left:right].mean())


def _boundary_model(inside_mean: float, config: OuterBoxDetectionParameters) -> str:
    if inside_mean <= float(config.white_dark_threshold):
        return "black_border_to_white_holder"
    if inside_mean >= float(config.white_light_threshold):
        return "mixed_or_uncertain"
    return "content_to_white_holder"


def _white_holder_side_boundary(
    gray: np.ndarray,
    side: str,
    holder_fraction: np.ndarray,
    config: OuterBoxDetectionParameters,
    min_run: int,
) -> OuterSideBoundary:
    holder_mask = holder_fraction >= float(config.white_border_ratio)
    boundary_from_start, reason, holder_run = _first_photo_footprint_index(holder_mask, min_run)
    if side in {"right", "bottom"}:
        axis_len = gray.shape[1] if side == "right" else gray.shape[0]
        boundary = axis_len - boundary_from_start
    else:
        boundary = boundary_from_start
    inside_mean = _inside_mean_for_axis(gray, side, boundary, min_run)
    return OuterSideBoundary(
        side=side,
        boundary=int(boundary),
        boundary_model=_boundary_model(inside_mean, config),
        reason=reason,
        holder_run=int(holder_run),
    )


def _footprint_side_boundary(
    side: str,
    footprint: np.ndarray,
    min_run: int,
    boundary_model: str,
) -> OuterSideBoundary:
    boundary_from_start, reason, holder_run = _first_photo_footprint_index(
        ~footprint.astype(bool),
        min_run,
    )
    axis_len = int(footprint.size)
    boundary = (
        axis_len - boundary_from_start
        if side in {"right", "bottom"}
        else boundary_from_start
    )
    return OuterSideBoundary(
        side=side,
        boundary=int(boundary),
        boundary_model=boundary_model,
        reason=reason,
        holder_run=int(holder_run),
    )


def _outer_from_sides(
    gray: np.ndarray,
    sides: tuple[OuterSideBoundary, ...],
    config: OuterBoxDetectionParameters,
    reason: str,
) -> SideBoundaryOuterResult:
    h, w = gray.shape
    by_side = {side.side: side for side in sides}
    if set(by_side) != {"left", "right", "top", "bottom"}:
        return SideBoundaryOuterResult(None, sides, "incomplete_sides")
    margin_x = max(
        config.white_margin_min,
        int(round(w * config.white_margin_ratio)),
    )
    margin_y = max(
        config.white_margin_min,
        int(round(h * config.white_margin_ratio)),
    )
    box = Box(
        by_side["left"].boundary,
        by_side["top"].boundary,
        by_side["right"].boundary,
        by_side["bottom"].boundary,
    ).expand(margin_x, margin_y, w, h)
    if (
        not box.valid()
        or box.width < max(config.min_width_px, w * config.white_min_width_ratio)
        or box.height < max(config.min_height_px, h * config.white_min_height_ratio)
    ):
        return SideBoundaryOuterResult(None, sides, "invalid_or_too_small")
    return SideBoundaryOuterResult(box, sides, reason)


def side_boundary_outer_proposals(
    gray: np.ndarray,
    config: OuterBoxDetectionParameters,
) -> tuple[SideBoundaryOuterResult, ...]:
    h, w = gray.shape
    min_run_x = clamp_int(w * config.white_run_ratio, config.white_run_min, config.white_run_max)
    min_run_y = clamp_int(h * config.white_run_ratio, config.white_run_min, config.white_run_max)
    white = gray >= int(config.white_light_threshold)
    col_holder = white.mean(axis=0)
    row_holder = white.mean(axis=1)
    white_sides = (
        _white_holder_side_boundary(gray, "left", col_holder, config, min_run_x),
        _white_holder_side_boundary(gray, "right", col_holder[::-1], config, min_run_x),
        _white_holder_side_boundary(gray, "top", row_holder, config, min_run_y),
        _white_holder_side_boundary(gray, "bottom", row_holder[::-1], config, min_run_y),
    )
    left, right, top, bottom = (
        white_sides[0].boundary,
        white_sides[1].boundary,
        white_sides[2].boundary,
        white_sides[3].boundary,
    )
    raw_box = Box(left, top, right, bottom)
    if raw_box.valid():
        focused_sides: list[OuterSideBoundary] = []
        for side in white_sides:
            depth = min_run_x if side.side in {"left", "right"} else min_run_y
            inside_mean = _inside_mean_for_boundary_box(gray, side.side, raw_box, depth)
            focused_sides.append(
                OuterSideBoundary(
                    side=side.side,
                    boundary=side.boundary,
                    boundary_model=_boundary_model(inside_mean, config),
                    reason=side.reason,
                    holder_run=side.holder_run,
                )
            )
        white_sides = tuple(focused_sides)

    tonal = gray < int(config.bw_not_white_threshold)
    tonal_cols = tonal.mean(axis=0) >= float(config.tonal_footprint_min_fraction)
    tonal_rows = tonal.mean(axis=1) >= float(config.tonal_footprint_min_fraction)
    tonal_sides = (
        _footprint_side_boundary("left", tonal_cols, min_run_x, "tonal_transition"),
        _footprint_side_boundary("right", tonal_cols[::-1], min_run_x, "tonal_transition"),
        _footprint_side_boundary("top", tonal_rows, min_run_y, "tonal_transition"),
        _footprint_side_boundary("bottom", tonal_rows[::-1], min_run_y, "tonal_transition"),
    )

    texture_cols = gray.astype(np.float32).std(axis=0) / 255.0
    texture_rows = gray.astype(np.float32).std(axis=1) / 255.0
    texture_sides = (
        _footprint_side_boundary(
            "left",
            texture_cols >= config.texture_activity_min,
            min_run_x,
            "texture_transition",
        ),
        _footprint_side_boundary(
            "right",
            texture_cols[::-1] >= config.texture_activity_min,
            min_run_x,
            "texture_transition",
        ),
        _footprint_side_boundary(
            "top",
            texture_rows >= config.texture_activity_min,
            min_run_y,
            "texture_transition",
        ),
        _footprint_side_boundary(
            "bottom",
            texture_rows[::-1] >= config.texture_activity_min,
            min_run_y,
            "texture_transition",
        ),
    )
    measured = (
        _outer_from_sides(gray, white_sides, config, "white_holder_boundary"),
        _outer_from_sides(gray, tonal_sides, config, "tonal_boundary"),
        _outer_from_sides(gray, texture_sides, config, "texture_boundary"),
    )
    valid = tuple(result for result in measured if result.box is not None)
    if not valid:
        return measured
    mixed_sides = tuple(
        (
            min(
                (side for result in valid for side in result.sides if side.side == name),
                key=lambda side: side.boundary,
            )
            if name in {"left", "top"}
            else max(
                (side for result in valid for side in result.sides if side.side == name),
                key=lambda side: side.boundary,
            )
        )
        for name in ("left", "right", "top", "bottom")
    )
    return (
        *measured,
        _outer_from_sides(gray, mixed_sides, config, "mixed_safe_overcontain"),
    )
