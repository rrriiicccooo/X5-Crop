from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Optional

import numpy as np

from ....constants import (
    GAP_DETECTED,
    GAP_EDGE_PAIR,
    GAP_ENHANCED_DETECTED,
    GAP_EQUAL,
    GAP_GRID,
    HARD_GAP_METHODS,
)
from ....domain import Box, Detection, Gap
from ...evidence.separator_summary import separator_gate_detail_summary
from ....formats import FormatSpec
from ....policies.registry import get_detection_policy
from ....policies.runtime.content import ContentPolicy
from ....policies.runtime.policy import DetectionPolicy
from ....policies.runtime.separator import SeparatorGeometrySupportModePolicy
from ....policies.separator_gate_profiles import SEPARATOR_GATE_PROFILE_MIN_HARD_WITH_EQUAL_CAP
from ....utils import sampled_percentile


@dataclass(frozen=True)
class GapMethodEvidenceSummary:
    direct_hard_gaps: int
    enhanced_hard_gaps: int
    hard_separator_gaps: int
    grid_model_gaps: int
    equal_model_gaps: int
    separator_support_gaps: int
    reliable_support_gaps: int


def gap_method_evidence_summary(
    gaps: list[Gap],
    reliable_min_score: float,
) -> GapMethodEvidenceSummary:
    direct_hard_gaps = sum(1 for gap in gaps if gap.method in {GAP_DETECTED, GAP_EDGE_PAIR})
    enhanced_hard_gaps = sum(1 for gap in gaps if gap.method == GAP_ENHANCED_DETECTED)
    hard_separator_gaps = direct_hard_gaps + enhanced_hard_gaps
    grid_model_gaps = sum(1 for gap in gaps if gap.method == GAP_GRID)
    equal_model_gaps = sum(1 for gap in gaps if gap.method == GAP_EQUAL)
    separator_support_gaps = hard_separator_gaps + grid_model_gaps
    reliable_support_gaps = sum(
        1
        for gap in gaps
        if gap.method in HARD_GAP_METHODS.union({GAP_GRID})
        and gap.score >= reliable_min_score
    )
    return GapMethodEvidenceSummary(
        direct_hard_gaps=direct_hard_gaps,
        enhanced_hard_gaps=enhanced_hard_gaps,
        hard_separator_gaps=hard_separator_gaps,
        grid_model_gaps=grid_model_gaps,
        equal_model_gaps=equal_model_gaps,
        separator_support_gaps=separator_support_gaps,
        reliable_support_gaps=reliable_support_gaps,
    )


def content_support_score(
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
    support_gate = {
        "ok": content_policy.support_gate_ok,
        "weak": content_policy.support_gate_weak,
        "low_content": content_policy.support_gate_low_content,
        "aspect_conflict": content_policy.support_gate_aspect_conflict,
    }.get(support, content_policy.support_gate_unknown)
    return max(
        0.0,
        min(
            1.0,
            (
                content_policy.support_coverage_weight * coverage_score
                + content_policy.support_mean_weight * mean_score
                + content_policy.support_aspect_weight * aspect_score
            )
            * support_gate,
        ),
    )


def geometry_support_score(
    detection: Detection,
    content_detail: dict[str, Any],
    policy: Optional[DetectionPolicy] = None,
) -> float:
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    geometry_policy = policy.scoring.geometry_support
    width_cv = float(detection.detail.get("width_cv", 0.0))
    if width_cv <= 0.0:
        widths = np.array([box.width for box in detection.frames if box.valid()], dtype=np.float64)
        width_cv = float(widths.std() / max(1.0, widths.mean())) if widths.size else 1.0
    width_score = max(0.0, min(1.0, 1.0 - width_cv / geometry_policy.width_cv_norm))
    outer_area = float(detection.detail.get("outer_area_ratio", 0.70))
    outer_score = 1.0 if geometry_policy.outer_min_area <= outer_area <= geometry_policy.outer_max_area else geometry_policy.outer_uncertain_score
    aspect_error = content_detail.get("max_aspect_error")
    aspect_score = geometry_policy.no_aspect_score if aspect_error is None else max(0.0, min(1.0, 1.0 - float(aspect_error) / geometry_policy.aspect_norm))
    count_score = 1.0 if len(detection.frames) == detection.count else 0.0
    return max(
        0.0,
        min(
            1.0,
            geometry_policy.width_weight * width_score
            + geometry_policy.outer_weight * outer_score
            + geometry_policy.aspect_weight * aspect_score
            + geometry_policy.count_weight * count_score,
        ),
    )


def separator_support_score(
    detection: Detection,
    hard_detail: dict[str, Any],
    policy: Optional[DetectionPolicy] = None,
) -> float:
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    support_policy = policy.scoring.separator_support
    evidence = separator_gate_detail_summary(hard_detail)
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


def detail_float(detail: dict[str, Any], key: str, default: float) -> float:
    value = detail.get(key, None)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def hard_full_calibration_floor_applies(
    candidate: Detection,
    hard_detail: dict[str, Any],
    fmt: FormatSpec,
    source: str,
    policy: Optional[DetectionPolicy] = None,
) -> bool:
    policy = policy or get_detection_policy(fmt.name, candidate.strip_mode)
    base_score = policy.scoring.base_detection
    evidence = separator_gate_detail_summary(hard_detail)
    width_cv = detail_float(candidate.detail, "width_cv", 1.0)
    return (
        source == "separator"
        and policy.scoring.hard_full_confidence_floor > 0.0
        and candidate.strip_mode == "full"
        and candidate.count == fmt.default_count
        and len(candidate.frames) == candidate.count
        and evidence.expected_gaps > 0
        and evidence.hard_separator_gaps >= evidence.expected_gaps
        and evidence.equal_model_gaps == 0
        and width_cv <= base_score.full_width_cv
    )


def separator_geometry_support_applies(
    candidate: Detection,
    hard_detail: dict[str, Any],
    fmt: FormatSpec,
    source: str,
    support: str,
    joint_score: float,
    mode_policy: SeparatorGeometrySupportModePolicy,
) -> bool:
    evidence = separator_gate_detail_summary(hard_detail)
    width_cv = detail_float(candidate.detail, "width_cv", 1.0)
    outer_area = detail_float(candidate.detail, "outer_area_ratio", 1.0)
    min_hard = int(math.ceil(evidence.expected_gaps * mode_policy.min_hard_ratio))
    support_gap_count = evidence.hard_separator_gaps + (
        evidence.grid_model_gaps if mode_policy.allow_grid else 0
    )
    return (
        mode_policy.enabled
        and source == "separator"
        and candidate.strip_mode == "full"
        and candidate.count == fmt.default_count
        and len(candidate.frames) == candidate.count
        and evidence.expected_gaps > 0
        and evidence.hard_separator_gaps >= min_hard
        and support_gap_count >= evidence.expected_gaps
        and evidence.equal_model_gaps <= mode_policy.max_equal_gaps
        and width_cv <= mode_policy.max_width_cv
        and support == mode_policy.required_content_support
        and joint_score >= mode_policy.min_joint_score
        and outer_area <= mode_policy.max_outer_area_ratio
    )


def score_detection(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    boxes: list[Box],
    count: int,
    fmt: FormatSpec,
    strip_mode: str,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[float, list[str], dict[str, Any]]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    base_score = policy.scoring.base_detection
    separator_gate = policy.separator.gate
    expected_gaps = max(0, count - 1)
    gap_evidence = gap_method_evidence_summary(
        gaps,
        policy.separator.robust_grid.reliable_min_score,
    )
    widths = np.array([box.width for box in boxes if box.valid()], dtype=np.float64)
    width_cv = float(widths.std() / max(1.0, widths.mean())) if widths.size else 1.0
    outer_area = float(outer.width * outer.height) / max(1.0, float(gray_work.shape[0] * gray_work.shape[1]))
    p01, p50, p99 = sampled_percentile(gray_work, [1, 50, 99])
    contrast = float(p99 - p01)

    gap_conf = 1.0 if expected_gaps == 0 else gap_evidence.separator_support_gaps / float(expected_gaps)
    width_conf = max(0.0, min(1.0, 1.0 - width_cv / base_score.width_cv_norm))
    outer_conf = 1.0 if base_score.outer_min_area <= outer_area <= base_score.outer_max_area else base_score.outer_uncertain_confidence
    contrast_conf = 1.0 if contrast >= base_score.contrast_min else max(base_score.contrast_floor, contrast / base_score.contrast_min)
    uses_min_hard_equal_cap = (
        separator_gate.profile == SEPARATOR_GATE_PROFILE_MIN_HARD_WITH_EQUAL_CAP
    )
    geometry_support_allowed = separator_gate.allow_geometry_support and bool(policy.separator.geometry_support_modes)
    enough_profile_separator_evidence = (
        not uses_min_hard_equal_cap
        or expected_gaps <= 1
        or (
            gap_evidence.hard_separator_gaps >= separator_gate.score_min_hard_gaps
            and gap_evidence.equal_model_gaps
            <= max(separator_gate.score_max_equal_gaps_floor, expected_gaps // 2)
        )
        or (
            gap_evidence.direct_hard_gaps >= 1
            and gap_evidence.enhanced_hard_gaps >= 2
            and gap_evidence.equal_model_gaps
            <= max(separator_gate.score_max_equal_gaps_floor, expected_gaps // 2)
        )
    )

    confidence = (
        base_score.gap_weight * gap_conf
        + base_score.width_weight * width_conf
        + base_score.outer_weight * outer_conf
        + base_score.contrast_weight * contrast_conf
    )

    full_geometry_ok = (
        strip_mode == "full"
        and count == fmt.default_count
        and len(boxes) == count
        and (
            width_cv <= base_score.full_width_cv
            or (
                uses_min_hard_equal_cap
                and separator_gate.allow_full_detected_geometry
                and gap_evidence.separator_support_gaps == expected_gaps
            )
        )
        and base_score.full_outer_min_area <= outer_area <= base_score.outer_max_area
        and outer_area <= base_score.outer_too_large
        and enough_profile_separator_evidence
        and (
            uses_min_hard_equal_cap
            or geometry_support_allowed
            or (
                gap_evidence.reliable_support_gaps >= expected_gaps
                and gap_evidence.equal_model_gaps == 0
            )
        )
    )
    if full_geometry_ok:
        geometry_floor = (
            base_score.geometry_floor_high
            if (uses_min_hard_equal_cap or geometry_support_allowed) and width_cv <= base_score.geometry_floor_tight_cv
            else base_score.geometry_floor_low
        )
        confidence = max(confidence, geometry_floor)
    reasons: list[str] = []
    if expected_gaps and gap_evidence.separator_support_gaps < max(1, expected_gaps // 2) and not full_geometry_ok:
        reasons.append("weak_separators")
    if gap_evidence.equal_model_gaps >= max(2, expected_gaps // 2 + 1) and not full_geometry_ok:
        reasons.append("mostly_equal_split")
    if (
        uses_min_hard_equal_cap
        and expected_gaps >= 3
        and gap_evidence.hard_separator_gaps < 2
        and not (
            gap_evidence.direct_hard_gaps >= 1
            and gap_evidence.enhanced_hard_gaps >= 2
        )
    ):
        reasons.append("too_few_detected_separators")
    if width_cv > base_score.unstable_width_cv:
        reasons.append("unstable_frame_width")
    if not (base_score.outer_min_area <= outer_area <= base_score.outer_max_area):
        reasons.append("outer_box_uncertain")
    if outer_area > base_score.outer_too_large:
        reasons.append("outer_box_too_large")
    if fmt.family == "120" and gap_evidence.separator_support_gaps < expected_gaps:
        reasons.append(base_score.family_separator_uncertain_reason)
    if contrast < base_score.contrast_min:
        reasons.append("low_contrast")
    if len(boxes) != count:
        reasons.append("frame_count_mismatch")
    if confidence < base_score.low_confidence_floor and not reasons:
        reasons.append("low_confidence")

    if strip_mode == "partial" and count < fmt.default_count:
        if count <= 1:
            confidence = min(confidence, base_score.partial_one_cap)
            reasons.append("partial_too_ambiguous")
        elif count <= 2 and fmt.default_count >= 6:
            confidence = min(confidence, base_score.partial_two_35mm_cap)
            reasons.append("partial_too_ambiguous")
        else:
            confidence = min(confidence, base_score.partial_general_cap)
        reasons.append("partial_strip_count_candidate")

    if uses_min_hard_equal_cap and expected_gaps >= 3:
        if gap_evidence.hard_separator_gaps < 1:
            confidence = min(confidence, separator_gate.low_hard_confidence_cap)
        elif gap_evidence.hard_separator_gaps < 2 and gap_evidence.enhanced_hard_gaps < 2:
            confidence = min(confidence, separator_gate.low_hard_confidence_cap)
        elif gap_evidence.equal_model_gaps >= max(2, expected_gaps // 2 + 1):
            confidence = min(confidence, separator_gate.mostly_equal_confidence_cap)
    if outer_area > base_score.outer_too_large:
        confidence = min(confidence, base_score.outer_too_large_cap)

    detail = {
        "detected_gaps": gap_evidence.separator_support_gaps,
        "actual_detected_gaps": gap_evidence.direct_hard_gaps,
        "enhanced_detected_gaps": gap_evidence.enhanced_hard_gaps,
        "grid_gaps": gap_evidence.grid_model_gaps,
        "reliable_gaps": gap_evidence.reliable_support_gaps,
        "equal_gaps": gap_evidence.equal_model_gaps,
        "width_cv": width_cv,
        "outer_area_ratio": outer_area,
        "image_quality": {
            "p01": float(p01),
            "p50": float(p50),
            "p99": float(p99),
            "range_1_99": contrast,
        },
        "contrast_1_99": contrast,
        "full_geometry_ok": full_geometry_ok,
        "separator_gate_profile": separator_gate.profile,
    }
    return float(max(0.0, min(1.0, confidence))), sorted(set(reasons)), detail

__all__ = [
    "GapMethodEvidenceSummary",
    "content_support_score",
    "detail_float",
    "gap_method_evidence_summary",
    "geometry_support_score",
    "hard_full_calibration_floor_applies",
    "separator_geometry_support_applies",
    "separator_support_score",
    "score_detection",
]
