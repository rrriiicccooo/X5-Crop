from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np

from ..detection.detail import final_review_reasons_from_detail
from ..domain import Box, Detection
from ..geometry.boxes import map_work_box, original_box_to_work
from ..geometry.layout import work_gray
from ..policies.runtime.final import ApprovedGeometryAdjustmentPolicy
from ..policies.runtime.output import EdgeBleedProtectionPolicy
from ..runtime.config import RuntimeConfig
from ..utils import clamp_float, clamp_int


def apply_edge_bleed_protection(
    detection: Detection,
    config: RuntimeConfig,
    image_w: int,
    image_h: int,
    policy: EdgeBleedProtectionPolicy,
) -> None:
    if not policy.enabled:
        return
    if detection.strip_mode != "full" or detection.count <= 1 or len(detection.frames) != detection.count:
        return
    outer_work = original_box_to_work(detection.outer, detection.layout, image_w, image_h)
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    if not outer_work.valid() or any(not frame.valid() for frame in frames_work):
        return

    work_w = image_w if detection.layout == "horizontal" else image_h
    nominal = float(outer_work.width) / float(max(1, detection.count))
    edge_guard = clamp_float(
        nominal * policy.guard_ratio,
        policy.guard_min,
        policy.guard_max,
    )
    changed: list[str] = []

    first_target = max(0, outer_work.left - int(config.bleed_x))
    if frames_work[0].left > first_target + edge_guard:
        frames_work[0] = Box(first_target, frames_work[0].top, frames_work[0].right, frames_work[0].bottom)
        changed.append("first")

    last_target = min(work_w, outer_work.right + int(config.bleed_x))
    if frames_work[-1].right < last_target - edge_guard:
        frames_work[-1] = Box(frames_work[-1].left, frames_work[-1].top, last_target, frames_work[-1].bottom)
        changed.append("last")

    if not changed or any(not frame.valid() for frame in frames_work):
        return

    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in frames_work]
    detection.detail["edge_bleed_protection"] = {
        "used": True,
        "pinned": changed,
        "edge_guard": edge_guard,
        "long_axis_bleed": int(config.bleed_x),
        "edge_guard_basis": "nominal_frame_width_ratio",
    }


def apply_approved_geometry_adjustment(
    detection: Detection,
    gray: np.ndarray,
    config: RuntimeConfig,
    status: str,
    policy: ApprovedGeometryAdjustmentPolicy,
) -> None:
    if status != "approved_auto" or detection.strip_mode != "full" or len(detection.frames) != detection.count:
        return
    if final_review_reasons_from_detail(detection):
        return
    gray_work = work_gray(gray, detection.layout)
    h, w = gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, gray.shape[1], gray.shape[0])
    frames = [original_box_to_work(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in detection.frames]
    if not outer.valid() or any(not frame.valid() for frame in frames):
        return

    original_outer = outer
    changes: dict[str, Any] = {}
    long_limit = clamp_int(
        (outer.width / float(max(1, detection.count))) * policy.long_limit_ratio,
        policy.long_limit_min,
        policy.long_limit_max,
    )
    band_top = outer.top + int(round(outer.height * policy.side_band_trim_ratio))
    band_bottom = outer.bottom - int(round(outer.height * policy.side_band_trim_ratio))
    if band_bottom <= band_top:
        band_top, band_bottom = outer.top, outer.bottom

    def side_extension(side: str) -> int:
        if side == "left":
            lo, hi = max(0, outer.left - long_limit), outer.left
        else:
            lo, hi = outer.right, min(w, outer.right + long_limit)
        if hi <= lo:
            return 0
        strip = gray_work[band_top:band_bottom, lo:hi]
        if strip.size == 0:
            return 0
        col_content = (strip < policy.content_threshold_u8).mean(axis=0)
        active = np.where(col_content > policy.min_active_column_fraction)[0]
        if side == "left":
            return int(hi - (lo + int(active[0]))) if active.size else 0
        return int(int(active[-1]) + 1) if active.size else 0

    pitch = float(outer.width) / float(max(1, detection.count))
    min_long_ext = clamp_int(
        pitch * policy.min_ext_ratio,
        policy.min_ext_min,
        policy.min_ext_max,
    )
    left_ext = side_extension("left")
    right_ext = side_extension("right")
    left_ext = left_ext if left_ext >= min_long_ext else 0
    right_ext = right_ext if right_ext >= min_long_ext else 0
    if 0 < left_ext <= long_limit:
        outer = Box(max(0, outer.left - left_ext), outer.top, outer.right, outer.bottom)
        frames[0] = Box(outer.left, frames[0].top, frames[0].right, frames[0].bottom)
    if 0 < right_ext <= long_limit:
        outer = Box(outer.left, outer.top, min(w, outer.right + right_ext), outer.bottom)
        frames[-1] = Box(frames[-1].left, frames[-1].top, outer.right, frames[-1].bottom)
    if left_ext or right_ext:
        changes["long_axis_expand"] = {
            "left": int(left_ext),
            "right": int(right_ext),
            "limit": int(long_limit),
            "minimum": int(min_long_ext),
        }

    if not changes or not outer.valid() or any(not frame.valid() for frame in frames):
        return
    detection.detail["approved_geometry_adjustment"] = {
        "used": True,
        "role": "approved_output_geometry_adjustment",
        "parameters": asdict(policy),
        "original_outer": asdict(original_outer),
        "adjusted_outer": asdict(outer),
        **changes,
    }
    detection.outer = map_work_box(outer, detection.layout, gray.shape[1], gray.shape[0])
    detection.frames = [map_work_box(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in frames]


__all__ = [
    "apply_approved_geometry_adjustment",
    "apply_edge_bleed_protection",
]
