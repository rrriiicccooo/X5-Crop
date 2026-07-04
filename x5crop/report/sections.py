from __future__ import annotations

from typing import Any

from ..detection_detail import candidate_assessment, candidate_competition
from ..domain import Detection
from ..policies.registry import get_detection_policy
from ..policies.runtime.diagnostics import ReportPolicy


def candidate_table(detection: Detection) -> list[dict[str, Any]]:
    candidates = candidate_competition(detection).get("top_candidates", [])
    return list(candidates) if isinstance(candidates, list) else []


def selected_candidate(detection: Detection) -> dict[str, Any]:
    competition = candidate_competition(detection)
    selected = competition.get("selected_candidate")
    if isinstance(selected, dict):
        return dict(selected)
    return {
        "format": detection.film_format,
        "count": int(detection.count),
        "strip_mode": detection.strip_mode,
        "confidence": float(detection.confidence),
        "review_reasons": list(detection.review_reasons),
        "candidate_assessment": candidate_assessment(detection),
        "candidate_plan": detection.detail.get("candidate_plan", {}),
        "gap_search_profile": detection.detail.get("gap_search_profile", {}),
        "separator_width_profile": detection.detail.get("separator_width_profile", {}),
    }


def gate_records(detection: Detection) -> list[dict[str, Any]]:
    assessment = candidate_assessment(detection)
    gates: list[dict[str, Any]] = []
    hard = assessment.get("separator_hard_evidence", {})
    if isinstance(hard, dict):
        gates.append(
            {
                "name": "separator_gate",
                "ok": bool(hard.get("ok", False)),
                "reason": str(hard.get("reason", "")),
                "detail": hard,
            }
        )
    partial = assessment.get("partial_safe_extra_frames", {})
    if isinstance(partial, dict) and bool(partial.get("used", False)):
        gates.append(
            {
                "name": "partial_safe_extra_frames_gate",
                "ok": bool(partial.get("ok", False)),
                "reason": str(partial.get("reason", "")),
                "detail": partial,
            }
        )
    gates.append(
        {
            "name": "auto_pass_gate",
            "ok": bool(assessment.get("auto_gate", False)),
            "reason": "auto_gate_passed" if assessment.get("auto_gate", False) else "auto_gate_failed",
            "detail": {
                "joint_score": assessment.get("joint_score"),
                "content_support": assessment.get("content_support"),
                "geometry_score": assessment.get("geometry_score"),
                "separator_score": assessment.get("separator_score"),
                "content_score": assessment.get("content_score"),
            },
        }
    )
    return gates


def report_policy_for_detection(detection: Detection) -> ReportPolicy:
    try:
        return get_detection_policy(detection.film_format, detection.strip_mode).report
    except ValueError:
        return ReportPolicy()


__all__ = [
    "candidate_table",
    "gate_records",
    "report_policy_for_detection",
    "selected_candidate",
]
