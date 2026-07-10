from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

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
    inside_mean: float

    def detail(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "boundary": int(self.boundary),
            "boundary_model": self.boundary_model,
            "reason": self.reason,
            "holder_run": int(self.holder_run),
            "inside_mean": float(self.inside_mean),
        }


@dataclass(frozen=True)
class SideBoundaryOuterResult:
    box: Box | None
    sides: tuple[OuterSideBoundary, ...]
    reason: str

    def detail(self) -> dict[str, Any]:
        return {
            "used": self.box is not None,
            "reason": self.reason,
            "evidence_name": "outer_side_boundary_evidence",
            "physical_rule": "mixed_boundary_side_independent",
            "box": None if self.box is None else asdict(self.box),
            "sides": [side.detail() for side in self.sides],
        }


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


def _side_boundary(
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
        inside_mean=float(inside_mean),
    )


def side_boundary_outer(
    gray: np.ndarray,
    config: OuterBoxDetectionParameters,
) -> SideBoundaryOuterResult:
    h, w = gray.shape
    min_run_x = clamp_int(w * config.white_run_ratio, config.white_run_min, config.white_run_max)
    min_run_y = clamp_int(h * config.white_run_ratio, config.white_run_min, config.white_run_max)
    white = gray >= int(config.white_light_threshold)
    col_holder = white.mean(axis=0)
    row_holder = white.mean(axis=1)
    sides = (
        _side_boundary(gray, "left", col_holder, config, min_run_x),
        _side_boundary(gray, "right", col_holder[::-1], config, min_run_x),
        _side_boundary(gray, "top", row_holder, config, min_run_y),
        _side_boundary(gray, "bottom", row_holder[::-1], config, min_run_y),
    )
    left, right, top, bottom = sides[0].boundary, sides[1].boundary, sides[2].boundary, sides[3].boundary
    raw_box = Box(left, top, right, bottom)
    if raw_box.valid():
        focused_sides: list[OuterSideBoundary] = []
        for side in sides:
            depth = min_run_x if side.side in {"left", "right"} else min_run_y
            inside_mean = _inside_mean_for_boundary_box(gray, side.side, raw_box, depth)
            focused_sides.append(
                OuterSideBoundary(
                    side=side.side,
                    boundary=side.boundary,
                    boundary_model=_boundary_model(inside_mean, config),
                    reason=side.reason,
                    holder_run=side.holder_run,
                    inside_mean=inside_mean,
                )
            )
        sides = tuple(focused_sides)
    margin_x = max(config.white_margin_min, int(round(w * config.white_margin_ratio)))
    margin_y = max(config.white_margin_min, int(round(h * config.white_margin_ratio)))
    box = Box(left, top, right, bottom).expand(margin_x, margin_y, w, h)
    if (
        not box.valid()
        or box.width < max(config.min_width_px, w * config.white_min_width_ratio)
        or box.height < max(config.min_height_px, h * config.white_min_height_ratio)
    ):
        return SideBoundaryOuterResult(None, sides, "invalid_or_too_small")
    return SideBoundaryOuterResult(box, sides, "ok")
