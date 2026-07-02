from __future__ import annotations

import copy
from typing import Any, Optional

import numpy as np

from ...domain import Box, Detection
from ...formats import CONTENT_ASPECTS_HORIZONTAL
from ...geometry.boxes import original_box_to_work
from ...image.evidence import make_content_evidence_gray
from ...policies.registry import get_detection_policy
from ...policies.runtime_content import ContentPolicy
from ...runtime import AnalysisCache
from ...utils import sampled_percentile
from .evidence_cache_keys import content_detail_cache_key


def expected_content_aspect(format_name: str, layout: str) -> Optional[float]:
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(format_name)
    if aspect is None:
        return None
    if layout == "vertical":
        return 1.0 / aspect
    return aspect


def _content_policy_for(
    format_name: str,
    strip_mode: str = "full",
    content_policy: Optional[ContentPolicy] = None,
) -> ContentPolicy:
    return content_policy or get_detection_policy(format_name, strip_mode).content


def _content_policy_key(content_policy: ContentPolicy) -> tuple[Any, ...]:
    return (content_policy,)


def content_evidence_detail(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
    content_policy: Optional[ContentPolicy] = None,
) -> dict[str, Any]:
    content_policy = _content_policy_for(detection.film_format, detection.strip_mode, content_policy)
    if cache is not None and cache.layout == detection.layout:
        return content_evidence_detail_from_cache(gray, detection, cache, content_policy)
    evidence_params = content_policy.evidence

    outer = detection.outer.clamp(gray.shape[1], gray.shape[0])
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    source_crop = gray[outer.top:outer.bottom, outer.left:outer.right]
    if source_crop.size == 0:
        return {"used": False, "reason": "empty_outer"}

    evidence = make_content_evidence_gray(source_crop).astype(np.float32) / 255.0
    outer_p70 = float(sampled_percentile(evidence, [evidence_params.percentile])[0])
    threshold = max(
        evidence_params.threshold_min,
        min(evidence_params.threshold_max, outer_p70 * evidence_params.threshold_multiplier),
    )
    frame_scores: list[dict[str, Any]] = []
    means: list[float] = []
    coverages: list[float] = []
    aspect_errors: list[float] = []
    expected_aspect = expected_content_aspect(detection.film_format, detection.layout)

    for index, frame in enumerate(detection.frames, start=1):
        absolute_box = frame.clamp(gray.shape[1], gray.shape[0])
        box = Box(
            max(0, absolute_box.left - outer.left),
            max(0, absolute_box.top - outer.top),
            min(outer.width, absolute_box.right - outer.left),
            min(outer.height, absolute_box.bottom - outer.top),
        )
        if not box.valid():
            continue
        crop = evidence[box.top:box.bottom, box.left:box.right]
        if crop.size == 0:
            continue
        mean = float(crop.mean())
        coverage = float((crop >= threshold).mean())
        means.append(mean)
        coverages.append(coverage)
        actual_aspect = float(absolute_box.width) / max(1.0, float(absolute_box.height))
        aspect_error: Optional[float] = None
        if expected_aspect is not None and expected_aspect > 0:
            aspect_error = abs(actual_aspect - expected_aspect) / expected_aspect
            aspect_errors.append(float(aspect_error))
        frame_scores.append(
            {
                "index": index,
                "mean": mean,
                "coverage": coverage,
                "actual_aspect": actual_aspect,
                "expected_aspect": expected_aspect,
                "aspect_error": aspect_error,
            }
        )

    if not frame_scores:
        return {"used": False, "reason": "no_valid_frames"}

    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    min_mean = float(min(means)) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else None
    aspect_ok = max_aspect_error is None or max_aspect_error <= evidence_params.aspect_ok_max
    content_present = median_mean >= evidence_params.present_mean_min or median_coverage >= evidence_params.present_coverage_min
    support = "ok" if content_present and aspect_ok else "weak"
    if not aspect_ok:
        support = "aspect_conflict"
    elif not content_present:
        support = "low_content"

    return {
        "used": True,
        "support": support,
        "composite": "gradient+neighbor_texture+local_contrast+tonal_presence",
        "threshold": threshold,
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": expected_aspect,
        "max_aspect_error": max_aspect_error,
        "frame_scores": frame_scores,
    }


def content_evidence_detail_from_cache(
    gray: np.ndarray,
    detection: Detection,
    cache: AnalysisCache,
    content_policy: Optional[ContentPolicy] = None,
) -> dict[str, Any]:
    content_policy = _content_policy_for(detection.film_format, detection.strip_mode, content_policy)
    evidence_params = content_policy.evidence
    source_h, source_w = gray.shape
    detail_key = content_detail_cache_key(detection, source_w, source_h, _content_policy_key(content_policy))
    cached = cache.content_evidence_details.get(detail_key)
    if cached is not None:
        return copy.deepcopy(cached)
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    evidence = cache.content_evidence_float_work[outer.top:outer.bottom, outer.left:outer.right]
    if evidence.size == 0:
        return {"used": False, "reason": "empty_outer"}

    outer_p70 = float(sampled_percentile(evidence, [evidence_params.percentile])[0])
    threshold = max(
        evidence_params.threshold_min,
        min(evidence_params.threshold_max, outer_p70 * evidence_params.threshold_multiplier),
    )
    frame_scores: list[dict[str, Any]] = []
    means: list[float] = []
    coverages: list[float] = []
    aspect_errors: list[float] = []
    expected_aspect = CONTENT_ASPECTS_HORIZONTAL.get(detection.film_format)

    for index, frame in enumerate(detection.frames, start=1):
        absolute_box = original_box_to_work(frame, detection.layout, source_w, source_h).clamp(work_w, work_h)
        box = Box(
            max(0, absolute_box.left - outer.left),
            max(0, absolute_box.top - outer.top),
            min(outer.width, absolute_box.right - outer.left),
            min(outer.height, absolute_box.bottom - outer.top),
        )
        if not box.valid():
            continue
        crop = evidence[box.top:box.bottom, box.left:box.right]
        if crop.size == 0:
            continue
        mean = float(crop.mean())
        coverage = float((crop >= threshold).mean())
        means.append(mean)
        coverages.append(coverage)
        actual_aspect = float(absolute_box.width) / max(1.0, float(absolute_box.height))
        aspect_error: Optional[float] = None
        if expected_aspect is not None and expected_aspect > 0:
            aspect_error = abs(actual_aspect - expected_aspect) / expected_aspect
            aspect_errors.append(float(aspect_error))
        frame_scores.append(
            {
                "index": index,
                "mean": mean,
                "coverage": coverage,
                "actual_aspect": actual_aspect,
                "expected_aspect": expected_aspect,
                "aspect_error": aspect_error,
            }
        )

    if not frame_scores:
        return {"used": False, "reason": "no_valid_frames"}

    median_mean = float(np.median(np.array(means, dtype=np.float32))) if means else 0.0
    min_mean = float(min(means)) if means else 0.0
    median_coverage = float(np.median(np.array(coverages, dtype=np.float32))) if coverages else 0.0
    max_aspect_error = float(max(aspect_errors)) if aspect_errors else None
    aspect_ok = max_aspect_error is None or max_aspect_error <= evidence_params.aspect_ok_max
    content_present = median_mean >= evidence_params.present_mean_min or median_coverage >= evidence_params.present_coverage_min
    support = "ok" if content_present and aspect_ok else "weak"
    if not aspect_ok:
        support = "aspect_conflict"
    elif not content_present:
        support = "low_content"

    detail = {
        "used": True,
        "support": support,
        "composite": "cached_gradient+neighbor_texture+local_contrast+tonal_presence",
        "threshold": threshold,
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": expected_aspect,
        "max_aspect_error": max_aspect_error,
        "frame_scores": frame_scores,
    }
    cache.content_evidence_details[detail_key] = copy.deepcopy(detail)
    return detail
