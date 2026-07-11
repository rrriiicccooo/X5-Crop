from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional

import numpy as np

from ....domain import Box, DetectionCandidate, SeparatorBandObservation
from ....formats import FormatPhysicalSpec
from ....geometry.frame_fit import frame_boxes_from_gaps
from ....geometry.gap_geometry import (
    gap_width_cv,
    separator_width_cv,
    separator_widths,
    width_cv as coefficient_of_variation,
)
from ....policies.runtime.policy import DetectionPolicy
from ....policies.parameters.scoring import BaseDetectionScoreParameters
from ....run_config import RunConfig
from ....utils import box_from_dict, gap_from_dict, sampled_percentile
from ...evidence.frame_topology import frame_topology_evidence
from ...evidence.separator_continuity import separator_cross_axis_continuity_evidence
from ...physical.photo_size import photo_size_consistency_from_gap_edges
from ...evidence.separator_summary import gap_method_evidence_summary


@dataclass(frozen=True)
class BaseDetectionAssessment:
    confidence: float
    detail: dict[str, Any]


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


def _gaps_from_detail(detail: dict[str, Any], key: str) -> list[SeparatorBandObservation]:
    value = detail.get(key)
    if not isinstance(value, list):
        return []
    gaps: list[SeparatorBandObservation] = []
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
    gaps: list[SeparatorBandObservation],
    boxes: list[Box],
    origin: float | None,
    pitch: float | None,
    count: int,
    target_photo_width: float | None = None,
) -> dict[str, Any]:
    frame_widths = _frame_box_widths(boxes)
    frame_box_cv = coefficient_of_variation(frame_widths) if frame_widths else 1.0
    photo_size = (
        photo_size_consistency_from_gap_edges(
            gaps,
            float(origin),
            float(pitch),
            count,
            target_photo_width=target_photo_width,
        )
        if origin is not None and pitch is not None and pitch > 0.0
        else None
    )
    photo_widths = list(photo_size.photo_widths) if photo_size is not None and photo_size.used else None
    photo_cv = photo_size.photo_width_cv if photo_size is not None and photo_size.used else None
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
        "photo_size_consistency": (
            photo_size.detail()
            if photo_size is not None
            else {"used": False, "reason": "missing_origin_or_pitch"}
        ),
        "photo_widths": photo_widths or [],
        "frame_box_widths": frame_widths,
        "separator_widths": separator_widths(gaps),
    }


def _outer_area_profile(
    outer_area: float,
    base_score: BaseDetectionScoreParameters,
) -> dict[str, Any]:
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


def _photo_width_stability_profile(
    width_metrics: dict[str, Any],
    base_score: BaseDetectionScoreParameters,
) -> dict[str, Any]:
    frame_box_cv_value = width_metrics.get("frame_box_width_cv")
    try:
        frame_box_cv = 1.0 if frame_box_cv_value is None else float(frame_box_cv_value)
    except (TypeError, ValueError):
        frame_box_cv = 1.0
    photo_width_cv = width_metrics.get("photo_width_cv")
    if photo_width_cv is None:
        return {
            "used": False,
            "reason": "photo_width_unavailable",
            "role": "diagnostic_until_photo_edges",
            "width_cv_source": width_metrics.get("width_cv_source", "unknown"),
            "photo_width_cv": None,
            "frame_box_width_cv": frame_box_cv,
            "confidence": None,
            "unstable": False,
        }
    cv = float(photo_width_cv)
    return {
        "used": True,
        "reason": "ok" if cv <= base_score.unstable_photo_width_cv else "photo_width_unstable",
        "role": "base_confidence_input",
        "width_cv_source": "photo_edges",
        "photo_width_cv": cv,
        "frame_box_width_cv": frame_box_cv,
        "confidence": max(0.0, min(1.0, 1.0 - cv / base_score.photo_width_cv_norm)),
        "unstable": cv > base_score.unstable_photo_width_cv,
        "unstable_photo_width_cv": float(base_score.unstable_photo_width_cv),
    }


def base_detection_assessment(
    gray_work: np.ndarray,
    outer: Box,
    gaps: list[SeparatorBandObservation],
    boxes: list[Box],
    count: int,
    fmt: FormatPhysicalSpec,
    strip_mode: str,
    policy: DetectionPolicy,
    origin: float | None = None,
    pitch: float | None = None,
) -> BaseDetectionAssessment:
    base_score = policy.scoring.base_detection
    separator_support = policy.separator.support
    expected_gaps = max(0, count - 1)
    gap_evidence = gap_method_evidence_summary(
        gaps,
        separator_support.reliable_gap_min_score,
    )
    frame_aspect = float(fmt.horizontal_content_aspect or 0.0)
    target_photo_width = float(outer.height) * frame_aspect if frame_aspect > 0.0 else None
    width_metrics = _candidate_width_metrics(
        gaps,
        boxes,
        origin,
        pitch,
        count,
        target_photo_width=target_photo_width,
    )
    photo_width_cv = width_metrics.get("photo_width_cv")
    photo_width_within_full_limit = (
        True if photo_width_cv is None else float(photo_width_cv) <= base_score.full_photo_width_cv
    )
    photo_width_tight = (
        False if photo_width_cv is None else float(photo_width_cv) <= base_score.geometry_floor_tight_photo_width_cv
    )
    photo_width_stability = _photo_width_stability_profile(width_metrics, base_score)
    work_h, work_w = gray_work.shape
    topology_boxes = frame_boxes_from_gaps(
        outer,
        gaps,
        count,
        work_w,
        work_h,
        0,
        0,
        origin=origin or 0.0,
        pitch=pitch,
    )
    topology_evidence = frame_topology_evidence(topology_boxes, count)
    separator_continuity = separator_cross_axis_continuity_evidence(
        gray_work,
        outer,
        gaps,
        pitch or 0.0,
        policy.separator.hard_gap_trust,
    )
    outer_area = float(outer.width * outer.height) / max(1.0, float(gray_work.shape[0] * gray_work.shape[1]))
    outer_area_profile = _outer_area_profile(outer_area, base_score)
    low_image, median_image, high_image = sampled_percentile(
        gray_work,
        base_score.image_quality_percentiles,
    )
    contrast = float(high_image - low_image)

    gap_conf = 1.0 if expected_gaps == 0 else gap_evidence.separator_support_count / float(expected_gaps)
    width_conf = photo_width_stability.get("confidence")
    hard_support_floor_checks_enabled = (
        expected_gaps >= base_score.hard_support_floor_min_expected_gaps
    )
    geometry_support_allowed = bool(policy.separator.geometry_support.active_modes())
    enough_profile_separator_evidence = (
        not hard_support_floor_checks_enabled
        or expected_gaps <= 1
        or (
            gap_evidence.hard_separator_gaps >= separator_support.score_min_hard_gaps
            and gap_evidence.equal_model_gaps
            <= max(separator_support.score_max_equal_gaps_floor, expected_gaps // 2)
        )
    )

    confidence_weight = max(
        1e-6,
        base_score.gap_weight
        + (base_score.photo_width_weight if width_conf is not None else 0.0),
    )
    confidence = base_score.gap_weight * gap_conf
    if width_conf is not None:
        confidence += base_score.photo_width_weight * float(width_conf)
    confidence /= confidence_weight

    full_geometry_ok = (
        strip_mode == "full"
        and count == fmt.default_count
        and len(boxes) == count
        and (
            photo_width_within_full_limit
            or (
                hard_support_floor_checks_enabled
                and gap_evidence.separator_support_count == expected_gaps
            )
        )
        and base_score.full_outer_min_area <= outer_area <= base_score.outer_max_area
        and outer_area <= base_score.outer_too_large
        and enough_profile_separator_evidence
        and (
            hard_support_floor_checks_enabled
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
            if (hard_support_floor_checks_enabled or geometry_support_allowed) and photo_width_tight
            else base_score.geometry_floor_low
        )
        confidence = max(confidence, geometry_floor)
    partial_count_assessment = {
        "used": bool(strip_mode == "partial" and count < fmt.default_count),
        "reason": "not_partial_or_default_count",
        "intrinsically_ambiguous": False,
        "count": int(count),
        "default_count": int(fmt.default_count),
        "role": "count_ambiguity_only",
    }
    if strip_mode == "partial" and count < fmt.default_count:
        if count <= 1:
            partial_count_assessment["reason"] = "single_frame_partial"
            partial_count_assessment["intrinsically_ambiguous"] = True
        elif (
            count <= base_score.partial_ambiguous_count_max
            and fmt.default_count >= base_score.partial_dense_sequence_min_nominal_count
        ):
            partial_count_assessment["reason"] = "two_frame_dense_sequence_partial"
            partial_count_assessment["intrinsically_ambiguous"] = True
        else:
            partial_count_assessment["reason"] = "enough_frames_for_physical_assessment"

    detail = {
        "detected_gaps": gap_evidence.separator_support_count,
        "separator_support_count": gap_evidence.separator_support_count,
        "actual_detected_gaps": gap_evidence.direct_hard_gaps,
        "reliable_gaps": gap_evidence.reliable_support_count,
        "reliable_support_count": gap_evidence.reliable_support_count,
        "equal_gaps": gap_evidence.equal_model_gaps,
        **width_metrics,
        "frame_topology_evidence": topology_evidence,
        "separator_cross_axis_continuity": separator_continuity,
        "photo_width_stability": photo_width_stability,
        "outer_area_ratio": outer_area,
        "outer_area_profile": outer_area_profile,
        "image_quality": {
            "low": float(low_image),
            "median": float(median_image),
            "high": float(high_image),
            "percentiles": list(base_score.image_quality_percentiles),
            "range": contrast,
            "contrast_ok": bool(contrast >= base_score.image_quality_contrast_min),
            "min_contrast": float(base_score.image_quality_contrast_min),
            "role": "diagnostic_not_crop_boundary",
        },
        "image_quality_contrast": contrast,
        "full_geometry_ok": full_geometry_ok,
        "separator_support_policy": "unified_physical_support",
        "partial_count_assessment": partial_count_assessment,
    }
    return BaseDetectionAssessment(
        confidence=float(max(0.0, min(1.0, confidence))),
        detail=detail,
    )


def apply_base_detection_scoring(
    gray_work: np.ndarray,
    detection: DetectionCandidate,
    config: RunConfig,
    fmt: FormatPhysicalSpec,
    policy: DetectionPolicy,
) -> DetectionCandidate:
    """Apply separator base assessment to a built candidate."""
    detail = dict(detection.detail)
    scoring_detail = detail.get("base_candidate_scoring", {})
    if isinstance(scoring_detail, dict) and bool(scoring_detail.get("applied", False)):
        return replace(detection, detail=detail)

    work_outer = _work_box_from_detail(detail)
    work_frame_boxes = _work_frame_boxes_from_detail(detail)
    if work_outer is None or not work_frame_boxes:
        detail["base_candidate_scoring"] = {
            "applied": False,
            "owner": "candidate.assessment",
            "reason": "missing_build_geometry",
        }
        return replace(detection, detail=detail)

    origin = _detail_float(detail, "origin", 0.0)
    pitch = _detail_float(detail, "pitch", 0.0)
    assessment = base_detection_assessment(
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
    confidence = assessment.confidence
    base_detail = assessment.detail
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
        pre_nearby_assessment = base_detection_assessment(
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
        )
        geometry_assessment = base_detection_assessment(
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
        confidence = min(confidence, geometry_assessment.confidence)
        base_detail["nearby_separator_refinement_pre_score"] = float(
            pre_nearby_assessment.confidence
        )
        base_detail["nearby_separator_refinement_geometry_score"] = float(
            geometry_assessment.confidence
        )

    detail.update(base_detail)
    detail["base_candidate_scoring"] = {
        "applied": True,
        "owner": "candidate.assessment",
        "source": "separator_base_geometry",
    }
    return replace(
        detection,
        confidence=float(max(0.0, min(1.0, confidence))),
        detail=detail,
    )
