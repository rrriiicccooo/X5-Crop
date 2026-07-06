from __future__ import annotations

import copy
from typing import Any, Optional

import numpy as np

from ...domain import Box, Detection
from ...formats import CONTENT_ASPECTS_HORIZONTAL
from ...geometry.boxes import original_box_to_work
from ...policies.runtime.content import ContentEvidencePolicy, ContentPolicy
from ...cache import AnalysisCache
from .evidence_cache_keys import content_detail_cache_key
from .content_signal import (
    CACHED_CONTENT_SIGNAL_COMPOSITE,
    content_evidence_threshold,
    content_policy_cache_key,
    content_signal_from_gray,
    resolve_content_policy,
)


def expected_content_aspect(format_name: str, layout: str) -> Optional[float]:
    aspect = CONTENT_ASPECTS_HORIZONTAL.get(format_name)
    if aspect is None:
        return None
    if layout == "vertical":
        return 1.0 / aspect
    return aspect


def content_frame_support_detail(
    evidence: np.ndarray,
    outer: Box,
    frames: list[Box],
    canvas_shape: tuple[int, int],
    *,
    threshold: float,
    expected_aspect: Optional[float],
    evidence_params: ContentEvidencePolicy,
    composite: str,
) -> dict[str, Any]:
    canvas_h, canvas_w = canvas_shape
    frame_scores: list[dict[str, Any]] = []
    means: list[float] = []
    coverages: list[float] = []
    aspect_errors: list[float] = []

    for index, frame in enumerate(frames, start=1):
        absolute_box = frame.clamp(canvas_w, canvas_h)
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
        return {
            "used": False,
            "evidence_role": "content_support_assessment",
            "reason": "no_valid_frames",
        }

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
        "evidence_role": "content_support_assessment",
        "support": support,
        "composite": composite,
        "threshold": threshold,
        "median_mean": median_mean,
        "min_mean": min_mean,
        "median_coverage": median_coverage,
        "expected_aspect": expected_aspect,
        "max_aspect_error": max_aspect_error,
        "frame_scores": frame_scores,
    }


def content_evidence_detail(
    gray: np.ndarray,
    detection: Detection,
    cache: Optional[AnalysisCache] = None,
    content_policy: Optional[ContentPolicy] = None,
) -> dict[str, Any]:
    content_policy = resolve_content_policy(detection.film_format, detection.strip_mode, content_policy)
    if cache is not None and cache.layout == detection.layout:
        return content_evidence_detail_from_cache(gray, detection, cache, content_policy)
    evidence_params = content_policy.evidence

    outer = detection.outer.clamp(gray.shape[1], gray.shape[0])
    if not outer.valid():
        return {"used": False, "reason": "invalid_outer"}

    source_crop = gray[outer.top:outer.bottom, outer.left:outer.right]
    if source_crop.size == 0:
        return {"used": False, "reason": "empty_outer"}

    signal = content_signal_from_gray(source_crop)
    threshold = content_evidence_threshold(signal.evidence_float, evidence_params)
    expected_aspect = expected_content_aspect(detection.film_format, detection.layout)
    return content_frame_support_detail(
        signal.evidence_float,
        outer,
        detection.frames,
        gray.shape,
        threshold=threshold,
        expected_aspect=expected_aspect,
        evidence_params=evidence_params,
        composite=signal.composite,
    )


def content_evidence_detail_from_cache(
    gray: np.ndarray,
    detection: Detection,
    cache: AnalysisCache,
    content_policy: Optional[ContentPolicy] = None,
) -> dict[str, Any]:
    content_policy = resolve_content_policy(detection.film_format, detection.strip_mode, content_policy)
    evidence_params = content_policy.evidence
    source_h, source_w = gray.shape
    detail_key = content_detail_cache_key(detection, source_w, source_h, content_policy_cache_key(content_policy))
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

    threshold = content_evidence_threshold(evidence, evidence_params)
    expected_aspect = CONTENT_ASPECTS_HORIZONTAL.get(detection.film_format)
    frames_work = [
        original_box_to_work(frame, detection.layout, source_w, source_h)
        for frame in detection.frames
    ]
    detail = content_frame_support_detail(
        evidence,
        outer,
        frames_work,
        cache.gray_work.shape,
        threshold=threshold,
        expected_aspect=expected_aspect,
        evidence_params=evidence_params,
        composite=CACHED_CONTENT_SIGNAL_COMPOSITE,
    )
    if bool(detail.get("used", False)):
        cache.content_evidence_details[detail_key] = copy.deepcopy(detail)
    return detail
