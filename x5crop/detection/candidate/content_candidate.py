from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import numpy as np

from ...runtime_config import RuntimeConfig
from ...constants import ANALYSIS_SOURCE_CONTENT_PRIMARY
from ...domain import Box, Detection, Gap
from ...formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ...geometry.boxes import map_work_box
from ...geometry.layout import work_gray
from ...image.evidence import make_content_evidence_gray
from ...policies.runtime_content import ContentPolicy
from ...runtime import AnalysisCache
from ...utils import box_from_dict
from ..evidence.content_evidence import _content_policy_for
from ..evidence.content_profile import content_mask_outer_detail, content_profile_runs, select_content_runs


def content_detection_for_count(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    count: int,
    strip_mode: str,
    offset_fraction: float = 0.0,
    cache: Optional[AnalysisCache] = None,
    content_policy: Optional[ContentPolicy] = None,
) -> Optional[Detection]:
    gray_work = cache.gray_work if cache is not None and cache.layout == config.layout else work_gray(gray, config.layout)
    content_policy = _content_policy_for(fmt.name, strip_mode, content_policy)
    mask_policy = content_policy.mask
    candidate_policy = content_policy.candidate
    wh, ww = gray_work.shape
    if cache is not None and cache.layout == config.layout:
        evidence = cache.content_evidence_work
        evidence_float = cache.content_evidence_float_work
    else:
        evidence = make_content_evidence_gray(gray_work)
        evidence_float = evidence.astype(np.float32) / 255.0
    mask_detail = content_mask_outer_detail(evidence_float, gray_work.shape, fmt, cache, content_policy)
    mask_threshold = float(mask_detail["mask_threshold"])
    outer_raw = mask_detail.get("outer")
    outer = box_from_dict(outer_raw) if isinstance(outer_raw, dict) else None
    if (
        outer is None
        or outer.width < max(mask_policy.outer_min_width_px, int(ww * mask_policy.outer_min_width_ratio))
        or outer.height < max(mask_policy.outer_min_height_px, int(wh * mask_policy.outer_min_height_ratio))
    ):
        return None

    expected_aspect = CONTENT_ASPECTS_HORIZONTAL.get(fmt.name)
    if expected_aspect is None or expected_aspect <= 0:
        return None
    runs, run_detail = content_profile_runs(evidence, outer, count, fmt.name, cache, content_policy)
    selected_runs = select_content_runs(runs, count)

    frame_h = max(1.0, float(outer.height))
    expected_w = max(candidate_policy.expected_width_min_px, frame_h * expected_aspect)
    raw_boxes: list[Box] = []
    placement = "content_runs" if len(selected_runs) >= count else "content_grid_fallback"
    if placement == "content_runs":
        for start, end in selected_runs[:count]:
            center = (float(start) + float(end)) * 0.5
            left = int(round(center - expected_w * 0.5))
            right = int(round(center + expected_w * 0.5))
            raw_boxes.append(Box(left, outer.top, right, outer.bottom).clamp(ww, wh))
    else:
        if strip_mode == "partial" and count < fmt.default_count:
            pitch = max(expected_w, outer.width / float(max(1, fmt.default_count)))
            total_width = pitch * count
            origin = max(0.0, min(float(outer.width) - total_width, (float(outer.width) - total_width) * offset_fraction))
            start_x = outer.left + origin
        else:
            pitch = max(expected_w, outer.width / float(max(1, count)))
            total_width = pitch * count
            start_x = outer.left + max(0.0, (outer.width - total_width) * 0.5)
        for i in range(count):
            center = start_x + pitch * (i + 0.5)
            raw_boxes.append(Box(int(round(center - expected_w * 0.5)), outer.top, int(round(center + expected_w * 0.5)), outer.bottom).clamp(ww, wh))

    raw_boxes = [box for box in raw_boxes if box.valid()]
    if len(raw_boxes) != count:
        return None

    boxes_work = [box.expand(config.bleed_x, config.bleed_y, ww, wh) for box in raw_boxes]
    boxes = [map_work_box(box, config.layout, gray.shape[1], gray.shape[0]) for box in boxes_work]
    outer_original = map_work_box(outer, config.layout, gray.shape[1], gray.shape[0])
    gaps: list[Gap] = []
    for index in range(1, count):
        left_box = raw_boxes[index - 1]
        right_box = raw_boxes[index]
        center = (float(left_box.right) + float(right_box.left)) * 0.5 - float(outer.left)
        gaps.append(Gap(index, center, 0.0, "content", float(left_box.right - outer.left), float(right_box.left - outer.left)))

    means: list[float] = []
    coverages: list[float] = []
    for box in raw_boxes:
        crop = evidence_float[box.top:box.bottom, box.left:box.right]
        if crop.size:
            means.append(float(crop.mean()))
            coverages.append(float((crop >= mask_threshold).mean()))
    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    run_conf = min(1.0, len(selected_runs) / float(max(1, count)))
    coverage_conf = min(1.0, median_coverage / candidate_policy.coverage_norm)
    mean_conf = min(1.0, median_mean / candidate_policy.mean_norm)
    aspect_errors = [abs((box.width / max(1.0, float(box.height))) - expected_aspect) / expected_aspect for box in raw_boxes]
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else 1.0
    aspect_conf = max(0.0, min(1.0, 1.0 - max_aspect_error / candidate_policy.aspect_norm))
    confidence = (
        candidate_policy.coverage_weight * coverage_conf
        + candidate_policy.mean_weight * mean_conf
        + candidate_policy.run_weight * run_conf
        + candidate_policy.aspect_weight * aspect_conf
    )
    reasons: list[str] = []
    if placement != "content_runs":
        confidence = min(confidence, candidate_policy.grid_fallback_cap)
        reasons.append("content_grid_fallback")
    if len(runs) != count:
        confidence = min(confidence, candidate_policy.run_mismatch_cap)
        reasons.append("content_run_count_mismatch")
    if run_conf < 1.0:
        confidence = min(confidence, candidate_policy.runs_incomplete_cap)
        reasons.append("content_runs_incomplete")
    if median_coverage < candidate_policy.weak_coverage:
        confidence = min(confidence, candidate_policy.weak_coverage_cap)
        reasons.append("content_coverage_weak")
    if max_aspect_error > candidate_policy.aspect_uncertain:
        confidence = min(confidence, candidate_policy.aspect_uncertain_cap)
        reasons.append("content_aspect_uncertain")
    if strip_mode == "partial":
        reasons.append("partial_strip_count_candidate")
    if confidence < config.confidence_threshold and not reasons:
        reasons.append("content_confidence_low")

    detail = {
        "analysis_source": ANALYSIS_SOURCE_CONTENT_PRIMARY,
        "candidate_count": count,
        "offset_fraction": float(offset_fraction),
        "layout": config.layout,
        "outer_candidate": "content_evidence",
        "work_outer": asdict(outer),
        "content_primary": {
            "used": True,
            "placement": placement,
            "mask_threshold": mask_threshold,
            "mask_percentiles": mask_detail.get("mask_percentiles", {}),
            "expected_frame_aspect": expected_aspect,
            "expected_frame_width": expected_w,
            "median_mean": median_mean,
            "median_coverage": median_coverage,
            "run_conf": run_conf,
            "coverage_conf": coverage_conf,
            "mean_conf": mean_conf,
            "max_aspect_error": max_aspect_error,
            "raw_boxes": [asdict(box) for box in raw_boxes],
            **run_detail,
        },
        "gap_centers": [gap.center for gap in gaps],
        "gap_scores": [gap.score for gap in gaps],
        "gap_methods": [gap.method for gap in gaps],
    }
    return Detection(
        fmt.name,
        config.layout,
        strip_mode,
        count,
        outer_original,
        boxes,
        gaps,
        float(max(0.0, min(1.0, confidence))),
        sorted(set(reasons)),
        detail,
    )
