from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ...domain import Detection
from ...formats import FORMATS
from ...cache.analysis import make_analysis_cache
from ...geometry.layout import work_gray
from ...policies.registry import get_detection_policy
from ...cache import AnalysisCache
from .gap_diagnostics import gap_diagnostic_record
from .separator_summary import gap_method_evidence_summary


def _detail_float(detail: dict[str, Any], key: str, default: float) -> float:
    value = detail.get(key)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def overlap_bleed_risk_detail(gray: np.ndarray, detection: Detection, cache: Optional[AnalysisCache] = None) -> dict[str, Any]:
    if not detection.gaps:
        return {"used": False, "risk": False, "reason": "no_gaps"}
    gray_work = cache.gray_work if cache is not None and cache.layout == detection.layout else work_gray(gray, detection.layout)
    gap_records = [gap_diagnostic_record(gray_work, detection, gap, cache) for gap in detection.gaps]
    overlap_risk_counts: dict[str, int] = {}
    for record in gap_records:
        risk = str(record.get("overlap_risk", "none"))
        overlap_risk_counts[risk] = overlap_risk_counts.get(risk, 0) + 1
    risk = int(overlap_risk_counts.get("strong", 0)) > 0 or int(overlap_risk_counts.get("medium", 0)) > 0
    return {
        "used": True,
        "risk": bool(risk),
        "reason": "diagnostic_overlap_risk" if risk else "no_medium_or_strong_overlap_risk",
        "overlap_risk_counts": overlap_risk_counts,
        "gap_diagnostics": gap_records,
        "gap_count": len(gap_records),
    }


def lucky_pass_risk_score_detail(
    gray: np.ndarray,
    detection: Detection,
    threshold: float,
    cache: Optional[AnalysisCache] = None,
) -> dict[str, Any]:
    policy = get_detection_policy(detection.film_format, detection.strip_mode).diagnostics.lucky_pass_risk
    fmt = FORMATS.get(detection.film_format, FORMATS["135"])
    if (
        not policy.enabled
        or detection.strip_mode != "full"
        or detection.count != fmt.default_count
        or detection.confidence < threshold
    ):
        return {"used": False, "reason": "not_applicable"}
    analysis_cache = cache if cache is not None and cache.layout == detection.layout else make_analysis_cache(gray, detection.layout)
    gray_work = analysis_cache.gray_work
    gap_records = [gap_diagnostic_record(gray_work, detection, gap, analysis_cache) for gap in detection.gaps]
    hard_counts: dict[str, int] = {}
    overlap_risk_counts: dict[str, int] = {}
    for record in gap_records:
        trust = str(record.get("hard_trust", "not_hard_gap"))
        hard_counts[trust] = hard_counts.get(trust, 0) + 1
        risk = str(record.get("overlap_risk", "none"))
        overlap_risk_counts[risk] = overlap_risk_counts.get(risk, 0) + 1
    strong_hard = int(hard_counts.get("strong_separator", 0))
    suspicious_hard = sum(
        int(hard_counts.get(name, 0))
        for name in ("suspect_internal_edge", "suspect_frame_border", "nearby_separator_conflict", "geometry_conflict")
    )
    strong_overlap_models = int(overlap_risk_counts.get("strong", 0))
    gap_evidence = gap_method_evidence_summary(detection.gaps, reliable_min_score=0.0)
    geometry_model_gaps = gap_evidence.geometry_model_gaps
    width_cv = _detail_float(detection.detail, "width_cv", 0.0)
    width_cv_source = str(detection.detail.get("width_cv_source") or "unknown")
    components: dict[str, float] = {}
    if geometry_model_gaps >= policy.model_gap_support_min:
        components["model_gap_support"] = policy.model_gap_support_weight
    elif geometry_model_gaps == 1:
        components["minor_model_gap_support"] = policy.minor_model_gap_support_weight
    if strong_hard <= policy.limited_strong_hard_max:
        components["limited_strong_hard_evidence"] = policy.limited_strong_hard_weight
    if strong_hard <= policy.very_limited_strong_hard_max:
        components["very_limited_strong_hard_evidence"] = policy.very_limited_strong_hard_weight
    if suspicious_hard >= 1:
        components["suspicious_hard_gap"] = policy.suspicious_hard_weight
    if strong_overlap_models >= 1:
        components["strong_overlap_model_gap"] = policy.strong_overlap_weight
    if geometry_model_gaps >= policy.model_gap_support_min and suspicious_hard >= 1 and strong_overlap_models >= 1:
        components["model_suspicion_overlap_combo"] = policy.combo_weight
    if width_cv >= policy.unstable_width_cv:
        components["unstable_widths"] = policy.unstable_width_weight
    elif width_cv >= policy.mild_width_cv:
        components["mild_width_instability"] = policy.mild_width_weight
    if strong_hard >= policy.strong_hard_credit_min:
        components["strong_hard_evidence_credit"] = policy.strong_hard_credit
    if width_cv < policy.stable_width_cv and geometry_model_gaps >= policy.stable_model_gap_min:
        components["stable_global_geometry_credit"] = policy.stable_geometry_credit
    risk_score = max(0.0, min(1.0, sum(components.values())))
    risk_threshold = policy.risk_threshold
    risk = risk_score >= risk_threshold
    return {
        "used": True,
        "risk": bool(risk),
        "reason": "lucky_pass_risk" if risk else "ok",
        "risk_score": float(risk_score),
        "risk_threshold": float(risk_threshold),
        "components": components,
        "hard_trust_counts": hard_counts,
        "overlap_risk_counts": overlap_risk_counts,
        "strong_hard_gaps": int(strong_hard),
        "suspicious_hard_gaps": int(suspicious_hard),
        "strong_overlap_model_gaps": int(strong_overlap_models),
        "model_gap_count": int(geometry_model_gaps),
        "width_cv": float(width_cv),
        "width_cv_source": width_cv_source,
    }
