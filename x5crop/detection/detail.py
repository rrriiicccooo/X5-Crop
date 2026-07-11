from __future__ import annotations

from typing import Any

from ..domain import DetectionCandidate, FinalDetection


CANDIDATE_ASSESSMENT = "candidate_assessment"
SELECTION_GEOMETRY_CONSENSUS = "selection_geometry_consensus"
COUNT_SELECTION = "count_selection"
CONTENT_EVIDENCE = "content_evidence"
DECISION_GEOMETRY = "decision_geometry"
DECISION_SUMMARY = "decision_summary"
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


def selection_geometry_consensus(detection: DetectionCandidate) -> dict[str, Any]:
    return detail_dict(detection, SELECTION_GEOMETRY_CONSENSUS)


def candidate_assessment(detection: DetectionCandidate) -> dict[str, Any]:
    return detail_dict(detection, CANDIDATE_ASSESSMENT)


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
