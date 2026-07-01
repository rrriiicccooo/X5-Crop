from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

import numpy as np

from ..config import Config
from ..domain import Box, Detection
from ..policies.base import (
    ApprovedGeometryAdjustmentPolicy,
    EdgeBleedProtectionPolicy,
    OutputPolicy,
)
from ..utils import clamp_float, clamp_int
from .boxes import map_work_box, original_box_to_work
from .layout import work_gray


def apply_edge_bleed_protection(
    detection: Detection,
    config: Config,
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


def detection_geometry_config(config: Config, policy: OutputPolicy) -> Config:
    return replace(
        config,
        bleed_x=int(policy.detection_long_axis_bleed),
        bleed_y=int(policy.detection_short_axis_bleed),
    )


def detection_has_overlap_bleed_risk(detection: Detection) -> bool:
    overlap_bleed = detection.detail.get("overlap_bleed_risk")
    if isinstance(overlap_bleed, dict) and bool(overlap_bleed.get("risk", False)):
        return True

    lucky = detection.detail.get("lucky_pass_risk_score")
    if isinstance(lucky, dict):
        if bool(lucky.get("risk", False)):
            return True
        counts = lucky.get("overlap_risk_counts")
        if isinstance(counts, dict):
            if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                return True

    diagnostics = detection.detail.get("diagnostics")
    if isinstance(diagnostics, dict):
        summary = diagnostics.get("summary")
        if isinstance(summary, dict):
            if int(summary.get("overlap_like_model_gaps", 0) or 0) > 0:
                return True
            counts = summary.get("overlap_risk_counts")
            if isinstance(counts, dict):
                if int(counts.get("strong", 0) or 0) > 0 or int(counts.get("medium", 0) or 0) > 0:
                    return True
    return False


def output_bleed_config_for_detection(
    config: Config,
    detection: Detection,
    policy: OutputPolicy,
) -> Config:
    if not detection_has_overlap_bleed_risk(detection):
        return config
    target_bleed_x = max(int(config.bleed_x), int(policy.overlap_risk_long_axis_bleed))
    if target_bleed_x == int(config.bleed_x):
        return config
    return replace(config, bleed_x=target_bleed_x)


def apply_output_bleed(detection: Detection, detection_config: Config, output_config: Config, image_w: int, image_h: int) -> None:
    if int(detection_config.bleed_x) == int(output_config.bleed_x) and int(detection_config.bleed_y) == int(output_config.bleed_y):
        return
    frames_work = [original_box_to_work(frame, detection.layout, image_w, image_h) for frame in detection.frames]
    work_w = image_w if detection.layout == "horizontal" else image_h
    work_h = image_h if detection.layout == "horizontal" else image_w
    adjusted_work: list[Box] = []
    for frame in frames_work:
        raw = Box(
            frame.left + int(detection_config.bleed_x),
            frame.top + int(detection_config.bleed_y),
            frame.right - int(detection_config.bleed_x),
            frame.bottom - int(detection_config.bleed_y),
        )
        if not raw.valid():
            return
        adjusted_work.append(raw.expand(int(output_config.bleed_x), int(output_config.bleed_y), work_w, work_h))
    detection.frames = [map_work_box(frame, detection.layout, image_w, image_h) for frame in adjusted_work]
    detection.detail["output_bleed"] = {
        "used": True,
        "detection_long_axis_bleed": int(detection_config.bleed_x),
        "detection_short_axis_bleed": int(detection_config.bleed_y),
        "output_long_axis_bleed": int(output_config.bleed_x),
        "output_short_axis_bleed": int(output_config.bleed_y),
        "overlap_risk_long_axis_bleed": bool(detection_has_overlap_bleed_risk(detection)),
    }


def reapply_cached_output_bleed(detection: Detection, config: Config, image_w: int, image_h: int) -> None:
    output_bleed = detection.detail.get("output_bleed")
    if not isinstance(output_bleed, dict):
        return
    try:
        cached_x = int(output_bleed.get("output_long_axis_bleed", config.bleed_x))
        cached_y = int(output_bleed.get("output_short_axis_bleed", config.bleed_y))
    except (TypeError, ValueError):
        return
    if cached_x == int(config.bleed_x) and cached_y == int(config.bleed_y):
        return
    cached_config = replace(config, bleed_x=cached_x, bleed_y=cached_y)
    apply_output_bleed(detection, cached_config, config, image_w, image_h)
    detection.detail["reused_output_bleed_adjustment"] = {
        "from_long_axis_bleed": int(cached_x),
        "from_short_axis_bleed": int(cached_y),
        "to_long_axis_bleed": int(config.bleed_x),
        "to_short_axis_bleed": int(config.bleed_y),
    }


def apply_approved_geometry_adjustment(
    detection: Detection,
    gray: np.ndarray,
    config: Config,
    status: str,
    policy: ApprovedGeometryAdjustmentPolicy,
) -> None:
    if status != "approved_auto" or detection.strip_mode != "full" or len(detection.frames) != detection.count:
        return
    if detection.review_reasons:
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
    band_top = outer.top + int(round(outer.height * 0.12))
    band_bottom = outer.bottom - int(round(outer.height * 0.12))
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
        col_content = (strip < 242).mean(axis=0)
        if side == "left":
            active = np.where(col_content > 0.018)[0]
            return int(hi - (lo + int(active[0]))) if active.size else 0
        active = np.where(col_content > 0.018)[0]
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
        "original_outer": asdict(original_outer),
        "adjusted_outer": asdict(outer),
        **changes,
    }
    detection.outer = map_work_box(outer, detection.layout, gray.shape[1], gray.shape[0])
    detection.frames = [map_work_box(frame, detection.layout, gray.shape[1], gray.shape[0]) for frame in frames]
