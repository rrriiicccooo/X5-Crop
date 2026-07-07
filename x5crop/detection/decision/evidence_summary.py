from __future__ import annotations

from typing import Any

import numpy as np

from ...domain import Detection
from ...gap_methods import (
    is_content_model_gap_method,
    is_equal_model_gap_method,
    is_grid_model_gap_method,
    is_hard_gap_method,
)
from ...policies.decision.contract import DetectionDecisionContract
from ..evidence.photo_width import (
    photo_width_stability_detail,
    photo_width_within_limit,
)
from ..evidence.separator_summary import SeparatorGateDetailSummary, separator_gate_detail_summary


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _gap_method_count(detection: Detection, predicate) -> int:
    return sum(1 for gap in detection.gaps if predicate(gap.method))


def _separator_summary_from_assessment(detection: Detection) -> SeparatorGateDetailSummary:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    hard_detail = _dict(assessment.get("separator_hard_evidence"))
    return separator_gate_detail_summary(
        hard_detail,
        expected_default=max(0, int(detection.count) - 1),
        hard_default=sum(1 for gap in detection.gaps if is_hard_gap_method(gap.method)),
        grid_default=_gap_method_count(detection, is_grid_model_gap_method),
        equal_default=_gap_method_count(detection, is_equal_model_gap_method),
        content_default=_gap_method_count(detection, is_content_model_gap_method),
    )


def _separator_summary(detection: Detection) -> dict[str, Any]:
    return _separator_summary_from_assessment(detection).evidence_detail()


def evidence_summary_for(
    gray: np.ndarray,
    detection: Detection,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    policy: DetectionDecisionContract,
) -> dict[str, Any]:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    separator = _separator_summary(detection)
    outer_area_ratio = _float(
        detection.detail.get("outer_area_ratio"),
        (detection.outer.width * detection.outer.height) / float(max(1, gray.shape[0] * gray.shape[1])),
    )
    geometry_score = _float(assessment.get("geometry_score"), 0.0)
    content_score = _float(assessment.get("content_score"), 0.0)
    content_quality_score = _float(assessment.get("content_quality_score"), 0.0)
    width_cv = _float(detection.detail.get("width_cv"), 1.0)
    width_cv_source = str(detection.detail.get("width_cv_source") or "unknown")
    photo_width_stability = photo_width_stability_detail(
        detection.detail,
        policy.evidence.max_photo_width_cv_ratio,
        used_role="photo_width_gate",
    )
    photo_width_stability["max_photo_width_cv_ratio"] = policy.evidence.max_photo_width_cv_ratio
    photo_width_ok = bool(photo_width_stability.get("ok", True))
    content_support = str(content_detail.get("support", ""))
    content_containment_ok = bool(content_detail.get("content_containment_ok", False))
    content_harm_risk = bool(content_detail.get("content_harm_risk", True))
    content_quality_ok = content_quality_score >= policy.evidence.min_content_score
    partial_detail = _dict(assessment.get("partial_safe_extra_frames"))
    partial_edge_safe = bool(partial_detail.get("ok", False))
    expected = int(separator["expected_gaps"])
    hard_ratio = float(separator["hard_gap_ratio"])
    model_share = float(separator["model_gap_share"])
    geometry_support_mode = str(separator.get("geometry_support_mode") or "")
    geometry_supported_separator = (
        policy.evidence.allow_geometry_supported_separator
        and geometry_support_mode in {"detected_geometry", "stable_grid"}
        and hard_ratio >= policy.evidence.geometry_supported_min_hard_ratio
        and photo_width_within_limit(
            detection.detail,
            policy.evidence.geometry_supported_max_photo_width_cv_ratio,
            unavailable_ok=True,
        )
        and int(separator["equal_gaps"]) <= policy.evidence.max_equal_gap_count
        and content_containment_ok
        and not content_harm_risk
    )
    partial_supported_separator = (
        detection.strip_mode == "partial"
        and partial_edge_safe
        and int(separator["hard_gaps"]) >= 1
        and content_containment_ok
        and not content_harm_risk
    )
    separator_ok = (
        expected <= 0
        or geometry_supported_separator
        or partial_supported_separator
        or (
            int(separator["hard_gaps"]) >= policy.evidence.min_hard_separator_count
            and hard_ratio >= policy.evidence.min_hard_separator_ratio
            and int(separator["equal_gaps"]) <= policy.evidence.max_equal_gap_count
            and int(separator["content_gaps"]) <= policy.evidence.max_content_gap_count
            and model_share <= policy.evidence.max_model_gap_share
        )
    )
    outer_area_ok = (
        policy.evidence.min_outer_area_ratio
        <= outer_area_ratio
        <= policy.evidence.max_outer_area_ratio
    )
    outer_alignment_ok = bool(outer_alignment.get("ok", True))
    safe_overcut_allowed = (
        not outer_area_ok
        and outer_area_ratio > policy.evidence.max_outer_area_ratio
        and bool(outer_alignment.get("used", False))
        and outer_alignment_ok
        and bool(outer_alignment.get("overcontainment_allowed", False))
        and content_containment_ok
        and not content_harm_risk
    )
    outer_ok = outer_alignment_ok and (outer_area_ok or safe_overcut_allowed)
    geometry_ok = (
        photo_width_ok
        and geometry_score >= policy.evidence.min_geometry_score
    )
    content_ok = (
        content_containment_ok
        and not content_harm_risk
    )
    return {
        "outer": {
            "ok": bool(outer_ok),
            "outer_area_ratio": outer_area_ratio,
            "min_outer_area_ratio": policy.evidence.min_outer_area_ratio,
            "max_outer_area_ratio": policy.evidence.max_outer_area_ratio,
            "area_ok": bool(outer_area_ok),
            "alignment_ok": bool(outer_alignment_ok),
            "safe_overcut_allowed": bool(safe_overcut_allowed),
            "outer_content_alignment": outer_alignment,
        },
        "separator": {
            **separator,
            "ok": bool(separator_ok),
            "geometry_supported_separator": bool(geometry_supported_separator),
            "partial_supported_separator": bool(partial_supported_separator),
            "min_hard_separator_ratio": policy.evidence.min_hard_separator_ratio,
            "min_hard_separator_count": policy.evidence.min_hard_separator_count,
            "max_model_gap_share": policy.evidence.max_model_gap_share,
        },
        "geometry": {
            "ok": bool(geometry_ok),
            "width_cv": width_cv,
            "width_cv_source": width_cv_source,
            "photo_width_stability": photo_width_stability,
            "max_photo_width_cv_ratio": policy.evidence.max_photo_width_cv_ratio,
            "geometry_score": geometry_score,
            "min_geometry_score": policy.evidence.min_geometry_score,
        },
        "content": {
            "ok": bool(content_ok),
            "support": content_support,
            "content_containment_ok": bool(content_containment_ok),
            "content_harm_risk": bool(content_harm_risk),
            "content_score": content_score,
            "content_score_role": assessment.get("content_score_role", "content_containment_support"),
            "content_quality_score": content_quality_score,
            "quality_ok": bool(content_quality_ok),
            "score_role": "quality_diagnostic_not_hard_gate",
            "min_content_score": policy.evidence.min_content_score,
            "detail": content_detail,
        },
        "partial_edge": {
            "ok": bool(partial_edge_safe),
            "required": bool(detection.strip_mode == "partial" and policy.evidence.partial_requires_safe_edge),
            "detail": partial_detail,
        },
    }


__all__ = [
    "evidence_summary_for",
]
