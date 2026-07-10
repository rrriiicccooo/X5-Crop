from __future__ import annotations

from typing import Any

from ..domain import DetectionCandidate, FinalDetection


CANDIDATE_COMPETITION = "candidate_competition"
CANDIDATE_ASSESSMENT = "candidate_assessment"
CANDIDATE_SIGNALS = "candidate_signals"
COUNT_SELECTION = "count_selection"
CONTENT_EVIDENCE = "content_evidence"
DECISION_GEOMETRY = "decision_geometry"
DECISION_SUMMARY = "decision_summary"
DECISION_SIGNALS = "decision_signals"
DIAGNOSTICS = "diagnostics"
EVIDENCE_SUMMARY = "evidence_summary"
OUTER_CONTENT_ALIGNMENT = "outer_content_alignment"
EXPOSURE_OVERLAP_EVIDENCE = "exposure_overlap_evidence"
OUTPUT_PROTECTION_PLAN = "output_protection_plan"
SCAN_CALIBRATION = "scan_calibration"
STRIP_COMPLETENESS = "strip_completeness"
HOLDER_OCCUPANCY = "holder_occupancy"


def detail_dict(detection: DetectionCandidate, key: str) -> dict[str, Any]:
    value = detection.detail.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def candidate_competition(detection: DetectionCandidate) -> dict[str, Any]:
    return detail_dict(detection, CANDIDATE_COMPETITION)


def candidate_assessment(detection: DetectionCandidate) -> dict[str, Any]:
    return detail_dict(detection, CANDIDATE_ASSESSMENT)


def candidate_signals_from_detail(detection: DetectionCandidate) -> list[str]:
    signals = detection.detail.get(CANDIDATE_SIGNALS)
    if isinstance(signals, list):
        return [str(signal) for signal in signals if signal]
    return []


def decision_summary(detection: DetectionCandidate) -> dict[str, Any]:
    return detail_dict(detection, DECISION_SUMMARY)


def decision_schema_diagnostics(detection: FinalDetection) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    summary = detection.detail.get(DECISION_SUMMARY)
    if not isinstance(summary, dict):
        diagnostics.append({"owner": "decision", "reason": "decision_summary_missing"})
        return diagnostics
    if not isinstance(summary.get("decision_gate"), dict):
        diagnostics.append({"owner": "decision", "reason": "decision_gate_missing"})
    return diagnostics
