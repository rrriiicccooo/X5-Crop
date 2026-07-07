from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ...domain import Box, Detection
from ...gap_methods import is_hard_gap_method
from ...geometry.boxes import box_cache_key, original_box_to_work
from ...geometry.layout import work_gray
from ...policies.registry import get_detection_policy
from ...policies.runtime.policy import DetectionPolicy
from ...cache import AnalysisCache
from ...utils import bbox_from_mask, box_from_dict, clamp_int
from .evidence_cache_keys import detection_gap_cache_key


def outer_alignment_cache_key(detection: Detection, source_w: int, source_h: int) -> tuple[Any, ...]:
    return (
        str(detection.film_format),
        str(detection.layout),
        str(detection.strip_mode),
        int(detection.count),
        int(source_w),
        int(source_h),
        box_cache_key(detection.outer),
        tuple(detection_gap_cache_key(detection)),
    )


def outer_content_alignment_detail(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
    policy: Optional[DetectionPolicy] = None,
) -> dict[str, Any]:
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    alignment = policy.outer.correction.content_containment
    work_h, work_w = gray_work.shape
    source_h, source_w = gray.shape
    detail_key: Optional[tuple[Any, ...]] = None
    if cache is not None and cache.layout == detection.layout:
        detail_key = outer_alignment_cache_key(detection, source_w, source_h)
        cached = cache.outer_alignment_details.get(detail_key)
        if cached is not None:
            return copy.deepcopy(cached)
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    candidates: list[tuple[str, Box]] = []
    for threshold in (225, 210, 190):
        box = bbox_from_mask(gray_work < threshold, min_row_fraction=0.015, min_col_fraction=0.015)
        if box is not None and box.valid():
            candidates.append((f"gray_lt_{threshold}", box))
    if not candidates:
        return {"used": False, "reason": "no_content_bbox"}

    source, content_box = candidates[0]
    pitch = float(outer.width) / float(max(1, detection.count))
    long_slack_left = max(0, content_box.left - outer.left)
    long_slack_right = max(0, outer.right - content_box.right)
    short_slack_top = max(0, content_box.top - outer.top)
    short_slack_bottom = max(0, outer.bottom - content_box.bottom)
    long_undercrop_left = max(0, outer.left - content_box.left)
    long_undercrop_right = max(0, content_box.right - outer.right)
    short_undercrop_top = max(0, outer.top - content_box.top)
    short_undercrop_bottom = max(0, content_box.bottom - outer.bottom)
    max_long_slack = max(long_slack_left, long_slack_right)
    max_short_slack = max(short_slack_top, short_slack_bottom)
    max_long_undercrop = max(long_undercrop_left, long_undercrop_right)
    max_short_undercrop = max(short_undercrop_top, short_undercrop_bottom)
    long_slack_ratio = float(max_long_slack) / max(1.0, pitch)
    short_slack_ratio = float(max_short_slack) / max(1.0, float(outer.height))
    long_undercrop_ratio = float(max_long_undercrop) / max(1.0, pitch)
    short_undercrop_ratio = float(max_short_undercrop) / max(1.0, float(outer.height))
    content_width_ratio = float(content_box.width) / max(1.0, float(outer.width))
    content_height_ratio = float(content_box.height) / max(1.0, float(outer.height))
    white_edge_long_slack_min = clamp_int(
        pitch * alignment.white_edge_long_ratio,
        alignment.white_edge_long_min,
        alignment.white_edge_long_max,
    )
    long_slack_pixel_gate = clamp_int(
        pitch * alignment.long_gate_ratio,
        alignment.long_gate_min,
        alignment.long_gate_max,
    )
    short_slack_pixel_gate = clamp_int(
        float(outer.height) * alignment.short_gate_ratio,
        alignment.short_gate_min,
        alignment.short_gate_max,
    )

    edge_band = max(4, min(80, int(round(min(outer.width, outer.height) * alignment.border_band_ratio))))
    outer_crop = gray_work[outer.top:outer.bottom, outer.left:outer.right]
    if outer_crop.size:
        left_band = outer_crop[:, :min(edge_band, outer_crop.shape[1])]
        right_band = outer_crop[:, max(0, outer_crop.shape[1] - edge_band):]
        top_band = outer_crop[:min(edge_band, outer_crop.shape[0]), :]
        bottom_band = outer_crop[max(0, outer_crop.shape[0] - edge_band):, :]
        border_dark_fraction = {
            "left": float((left_band < 245).mean()) if left_band.size else 0.0,
            "right": float((right_band < 245).mean()) if right_band.size else 0.0,
            "top": float((top_band < 245).mean()) if top_band.size else 0.0,
            "bottom": float((bottom_band < 245).mean()) if bottom_band.size else 0.0,
        }
    else:
        border_dark_fraction = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}

    edge_hard_anchors = (
        detection.strip_mode == "full"
        and len(detection.gaps) >= 2
        and is_hard_gap_method(detection.gaps[0].method)
        and is_hard_gap_method(detection.gaps[-1].method)
    )
    white_edge_slack = (
        edge_hard_anchors
        and content_width_ratio >= alignment.content_width_min
        and max_short_slack <= max(24, int(round(float(outer.height) * alignment.edge_short_ratio)))
        and (
            (long_slack_left >= white_edge_long_slack_min and float(border_dark_fraction.get("left", 1.0)) <= alignment.edge_dark_max)
            or (long_slack_right >= white_edge_long_slack_min and float(border_dark_fraction.get("right", 1.0)) <= alignment.edge_dark_max)
        )
    )
    short_axis_semantic_ok = True
    if alignment.short_requires_hard_anchors:
        short_axis_semantic_ok = short_axis_semantic_ok and edge_hard_anchors
    if alignment.short_content_height_max < 1.0:
        short_axis_semantic_ok = short_axis_semantic_ok and content_height_ratio <= alignment.short_content_height_max

    overcontains_long = long_slack_ratio > alignment.long_excess_ratio or (max_long_slack >= long_slack_pixel_gate and long_slack_ratio > alignment.long_gate_excess_ratio) or white_edge_slack
    overcontains_short = short_axis_semantic_ok and short_slack_ratio > alignment.short_excess_ratio and max_short_slack >= short_slack_pixel_gate
    undercrops_long = max_long_undercrop >= long_slack_pixel_gate
    undercrops_short = max_short_undercrop >= short_slack_pixel_gate
    ok = not (undercrops_long or undercrops_short)
    reason = "ok"
    if undercrops_long:
        reason = "content_outside_outer_long_axis"
    elif undercrops_short:
        reason = "content_outside_outer_short_axis"

    detail = {
        "used": True,
        "ok": ok,
        "reason": reason,
        "overcontainment_allowed": True,
        "content_bbox_source": source,
        "outer_work_box": asdict(outer),
        "content_work_box": asdict(content_box),
        "long_slack_left": int(long_slack_left),
        "long_slack_right": int(long_slack_right),
        "short_slack_top": int(short_slack_top),
        "short_slack_bottom": int(short_slack_bottom),
        "long_undercrop_left": int(long_undercrop_left),
        "long_undercrop_right": int(long_undercrop_right),
        "short_undercrop_top": int(short_undercrop_top),
        "short_undercrop_bottom": int(short_undercrop_bottom),
        "max_long_slack": int(max_long_slack),
        "max_short_slack": int(max_short_slack),
        "max_long_undercrop": int(max_long_undercrop),
        "max_short_undercrop": int(max_short_undercrop),
        "long_slack_ratio": long_slack_ratio,
        "short_slack_ratio": short_slack_ratio,
        "long_undercrop_ratio": long_undercrop_ratio,
        "short_undercrop_ratio": short_undercrop_ratio,
        "content_width_ratio": content_width_ratio,
        "content_height_ratio": content_height_ratio,
        "overcontains_long_axis": bool(overcontains_long),
        "overcontains_short_axis": bool(overcontains_short),
        "white_edge_long_slack_min": int(white_edge_long_slack_min),
        "long_slack_pixel_gate": int(long_slack_pixel_gate),
        "short_slack_pixel_gate": int(short_slack_pixel_gate),
        "border_dark_fraction": border_dark_fraction,
        "edge_hard_anchors": edge_hard_anchors,
        "white_edge_slack": white_edge_slack,
        "short_axis_semantic_ok": bool(short_axis_semantic_ok),
        "short_content_height_max": float(alignment.short_content_height_max),
    }
    if detail_key is not None:
        cache.outer_alignment_details[detail_key] = copy.deepcopy(detail)
    return detail


def corrected_outer_from_alignment(alignment: dict[str, Any], count: int, policy: DetectionPolicy) -> Optional[Box]:
    alignment_policy = policy.outer.correction.content_containment
    if not bool(alignment.get("used", False)) or bool(alignment.get("ok", True)):
        return None
    try:
        outer = box_from_dict(alignment["outer_work_box"])
        content = box_from_dict(alignment["content_work_box"])
    except Exception:
        return None
    if not outer.valid() or not content.valid():
        return None

    pitch = float(outer.width) / float(max(1, count))
    alignment_margin_x = clamp_int(pitch * alignment_policy.margin_x_ratio, alignment_policy.margin_x_min, alignment_policy.margin_x_max)
    alignment_margin_y = clamp_int(float(outer.height) * alignment_policy.margin_y_ratio, alignment_policy.margin_y_min, alignment_policy.margin_y_max)
    long_margin_cap = clamp_int(pitch * alignment_policy.long_margin_cap_ratio, alignment_policy.long_margin_cap_min, alignment_policy.long_margin_cap_max)
    short_margin_cap = clamp_int(float(outer.height) * alignment_policy.short_margin_cap_ratio, alignment_policy.short_margin_cap_min, alignment_policy.short_margin_cap_max)
    long_margin = max(alignment_margin_x, min(long_margin_cap, int(round(pitch * alignment_policy.long_margin_ratio))))
    short_margin = max(alignment_margin_y, min(short_margin_cap, int(round(float(outer.height) * alignment_policy.short_margin_ratio))))
    left, top, right, bottom = outer.left, outer.top, outer.right, outer.bottom

    if int(alignment.get("long_slack_left", 0)) > 0:
        left = max(outer.left, content.left - long_margin)
    if int(alignment.get("long_slack_right", 0)) > 0:
        right = min(outer.right, content.right + long_margin)
    if int(alignment.get("short_slack_top", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        top = max(outer.top, content.top - short_margin)
    if int(alignment.get("short_slack_bottom", 0)) > 0 and str(alignment.get("reason", "")) == "outer_short_axis_excess":
        bottom = min(outer.bottom, content.bottom + short_margin)

    corrected = Box(left, top, right, bottom)
    if not corrected.valid():
        return None
    if corrected.width < max(80, int(round(outer.width * 0.80))) or corrected.height < max(40, int(round(outer.height * 0.80))):
        return None
    if corrected == outer:
        return None
    return corrected
