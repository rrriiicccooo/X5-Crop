from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

import numpy as np

from ....domain import Box, Detection
from ....formats import CONTENT_ASPECTS_HORIZONTAL, FormatSpec
from ....geometry.boxes import original_box_to_work
from ....policies.registry import get_detection_policy
from ....policies.runtime_policy import DetectionPolicy
from ....runtime import AnalysisCache
from ....runtime_config import RuntimeConfig
from ....utils import clamp_int
from ...evidence.outer_alignment import outer_content_alignment_detail


def corrected_outer_for_short_axis_aspect(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    cache: AnalysisCache,
    policy: Optional[DetectionPolicy] = None,
) -> Optional[Box]:
    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    short_axis_retry = policy.outer.short_axis_aspect_retry
    if not short_axis_retry.enabled:
        return None
    if detection.strip_mode != "full" or detection.count != fmt.default_count:
        return None
    candidate = detection.detail.get("candidate_assessment", {})
    if not isinstance(candidate, dict) or candidate.get("source") != "separator":
        return None
    hard_detail = candidate.get("separator_hard_evidence", {})
    if not isinstance(hard_detail, dict) or not bool(hard_detail.get("ok", False)):
        return None
    if str(content_detail.get("support", "")) != "aspect_conflict":
        return None
    max_aspect_error = content_detail.get("max_aspect_error")
    if max_aspect_error is None or float(max_aspect_error) < short_axis_retry.min_error:
        return None

    source_h, source_w = gray.shape
    work_h, work_w = cache.gray_work.shape
    outer = original_box_to_work(detection.outer, detection.layout, source_w, source_h).clamp(work_w, work_h)
    if not outer.valid():
        return None
    pitch = float(outer.width) / float(max(1, detection.count))
    target_aspect = max(0.01, float(short_axis_retry.target_aspect))
    target_height = pitch / target_aspect
    if target_height <= float(outer.height):
        return None

    margin = clamp_int(
        pitch * short_axis_retry.margin_ratio,
        short_axis_retry.margin_min,
        short_axis_retry.margin_max,
    )
    target_height = min(float(work_h), target_height + float(margin * 2))
    center = (float(outer.top) + float(outer.bottom)) * 0.5
    top = int(round(center - target_height * 0.5))
    bottom = int(round(center + target_height * 0.5))
    if top < 0:
        bottom -= top
        top = 0
    if bottom > work_h:
        top -= bottom - work_h
        bottom = work_h
    top = max(0, top)
    bottom = min(work_h, bottom)
    corrected = Box(outer.left, top, outer.right, bottom)
    if not corrected.valid() or corrected == outer:
        return None
    if corrected.height <= outer.height:
        return None
    return corrected


def retry_with_short_axis_aspect_outer(
    gray: np.ndarray,
    config: RuntimeConfig,
    fmt: FormatSpec,
    detection: Detection,
    content_detail: dict[str, Any],
    cache: AnalysisCache,
) -> Optional[Detection]:
    from ...candidate.build import build_detection_for_outer
    from ...candidate.candidate_assessment import apply_candidate_assessment_policy
    from ...evidence.content_evidence import content_evidence_detail

    policy = get_detection_policy(fmt.name, detection.strip_mode)
    corrected_outer = corrected_outer_for_short_axis_aspect(
        gray,
        config,
        fmt,
        detection,
        content_detail,
        cache,
        policy=policy,
    )
    if corrected_outer is None:
        return None
    retried = build_detection_for_outer(
        gray,
        config,
        fmt,
        detection.count,
        detection.strip_mode,
        corrected_outer,
        float(detection.detail.get("offset_fraction", 0.0)),
        "short_axis_aspect_outer",
        "short_axis_retry",
        cache=cache,
        allow_outer_refine=False,
        policy=policy,
    )
    retried = apply_candidate_assessment_policy(gray, retried, config, fmt, "separator", cache, policy=policy)
    retry_content = content_evidence_detail(gray, retried, cache, policy.content)
    retry_alignment = outer_content_alignment_detail(gray, retried, cache, policy=policy)
    retried.detail["content_evidence"] = retry_content
    retried.detail["outer_content_alignment"] = retry_alignment
    retried.detail["outer_correction"] = {
        "used": True,
        "source_reason": "short_axis_aspect_conflict",
        "original_outer_work_box": detection.detail.get("work_outer"),
        "corrected_outer_work_box": asdict(corrected_outer),
        "retry_alignment": retry_alignment,
        "retry_content_support": retry_content.get("support"),
    }
    return retried
