from __future__ import annotations

from typing import Any, Optional

from ....domain import Detection
from ...evidence.photo_width import photo_width_cv_from_detail
from ...evidence.separator_summary import separator_support_detail_summary
from ....policies.registry import get_detection_policy
from ....policies.runtime.content import ContentPolicy
from ....policies.runtime.policy import DetectionPolicy

def content_quality_score(
    detail: dict[str, Any],
    format_name: str,
    content_policy: Optional[ContentPolicy] = None,
) -> float:
    if not bool(detail.get("used", False)):
        return 0.0
    if content_policy is None:
        content_policy = get_detection_policy(format_name, "full").content
    mean_score = min(1.0, float(detail.get("median_mean", 0.0)) / content_policy.support_mean_norm)
    coverage_score = min(1.0, float(detail.get("median_coverage", 0.0)) / content_policy.support_coverage_norm)
    aspect_error = detail.get("max_aspect_error")
    aspect_score = 0.75 if aspect_error is None else max(0.0, min(1.0, 1.0 - float(aspect_error) / content_policy.support_aspect_norm))
    support = str(detail.get("support", ""))
    support_score = {
        "ok": content_policy.support_score_ok,
        "weak": content_policy.support_score_weak,
        "low_content": content_policy.support_score_low_content,
        "aspect_conflict": content_policy.support_score_aspect_conflict,
    }.get(support, content_policy.support_score_unknown)
    return max(
        0.0,
        min(
            1.0,
            (
                content_policy.support_coverage_weight * coverage_score
                + content_policy.support_mean_weight * mean_score
                + content_policy.support_aspect_weight * aspect_score
            )
            * support_score,
        ),
    )


def content_support_score(
    detail: dict[str, Any],
) -> float:
    if not bool(detail.get("used", False)):
        return 0.0
    containment_ok = bool(detail.get("content_containment_ok", False))
    content_integrity_failed = bool(detail.get("content_integrity_failed", True))
    return 1.0 if containment_ok and not content_integrity_failed else 0.0


def geometry_support_score(
    detection: Detection,
    content_detail: dict[str, Any],
    policy: Optional[DetectionPolicy] = None,
) -> float:
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
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
    detection: Detection,
    hard_detail: dict[str, Any],
    policy: Optional[DetectionPolicy] = None,
) -> float:
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    support_policy = policy.scoring.separator_support
    evidence = separator_support_detail_summary(hard_detail)
    if evidence.expected_gaps == 0:
        return (
            1.0
            if detection.confidence >= support_policy.no_expected_confidence_threshold
            else min(support_policy.no_expected_confidence_cap, detection.confidence)
        )
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
    scoring_policy = policy.scoring
    source_bias = scoring_policy.separator_source_bias if source == "separator" else 0.0
    joint_score = (
        scoring_policy.geometry_weight * geometry_score
        + scoring_policy.content_weight * content_score
        + scoring_policy.separator_weight * separator_score
        + source_bias
    )
    return max(0.0, min(1.0, joint_score))


__all__ = [
    "content_quality_score",
    "content_support_score",
    "geometry_support_score",
    "joint_support_score",
    "separator_support_score",
]
