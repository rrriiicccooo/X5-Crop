from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
from ....policies.parameters.candidate import EvidenceIndependenceParameters
from ...evidence.photo_width import photo_width_stability_detail


DEPENDENT_OUTER_STRATEGY = "separator_outer"
DEPENDENT_GAP_SOURCES = ("observed_width_profile",)


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
    detection: DetectionCandidate,
    *,
    source: str,
    frame_content_support_available: bool,
    photo_geometry_supported: bool,
    policy: EvidenceIndependenceParameters,
) -> dict[str, Any]:
    if source != "separator":
        return {
            "used": False,
            "state": "not_applicable",
            "ok": True,
            "reason": "non_separator_source",
        }

    outer_strategy = str(detection.detail.get("outer_candidate_strategy", ""))
    separator_detail = _dict(detection.detail.get("standard_gap_search"))
    dependent_outer = outer_strategy == DEPENDENT_OUTER_STRATEGY
    dependent_gap_count = gap_source_count(
        separator_detail,
        DEPENDENT_GAP_SOURCES,
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
    content_support_available = bool(frame_content_support_available)
    geometry_ok = bool(photo_geometry_supported)
    ok = (
        True
        if not requires_validation
        else bool(standard_ok and content_support_available and geometry_ok)
    )
    reason = "ok" if ok else "evidence_dependency_cycle_detected"
    return {
        "used": True,
        "state": "supported" if ok else "contradicted",
        "ok": bool(ok),
        "reason": reason,
        "requires_validation": bool(requires_validation),
        "outer_candidate_strategy": outer_strategy,
        "dependent_outer": bool(dependent_outer),
        "dependent_gap_sources": list(DEPENDENT_GAP_SOURCES),
        "dependent_gap_count": int(dependent_gap_count),
        "max_dependent_gap_count_without_validation": int(
            policy.max_dependent_gap_count_without_validation
        ),
        "standard_detected_gaps": int(standard_detected_gaps),
        "min_standard_detected_gaps": int(policy.min_standard_detected_gaps),
        "standard_ok": bool(standard_ok),
        "frame_content_support_available": bool(content_support_available),
        "width_cv": _float(detection.detail.get("width_cv"), 1.0),
        "width_cv_source": str(detection.detail.get("width_cv_source") or "unknown"),
        "max_photo_width_cv": float(policy.max_photo_width_cv),
        "photo_width_stability": photo_width_stability,
        "geometry_ok": bool(geometry_ok),
    }
