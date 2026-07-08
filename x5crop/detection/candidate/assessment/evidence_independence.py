from __future__ import annotations

from typing import Any

from ....domain import Detection
from ....policies.runtime.candidate import EvidenceIndependencePolicy
from ...evidence.photo_width import photo_width_stability_detail


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _entries(detail: dict[str, Any]) -> list[dict[str, Any]]:
    entries = detail.get("entries", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def gap_source_count(detail: dict[str, Any], sources: tuple[str, ...]) -> int:
    wanted = set(sources)
    return sum(1 for entry in _entries(detail) if str(entry.get("selected_source", "")) in wanted)


def evidence_independence_detail(
    detection: Detection,
    *,
    source: str,
    content_support: str,
    content_score: float,
    geometry_score: float,
    policy: EvidenceIndependencePolicy,
) -> dict[str, Any]:
    if not policy.enabled:
        return {"used": False, "ok": True, "reason": "disabled"}
    if source != "separator":
        return {"used": False, "ok": True, "reason": "non_separator_source"}

    outer_strategy = str(detection.detail.get("outer_candidate_strategy", ""))
    separator_detail = _dict(detection.detail.get("standard_gap_search"))
    dependent_outer = outer_strategy in set(policy.dependent_outer_strategies)
    dependent_gap_count = gap_source_count(
        separator_detail,
        tuple(policy.dependent_gap_sources),
    )
    requires_validation = (
        dependent_outer
        and dependent_gap_count > int(policy.max_dependent_gap_count_without_validation)
    )
    standard_detected_gaps = gap_source_count(separator_detail, ("standard_detected",))
    photo_width_stability = photo_width_stability_detail(
        detection.detail,
        float(policy.max_photo_width_cv),
        used_role="evidence_independence_geometry_check",
    )
    standard_ok = standard_detected_gaps >= int(policy.min_standard_detected_gaps)
    content_ok = content_support == policy.require_content_support
    content_quality_ok = float(content_score) >= float(policy.min_content_score)
    geometry_ok = (
        float(geometry_score) >= float(policy.min_geometry_score)
        and bool(photo_width_stability.get("used", False))
        and bool(photo_width_stability.get("ok", False))
    )
    ok = (
        True
        if not requires_validation
        else bool(standard_ok and content_ok and geometry_ok)
    )
    reason = "ok" if ok else policy.candidate_signal
    return {
        "used": True,
        "ok": bool(ok),
        "reason": reason,
        "requires_validation": bool(requires_validation),
        "outer_candidate_strategy": outer_strategy,
        "dependent_outer": bool(dependent_outer),
        "dependent_gap_sources": list(policy.dependent_gap_sources),
        "dependent_gap_count": int(dependent_gap_count),
        "max_dependent_gap_count_without_validation": int(
            policy.max_dependent_gap_count_without_validation
        ),
        "standard_detected_gaps": int(standard_detected_gaps),
        "min_standard_detected_gaps": int(policy.min_standard_detected_gaps),
        "standard_ok": bool(standard_ok),
        "content_support": content_support,
        "required_content_support": policy.require_content_support,
        "content_score": float(content_score),
        "min_content_score": float(policy.min_content_score),
        "content_ok": bool(content_ok),
        "content_quality_ok": bool(content_quality_ok),
        "content_score_role": "quality_diagnostic_not_hard_gate",
        "geometry_score": float(geometry_score),
        "min_geometry_score": float(policy.min_geometry_score),
        "width_cv": _float(detection.detail.get("width_cv"), 1.0),
        "width_cv_source": str(detection.detail.get("width_cv_source") or "unknown"),
        "max_photo_width_cv": float(policy.max_photo_width_cv),
        "photo_width_stability": photo_width_stability,
        "geometry_ok": bool(geometry_ok),
    }


__all__ = [
    "evidence_independence_detail",
    "gap_source_count",
]
