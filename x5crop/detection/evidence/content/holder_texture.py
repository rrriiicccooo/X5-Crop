from __future__ import annotations

from typing import Any

import numpy as np

from ....policies.parameters.content import ContentEvidenceParameters


def _score_float(item: dict[str, Any], key: str) -> float:
    try:
        return float(item.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def holder_texture_evidence_detail(
    frame_scores: list[dict[str, Any]],
    *,
    content_indexes: list[int],
    empty_indexes: list[int],
    evidence_policy: ContentEvidenceParameters,
) -> dict[str, Any]:
    score_by_index = {
        int(item.get("index", 0)): item
        for item in frame_scores
        if isinstance(item, dict)
    }
    content_scores = [
        score_by_index[index]
        for index in content_indexes
        if index in score_by_index
    ]
    holder_scores = [
        score_by_index[index]
        for index in empty_indexes
        if index in score_by_index
    ]
    if not holder_scores:
        return {
            "used": False,
            "reason": "no_empty_holder_frames",
            "evidence_role": "holder_texture_guidance",
        }
    holder_means = [_score_float(item, "mean") for item in holder_scores]
    holder_coverages = [_score_float(item, "coverage") for item in holder_scores]
    content_means = [_score_float(item, "mean") for item in content_scores]
    content_coverages = [_score_float(item, "coverage") for item in content_scores]
    holder_texture_low = (
        max(holder_means, default=0.0) < float(evidence_policy.present_mean_min)
        and max(holder_coverages, default=0.0) < float(evidence_policy.present_coverage_min)
    )
    median_holder_mean = float(np.median(np.array(holder_means, dtype=np.float32)))
    median_holder_coverage = float(np.median(np.array(holder_coverages, dtype=np.float32)))
    median_content_mean = (
        float(np.median(np.array(content_means, dtype=np.float32)))
        if content_means
        else None
    )
    median_content_coverage = (
        float(np.median(np.array(content_coverages, dtype=np.float32)))
        if content_coverages
        else None
    )
    content_holder_contrast = (
        None
        if median_content_mean is None
        else float(median_content_mean - median_holder_mean)
    )
    coverage_contrast = (
        None
        if median_content_coverage is None
        else float(median_content_coverage - median_holder_coverage)
    )
    return {
        "used": True,
        "evidence_role": "holder_texture_guidance",
        "physical_rule": "holder_area_is_low_texture_low_content",
        "gate_role": "guidance_not_candidate_pass",
        "holder_texture_low": bool(holder_texture_low),
        "holder_frame_indexes": list(empty_indexes),
        "content_frame_indexes": list(content_indexes),
        "median_holder_mean": median_holder_mean,
        "median_holder_coverage": median_holder_coverage,
        "median_content_mean": median_content_mean,
        "median_content_coverage": median_content_coverage,
        "content_holder_contrast": content_holder_contrast,
        "content_holder_coverage_contrast": coverage_contrast,
    }
