from __future__ import annotations

from typing import Any

import numpy as np

from ..domain import Box, Gap
from ..gap_methods import (
    is_detected_gap_method,
    is_edge_pair_gap_method,
    is_geometry_model_gap_method,
)
from ..utils import clamp_float
from .detection_parameters import FrameFitParameters


def frame_boxes_from_gaps(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    *,
    origin: float,
    pitch: float | None,
) -> list[Box]:
    if pitch is None:
        cuts = [float(outer.left)] + [gap.center + outer.left for gap in gaps] + [float(outer.right)]
    else:
        cuts = [outer.left + origin] + [outer.left + gap.center for gap in gaps] + [outer.left + origin + pitch * count]
    boxes: list[Box] = []
    for left, right in zip(cuts[:-1], cuts[1:]):
        box = Box(int(round(left)), outer.top, int(round(right)), outer.bottom)
        boxes.append(box.expand(bleed_x, bleed_y, image_w, image_h))
    return boxes[:count]


def frame_edge_weight(gap: Gap, config: FrameFitParameters) -> float:
    if gap.width <= 0:
        return 0.0
    if is_edge_pair_gap_method(gap.method):
        return max(0.0, min(float(config.edge_pair_score_cap), gap.score)) * float(config.edge_pair_weight_multiplier)
    if is_detected_gap_method(gap.method):
        return max(0.0, min(float(config.detected_gap_score_cap), gap.score))
    return 0.0


def relative_ranges_from_gaps(outer: Box, gaps: list[Gap]) -> list[tuple[float, float]]:
    cuts = [0.0] + [float(gap.center) for gap in gaps] + [float(outer.width)]
    return [(left, right) for left, right in zip(cuts[:-1], cuts[1:])]


def box_list_from_relative_ranges(
    outer: Box,
    ranges: list[tuple[float, float]],
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
) -> list[Box]:
    out: list[Box] = []
    for left, right in ranges:
        box = Box(outer.left + int(round(left)), outer.top, outer.left + int(round(right)), outer.bottom)
        out.append(box.expand(bleed_x, bleed_y, image_w, image_h))
    return out


def fit_boxes_by_edge_evidence(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    config: FrameFitParameters,
) -> tuple[list[Box] | None, dict[str, Any]]:
    if not config.edge_evidence:
        return None, {"used": False, "reason": "edge_evidence_disabled"}
    if count <= 1 or len(gaps) != count - 1 or outer.width <= 1:
        return None, {"used": False, "reason": "not_applicable"}
    left_edges: list[tuple[float, float] | None] = [None] * count
    right_edges: list[tuple[float, float] | None] = [None] * count
    for i, gap in enumerate(gaps):
        weight = frame_edge_weight(gap, config)
        if weight <= 0 or gap.start is None or gap.end is None:
            continue
        right_edges[i] = (float(gap.start), weight)
        left_edges[i + 1] = (float(gap.end), weight)

    nominal = outer.width / float(count)
    samples: list[tuple[int, float]] = []
    for i, (left, right) in enumerate(zip(left_edges, right_edges), 1):
        if left is None or right is None:
            continue
        width = float(right[0]) - float(left[0])
        if nominal * config.nominal_min_ratio <= width <= nominal * config.nominal_max_ratio:
            samples.append((i, width))
    if len(samples) < config.min_edge_samples:
        return None, {"used": False, "reason": "too_few_edge_samples", "sample_count": len(samples)}

    widths = np.array([width for _, width in samples], dtype=np.float64)
    target = float(np.median(widths))
    tol = max(config.min_inlier_tolerance_px, target * config.inlier_tolerance_ratio)
    inliers = [(i, width) for i, width in samples if abs(width - target) <= tol]
    if len(inliers) < config.min_edge_samples:
        return None, {"used": False, "reason": "edge_samples_disagree", "sample_count": len(samples)}
    target = float(np.median(np.array([width for _, width in inliers], dtype=np.float64)))
    if not (nominal * config.nominal_min_ratio <= target <= nominal * config.nominal_max_ratio):
        return None, {"used": False, "reason": "target_width_out_of_range", "target_width": target}

    base_ranges = relative_ranges_from_gaps(outer, gaps)
    max_left = max(0.0, float(outer.width) - target)
    fitted: list[tuple[float, float]] = []
    adjusted: list[int] = []
    for i, (base_left, base_right) in enumerate(base_ranges):
        candidates: list[tuple[float, float]] = []
        if left_edges[i] is not None:
            candidates.append((float(left_edges[i][0]), float(left_edges[i][1])))
        if right_edges[i] is not None:
            candidates.append((float(right_edges[i][0]) - target, float(right_edges[i][1])))
        weak_boundary = any(
            0 <= gi < len(gaps) and is_geometry_model_gap_method(gaps[gi].method)
            for gi in (i - 1, i)
        )
        base_width = float(base_right) - float(base_left)
        if not candidates and not weak_boundary and abs(base_width - target) <= tol:
            fitted.append((base_left, base_right))
            continue
        base_left_from_center = (float(base_left) + float(base_right) - target) / 2.0
        candidates.append((base_left_from_center, config.edge_candidate_weight_with_edges if candidates else config.edge_candidate_weight_without_edges))
        new_left = weighted_median(candidates)
        new_left = min(max(0.0, new_left), max_left)
        new_right = new_left + target
        adjust_tolerance = clamp_float(
            target * config.edge_adjust_tolerance_ratio,
            config.edge_adjust_tolerance_min,
            config.edge_adjust_tolerance_max,
        )
        if abs(new_left - base_left) > adjust_tolerance or abs(new_right - base_right) > adjust_tolerance:
            adjusted.append(i + 1)
        fitted.append((new_left, new_right))
    if not adjusted:
        return None, {
            "used": False,
            "reason": "no_adjustment_needed",
            "target_width": target,
            "sample_indices": [i for i, _ in inliers],
        }
    return box_list_from_relative_ranges(outer, fitted, image_w, image_h, bleed_x, bleed_y), {
        "used": True,
        "method": "edge_evidence",
        "target_width": target,
        "sample_indices": [i for i, _ in inliers],
        "sample_widths": [float(width) for _, width in inliers],
        "adjusted_indices": adjusted,
    }


def fit_frame_boxes_from_gaps(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    *,
    origin: float,
    pitch: float | None,
    frame_fit: FrameFitParameters,
) -> tuple[list[Box], dict[str, Any]]:
    config = frame_fit
    base_boxes = frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        image_w,
        image_h,
        bleed_x,
        bleed_y,
        origin=origin,
        pitch=pitch,
    )
    fitted_boxes, detail = fit_boxes_by_edge_evidence(
        outer,
        gaps,
        count,
        image_w,
        image_h,
        bleed_x,
        bleed_y,
        config,
    )
    detail = dict(detail)
    detail["parameters"] = {
        "name": config.name,
        "edge_evidence": bool(config.edge_evidence),
        "min_edge_samples": int(config.min_edge_samples),
        "nominal_min_ratio": float(config.nominal_min_ratio),
        "nominal_max_ratio": float(config.nominal_max_ratio),
        "inlier_tolerance_ratio": float(config.inlier_tolerance_ratio),
        "min_inlier_tolerance_px": float(config.min_inlier_tolerance_px),
        "edge_candidate_weight_with_edges": float(config.edge_candidate_weight_with_edges),
        "edge_candidate_weight_without_edges": float(config.edge_candidate_weight_without_edges),
        "edge_adjust_tolerance_ratio": float(config.edge_adjust_tolerance_ratio),
        "edge_adjust_tolerance_min": float(config.edge_adjust_tolerance_min),
        "edge_adjust_tolerance_max": float(config.edge_adjust_tolerance_max),
    }
    if fitted_boxes is not None:
        return fitted_boxes, detail
    detail.setdefault("method", "geometry_model")
    return base_boxes, detail


def weighted_median(candidates: list[tuple[float, float]]) -> float:
    ordered = sorted((float(value), max(0.0, float(weight))) for value, weight in candidates)
    if not ordered:
        return 0.0
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return float(np.median(np.array([value for value, _ in ordered], dtype=np.float64)))
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= total / 2.0:
            return value
    return ordered[-1][0]
