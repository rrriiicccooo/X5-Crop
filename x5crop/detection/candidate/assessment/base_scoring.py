from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

import numpy as np

from ....domain import Box, Detection, Gap
from ....formats import FormatSpec
from ....geometry.frame_fit import frame_boxes_from_gaps
from ....geometry.gap_geometry import (
    gap_width_cv,
    photo_widths_from_gap_edges,
    separator_width_cv,
    separator_widths,
    width_cv as coefficient_of_variation,
)
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....policies.separator_gate_profiles import SEPARATOR_GATE_PROFILE_MIN_HARD_WITH_EQUAL_CAP
from ....runtime.config import RuntimeConfig
from ....utils import box_from_dict, gap_from_dict, sampled_percentile
from ...evidence.separator_summary import gap_method_evidence_summary


def _work_box_from_detail(detail: dict[str, Any]) -> Optional[Box]:
    value = detail.get("work_outer")
    if not isinstance(value, dict):
        return None
    try:
        return box_from_dict(value)
    except (KeyError, TypeError, ValueError):
        return None


def _work_frame_boxes_from_detail(detail: dict[str, Any]) -> list[Box]:
    value = detail.get("work_frame_boxes")
    if not isinstance(value, list):
        return []
    boxes: list[Box] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            box = box_from_dict(item)
        except (KeyError, TypeError, ValueError):
            continue
        if box.valid():
            boxes.append(box)
    return boxes


def _gaps_from_detail(detail: dict[str, Any], key: str) -> list[Gap]:
    value = detail.get(key)
    if not isinstance(value, list):
        return []
    gaps: list[Gap] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            gaps.append(gap_from_dict(item))
        except (KeyError, TypeError, ValueError):
            continue
    return gaps


def _detail_float(detail: dict[str, Any], key: str, default: float) -> float:
    value = detail.get(key)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _frame_box_widths(boxes: list[Box]) -> list[float]:
    return [float(box.width) for box in boxes if box.valid()]


def _candidate_width_metrics(
    gaps: list[Gap],
    boxes: list[Box],
    origin: float | None,
    pitch: float | None,
    count: int,
) -> dict[str, Any]:
    frame_widths = _frame_box_widths(boxes)
    frame_box_cv = coefficient_of_variation(frame_widths) if frame_widths else 1.0
    photo_widths = (
        photo_widths_from_gap_edges(gaps, float(origin), float(pitch), count)
        if origin is not None and pitch is not None and pitch > 0.0
        else None
    )
    photo_cv = (
        coefficient_of_variation(photo_widths)
        if photo_widths is not None
        else None
    )
    center_cv = (
        gap_width_cv(gaps, float(origin), float(pitch), count)
        if origin is not None and pitch is not None and pitch > 0.0
        else None
    )
    selected_cv = float(photo_cv) if photo_cv is not None else float(frame_box_cv)
    return {
        "width_cv": selected_cv,
        "width_cv_source": "photo_edges" if photo_cv is not None else "frame_boxes",
        "photo_width_cv": photo_cv,
        "frame_box_width_cv": float(frame_box_cv),
        "center_interval_width_cv": center_cv,
        "separator_width_cv": separator_width_cv(gaps),
        "photo_widths": photo_widths or [],
        "frame_box_widths": frame_widths,
        "separator_widths": separator_widths(gaps),
    }


def _outer_area_profile(outer_area: float, base_score) -> dict[str, Any]:
    if outer_area < base_score.outer_min_area:
        status = "below_profile"
    elif outer_area > base_score.outer_max_area:
        status = "above_profile"
    else:
        status = "ok"
    return {
        "status": status,
        "role": "diagnostic_until_final_alignment",
        "outer_area_ratio": float(outer_area),
        "min_outer_area_ratio": float(base_score.outer_min_area),
        "max_outer_area_ratio": float(base_score.outer_max_area),
        "too_large_ratio": float(base_score.outer_too_large),
    }


def base_detection_assessment(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[Gap],
    boxes: list[Box],
    count: int,
    fmt: FormatSpec,
    strip_mode: str,
    policy: Optional[DetectionPolicy] = None,
    origin: float | None = None,
    pitch: float | None = None,
) -> tuple[float, list[str], dict[str, Any]]:
    policy = policy or get_detection_policy(fmt.name, strip_mode)
    base_score = policy.scoring.base_detection
    separator_gate = policy.separator.gate
    expected_gaps = max(0, count - 1)
    gap_evidence = gap_method_evidence_summary(
        gaps,
        policy.separator.robust_grid.reliable_min_score,
    )
    width_metrics = _candidate_width_metrics(gaps, boxes, origin, pitch, count)
    width_cv = float(width_metrics["width_cv"])
    outer_area = float(outer.width * outer.height) / max(1.0, float(gray_work.shape[0] * gray_work.shape[1]))
    outer_area_profile = _outer_area_profile(outer_area, base_score)
    p01, p50, p99 = sampled_percentile(gray_work, [1, 50, 99])
    contrast = float(p99 - p01)

    gap_conf = 1.0 if expected_gaps == 0 else gap_evidence.separator_support_count / float(expected_gaps)
    width_conf = max(0.0, min(1.0, 1.0 - width_cv / base_score.width_cv_norm))
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
    )

    confidence_weight = max(
        1e-6,
        base_score.gap_weight + base_score.width_weight,
    )
    confidence = (
        base_score.gap_weight * gap_conf
        + base_score.width_weight * width_conf
    ) / confidence_weight

    full_geometry_ok = (
        strip_mode == "full"
        and count == fmt.default_count
        and len(boxes) == count
        and (
            width_cv <= base_score.full_width_cv
            or (
                uses_min_hard_equal_cap
                and separator_gate.allow_full_detected_geometry
                and gap_evidence.separator_support_count == expected_gaps
            )
        )
        and base_score.full_outer_min_area <= outer_area <= base_score.outer_max_area
        and outer_area <= base_score.outer_too_large
        and enough_profile_separator_evidence
        and (
            uses_min_hard_equal_cap
            or geometry_support_allowed
            or (
                gap_evidence.reliable_support_count >= expected_gaps
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
    if expected_gaps and gap_evidence.separator_support_count < max(1, expected_gaps // 2) and not full_geometry_ok:
        reasons.append("weak_separators")
    if gap_evidence.equal_model_gaps >= max(2, expected_gaps // 2 + 1) and not full_geometry_ok:
        reasons.append("mostly_equal_split")
    if (
        uses_min_hard_equal_cap
        and expected_gaps >= 3
        and gap_evidence.hard_separator_gaps < 2
    ):
        reasons.append("too_few_detected_separators")
    if width_cv > base_score.unstable_width_cv:
        reasons.append("photo_width_unstable")
    if fmt.family == "120" and gap_evidence.separator_support_count < expected_gaps:
        reasons.append(base_score.family_separator_uncertain_reason)
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
        elif gap_evidence.hard_separator_gaps < 2:
            confidence = min(confidence, separator_gate.low_hard_confidence_cap)
        elif gap_evidence.equal_model_gaps >= max(2, expected_gaps // 2 + 1):
            confidence = min(confidence, separator_gate.mostly_equal_confidence_cap)
    detail = {
        "detected_gaps": gap_evidence.separator_support_count,
        "separator_support_count": gap_evidence.separator_support_count,
        "actual_detected_gaps": gap_evidence.direct_hard_gaps,
        "grid_gaps": gap_evidence.grid_model_gaps,
        "reliable_gaps": gap_evidence.reliable_support_count,
        "reliable_support_count": gap_evidence.reliable_support_count,
        "equal_gaps": gap_evidence.equal_model_gaps,
        **width_metrics,
        "outer_area_ratio": outer_area,
        "outer_area_profile": outer_area_profile,
        "image_quality": {
            "p01": float(p01),
            "p50": float(p50),
            "p99": float(p99),
            "range_1_99": contrast,
            "contrast_ok": bool(contrast >= base_score.image_quality_contrast_min),
            "min_contrast": float(base_score.image_quality_contrast_min),
            "role": "diagnostic_not_crop_gate",
        },
        "contrast_1_99": contrast,
        "full_geometry_ok": full_geometry_ok,
        "separator_gate_profile": separator_gate.profile,
    }
    return float(max(0.0, min(1.0, confidence))), sorted(set(reasons)), detail


def apply_base_detection_scoring(
    gray_work: np.ndarray,
    detection: Detection,
    config: RuntimeConfig,
    fmt: FormatSpec,
    policy: Optional[DetectionPolicy] = None,
) -> Detection:
    """Apply separator base assessment to a built candidate."""
    detail = dict(detection.detail)
    scoring_detail = detail.get("base_candidate_scoring", {})
    if isinstance(scoring_detail, dict) and bool(scoring_detail.get("applied", False)):
        return replace(detection, review_reasons=list(detection.review_reasons), detail=detail)

    policy = policy or get_detection_policy(fmt.name, detection.strip_mode)
    work_outer = _work_box_from_detail(detail)
    work_frame_boxes = _work_frame_boxes_from_detail(detail)
    if work_outer is None or not work_frame_boxes:
        detail["base_candidate_scoring"] = {
            "applied": False,
            "owner": "candidate.assessment",
            "reason": "missing_build_geometry",
        }
        return replace(detection, review_reasons=list(detection.review_reasons), detail=detail)

    origin = _detail_float(detail, "origin", 0.0)
    pitch = _detail_float(detail, "pitch", 0.0)
    confidence, reasons, base_detail = base_detection_assessment(
        gray_work,
        work_outer,
        detection.gaps,
        work_frame_boxes,
        detection.count,
        fmt,
        detection.strip_mode,
        policy,
        origin=origin,
        pitch=pitch,
    )
    pre_nearby_gaps = _gaps_from_detail(detail, "pre_nearby_gaps")
    if pre_nearby_gaps:
        wh, ww = gray_work.shape
        pre_nearby_boxes_work = frame_boxes_from_gaps(
            work_outer,
            pre_nearby_gaps,
            detection.count,
            ww,
            wh,
            config.bleed_x,
            config.bleed_y,
            origin=origin,
            pitch=pitch,
        )
        pre_nearby_confidence, _pre_nearby_reasons, _pre_nearby_detail = base_detection_assessment(
            gray_work,
            work_outer,
            pre_nearby_gaps,
            pre_nearby_boxes_work,
            detection.count,
            fmt,
            detection.strip_mode,
            policy,
            origin=origin,
            pitch=pitch,
        )
        score_boxes_work = frame_boxes_from_gaps(
            work_outer,
            detection.gaps,
            detection.count,
            ww,
            wh,
            config.bleed_x,
            config.bleed_y,
            origin=origin,
            pitch=pitch,
            apply_geometry_fit=policy.frame_fit.geometry_fallback,
            geometry_config=policy.frame_fit,
        )
        geometry_confidence, _geometry_reasons, _geometry_detail = base_detection_assessment(
            gray_work,
            work_outer,
            detection.gaps,
            score_boxes_work,
            detection.count,
            fmt,
            detection.strip_mode,
            policy,
            origin=origin,
            pitch=pitch,
        )
        confidence = min(confidence, geometry_confidence)
        base_detail["nearby_separator_refinement_confidence_cap"] = float(pre_nearby_confidence)
        base_detail["nearby_separator_refinement_geometry_confidence_cap"] = float(geometry_confidence)

    detail.update(base_detail)
    detail["base_candidate_scoring"] = {
        "applied": True,
        "owner": "candidate.assessment",
        "source": "separator_base_geometry",
    }
    build_detail = detail.get("candidate_build", {})
    if isinstance(build_detail, dict):
        build_detail = dict(build_detail)
        build_detail["base_scoring_applied"] = False
        build_detail["base_scoring_owner"] = "candidate.assessment"
        detail["candidate_build"] = build_detail
    return replace(
        detection,
        confidence=float(max(0.0, min(1.0, confidence))),
        review_reasons=sorted(set([*detection.review_reasons, *reasons])),
        detail=detail,
    )


__all__ = [
    "apply_base_detection_scoring",
    "base_detection_assessment",
]
