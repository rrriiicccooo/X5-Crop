from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from ..domain import Box, Gap
from ..gap_methods import (
    is_detected_gap_method,
    is_edge_pair_gap_method,
    is_geometry_model_gap_method,
)
from ..utils import clamp_float


class FrameFitParameters(Protocol):
    name: str
    edge_evidence: bool
    geometry_fallback: bool
    min_edge_samples: int
    nominal_min_ratio: float
    nominal_max_ratio: float
    inlier_tolerance_ratio: float
    min_inlier_tolerance_px: float
    geometry_pitch_min_ratio: float
    geometry_pitch_max_ratio: float
    geometry_noop_width_cv: float
    geometry_outer_tolerance_ratio: float
    geometry_outer_tolerance_min: float
    geometry_outer_tolerance_max: float
    edge_candidate_weight_with_edges: float
    edge_candidate_weight_without_edges: float
    edge_adjust_tolerance_ratio: float
    edge_adjust_tolerance_min: float
    edge_adjust_tolerance_max: float


def frame_boxes_from_gaps(
    outer: Box,
    gaps: list[Gap],
    count: int,
    image_w: int,
    image_h: int,
    bleed_x: int,
    bleed_y: int,
    origin: float = 0.0,
    pitch: float | None = None,
    apply_geometry_fit: bool = True,
    geometry_config: FrameFitParameters | None = None,
) -> list[Box]:
    if pitch is None:
        cuts = [float(outer.left)] + [gap.center + outer.left for gap in gaps] + [float(outer.right)]
    else:
        cuts = [outer.left + origin] + [outer.left + gap.center for gap in gaps] + [outer.left + origin + pitch * count]
    if apply_geometry_fit:
        if geometry_config is None:
            raise ValueError("geometry_config is required when geometry fit is enabled")
        cuts = fit_cuts_by_geometry(cuts, outer, count, pitch, geometry_config)
    boxes: list[Box] = []
    for left, right in zip(cuts[:-1], cuts[1:]):
        box = Box(int(round(left)), outer.top, int(round(right)), outer.bottom)
        boxes.append(box.expand(bleed_x, bleed_y, image_w, image_h))
    return boxes[:count]


def fit_cuts_by_geometry(
    cuts: list[float],
    outer: Box,
    count: int,
    pitch: float | None,
    config: FrameFitParameters,
) -> list[float]:
    if len(cuts) != count + 1 or count <= 1:
        return cuts
    widths = np.diff(np.array(cuts, dtype=np.float64))
    if widths.size != count or np.any(widths <= 1):
        return cuts
    width_cv = float(widths.std() / max(1.0, widths.mean()))
    target = float(np.median(widths))
    if pitch is not None and config.geometry_pitch_min_ratio <= target / max(1.0, float(pitch)) <= config.geometry_pitch_max_ratio:
        target = float(pitch)
    if width_cv <= config.geometry_noop_width_cv:
        return cuts

    centers = (np.array(cuts[:-1], dtype=np.float64) + np.array(cuts[1:], dtype=np.float64)) / 2.0
    starts = centers - (np.arange(count, dtype=np.float64) + 0.5) * target
    start = float(np.median(starts))
    start = max(float(outer.left), min(float(outer.right) - target * count, start))
    fitted = [start + target * i for i in range(count + 1)]
    outer_tolerance = clamp_float(
        target * config.geometry_outer_tolerance_ratio,
        config.geometry_outer_tolerance_min,
        config.geometry_outer_tolerance_max,
    )
    if fitted[0] < outer.left - outer_tolerance or fitted[-1] > outer.right + outer_tolerance:
        return cuts
    if len(fitted) != len(cuts) or any(b <= a for a, b in zip(fitted[:-1], fitted[1:])):
        return cuts
    return fitted


def frame_edge_weight(gap: Gap) -> float:
    if gap.width <= 0:
        return 0.0
    if is_edge_pair_gap_method(gap.method):
        return max(0.0, min(1.8, gap.score)) * 1.20
    if is_detected_gap_method(gap.method):
        return max(0.0, min(1.5, gap.score))
    return 0.0


def relative_ranges_from_gaps(outer: Box, gaps: list[Gap], count: int) -> list[tuple[float, float]]:
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
        weight = frame_edge_weight(gap)
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

    base_ranges = relative_ranges_from_gaps(outer, gaps, count)
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
    origin: float = 0.0,
    pitch: float | None = None,
    frame_fit: FrameFitParameters | None = None,
) -> tuple[list[Box], dict[str, Any]]:
    if frame_fit is None:
        raise ValueError("frame_fit config is required")
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
        apply_geometry_fit=config.geometry_fallback,
        geometry_config=config,
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
        "geometry_fallback": bool(config.geometry_fallback),
        "min_edge_samples": int(config.min_edge_samples),
        "nominal_min_ratio": float(config.nominal_min_ratio),
        "nominal_max_ratio": float(config.nominal_max_ratio),
        "inlier_tolerance_ratio": float(config.inlier_tolerance_ratio),
        "min_inlier_tolerance_px": float(config.min_inlier_tolerance_px),
        "geometry_pitch_min_ratio": float(config.geometry_pitch_min_ratio),
        "geometry_pitch_max_ratio": float(config.geometry_pitch_max_ratio),
        "geometry_noop_width_cv": float(config.geometry_noop_width_cv),
        "geometry_outer_tolerance_ratio": float(config.geometry_outer_tolerance_ratio),
        "geometry_outer_tolerance_min": float(config.geometry_outer_tolerance_min),
        "geometry_outer_tolerance_max": float(config.geometry_outer_tolerance_max),
        "edge_candidate_weight_with_edges": float(config.edge_candidate_weight_with_edges),
        "edge_candidate_weight_without_edges": float(config.edge_candidate_weight_without_edges),
        "edge_adjust_tolerance_ratio": float(config.edge_adjust_tolerance_ratio),
        "edge_adjust_tolerance_min": float(config.edge_adjust_tolerance_min),
        "edge_adjust_tolerance_max": float(config.edge_adjust_tolerance_max),
    }
    if fitted_boxes is not None:
        return fitted_boxes, detail
    detail.setdefault("method", "geometry_fallback" if config.geometry_fallback else "raw_gaps")
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
