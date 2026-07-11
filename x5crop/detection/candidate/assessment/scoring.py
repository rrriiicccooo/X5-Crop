from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
from ...evidence.photo_width import photo_width_cv_from_detail
from ...evidence.separator_summary import separator_support_detail_summary
from ....policies.runtime.content import ContentPolicy
from ....policies.runtime.policy import DetectionPolicy

def content_quality_score(
    detail: dict[str, Any],
    content_policy: ContentPolicy,
) -> float:
    if not bool(detail.get("used", False)):
        return 0.0
    support_policy = content_policy.support
    mean_score = min(1.0, float(detail.get("median_mean", 0.0)) / support_policy.mean_norm)
    coverage_score = min(1.0, float(detail.get("median_coverage", 0.0)) / support_policy.coverage_norm)
    aspect_error = detail.get("max_aspect_error")
    aspect_score = (
        support_policy.missing_aspect_score
        if aspect_error is None
        else max(0.0, min(1.0, 1.0 - float(aspect_error) / support_policy.aspect_norm))
    )
    support = str(detail.get("support", ""))
    support_score = {
        "ok": support_policy.score_ok,
        "weak": support_policy.score_weak,
        "low_content": support_policy.score_low_content,
        "aspect_conflict": support_policy.score_aspect_conflict,
    }.get(support, support_policy.score_unknown)
    return max(
        0.0,
        min(
            1.0,
            (
                support_policy.coverage_weight * coverage_score
                + support_policy.mean_weight * mean_score
                + support_policy.aspect_weight * aspect_score
            )
            * support_score,
        ),
    )


def content_support_score(
    detail: dict[str, Any],
) -> float:
    if not bool(detail.get("used", False)):
        return 0.0
    return 1.0 if bool(detail.get("frame_content_support_available", False)) else 0.0


def geometry_support_score(
    detection: DetectionCandidate,
    content_detail: dict[str, Any],
    policy: DetectionPolicy,
) -> float:
    geometry_policy = policy.scoring.geometry_support
    photo_width_cv = photo_width_cv_from_detail(detection.detail)
    width_score = (
        max(0.0, min(1.0, 1.0 - photo_width_cv / geometry_policy.photo_width_cv_norm))
        if photo_width_cv is not None
        else None
    )
    aspect_error = content_detail.get("max_aspect_error")
    aspect_score = (
        max(0.0, min(1.0, 1.0 - float(aspect_error) / geometry_policy.aspect_norm))
        if aspect_error is not None
        else None
    )
    count_score = 1.0 if len(detection.frames) == detection.count else 0.0
    weighted_scores = [
        (geometry_policy.count_weight, count_score),
    ]
    if width_score is not None:
        weighted_scores.append((geometry_policy.photo_width_weight, width_score))
    if aspect_score is not None:
        weighted_scores.append((geometry_policy.aspect_weight, aspect_score))
    weight_total = max(1e-6, sum(weight for weight, _score in weighted_scores))
    return max(
        0.0,
        min(
            1.0,
            sum(weight * score for weight, score in weighted_scores) / weight_total,
        ),
    )


def separator_support_score(
    hard_detail: dict[str, Any],
    policy: DetectionPolicy,
) -> float:
    support_policy = policy.scoring.separator_support
    evidence = separator_support_detail_summary(hard_detail)
    if evidence.expected_gaps == 0:
        return 1.0
    hard_ratio = min(1.0, evidence.hard_separator_gaps / float(max(1, evidence.expected_gaps)))
    model_ratio = min(
        1.0,
        (
            evidence.hard_separator_gaps
            + support_policy.model_grid_credit * evidence.grid_model_gaps
            + support_policy.model_equal_credit * evidence.equal_model_gaps
        )
        / float(max(1, evidence.expected_gaps)),
    )
    return max(
        0.0,
        min(
            1.0,
            support_policy.hard_weight * hard_ratio
            + support_policy.model_weight * model_ratio,
        ),
    )


def joint_support_score(
    *,
    geometry_score: float,
    content_score: float,
    separator_score: float,
    source: str,
    policy: DetectionPolicy,
) -> float:
    calibration = policy.scoring.calibration
    source_bias = calibration.separator_source_bias if source == "separator" else 0.0
    joint_score = (
        calibration.geometry_weight * geometry_score
        + calibration.content_weight * content_score
        + calibration.separator_weight * separator_score
        + source_bias
    )
    return max(0.0, min(1.0, joint_score))
