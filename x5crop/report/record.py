from __future__ import annotations

from dataclasses import asdict

from ..app_info import VERSION
from ..detection.detail import (
    CANDIDATE_ASSESSMENT,
    COUNT_SELECTION,
    CONTENT_EVIDENCE,
    DECISION_GEOMETRY,
    DECISION_SIGNALS,
    DIAGNOSTICS,
    EVIDENCE_SUMMARY,
    EXPOSURE_OVERLAP_EVIDENCE,
    OUTER_CONTENT_ALIGNMENT,
    OUTPUT_PROTECTION_PLAN,
    decision_schema_diagnostics,
    detail_dict,
    HOLDER_OCCUPANCY,
    SCAN_CALIBRATION,
    STRIP_COMPLETENESS,
)
from ..domain import FinalDetection
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from ..utils import json_safe
from .read_models import (
    candidate_gate_detail,
    candidate_table,
    decision_gate_detail,
)


def _missing_schema_diagnostic(owner: str, reason: str) -> dict[str, str]:
    return {"owner": owner, "reason": reason}


def _schema_validation(
    detection: FinalDetection,
    policy_id: str,
    runtime_policy: dict,
    decision_policy: dict,
) -> list[dict[str, str]]:
    diagnostics = decision_schema_diagnostics(detection)
    if not runtime_policy:
        diagnostics.append(_missing_schema_diagnostic("runtime_policy", "runtime_policy_detail_missing"))
    if not decision_policy:
        diagnostics.append(_missing_schema_diagnostic("decision_policy", "decision_policy_detail_missing"))
    if not detail_dict(detection, EVIDENCE_SUMMARY):
        diagnostics.append(_missing_schema_diagnostic("evidence_summary", "evidence_summary_missing"))
    if not detail_dict(detection, DECISION_SIGNALS):
        diagnostics.append(_missing_schema_diagnostic("decision_signals", "decision_signals_missing"))
    if not policy_id:
        diagnostics.append(_missing_schema_diagnostic("policy", "policy_id_missing"))
    return diagnostics


def report_record_for_final_detection(
    detection: FinalDetection,
    *,
    source: str,
    profile: dict,
    output_files: list[str],
    review_copy: str | None,
    warnings: list[str],
    policy_id: str,
    runtime_policy: dict,
    decision_policy: dict,
    deskew_detail: dict,
    analysis_cache_metadata: dict,
) -> dict:
    output = {
        "protection_plan": detail_dict(detection, OUTPUT_PROTECTION_PLAN),
    }
    output.update({
        "output_files": list(output_files),
        "review_copy": review_copy,
        "warnings": list(warnings),
    })
    schema_validation = _schema_validation(
        detection,
        policy_id,
        runtime_policy,
        decision_policy,
    )
    policy_detail = {
        "runtime_policy": dict(runtime_policy),
        "decision_policy": dict(decision_policy),
    }
    evidence_summary = detail_dict(detection, EVIDENCE_SUMMARY)
    decision_signals = detail_dict(detection, DECISION_SIGNALS)
    schema = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": str(source),
        "profile": dict(profile),
        "format_id": detection.format_id,
        "strip_mode": detection.strip_mode,
        "layout": detection.layout,
        "count": int(detection.count),
        "count_selection": detail_dict(detection, COUNT_SELECTION),
        "strip_completeness": detail_dict(detection, STRIP_COMPLETENESS),
        "holder_occupancy": detail_dict(detection, HOLDER_OCCUPANCY),
        "status": detection.status,
        "confidence": float(detection.confidence),
        "final_review_reasons": list(detection.final_review_reasons),
        "outer_box": asdict(detection.outer),
        "frame_boxes": [asdict(box) for box in detection.frames],
        "gaps": [asdict(gap) for gap in detection.gaps],
        "candidate_table": candidate_table(detection),
        "policy": policy_detail,
        "policy_id": policy_id,
        "evidence": {
            "content": detail_dict(detection, CONTENT_EVIDENCE),
            "separator": detail_dict(detection, CANDIDATE_ASSESSMENT).get(
                "separator_support",
                {},
            ),
            "outer_content_alignment": detail_dict(detection, OUTER_CONTENT_ALIGNMENT),
            "exposure_overlap": detail_dict(detection, EXPOSURE_OVERLAP_EVIDENCE),
        },
        "evidence_summary": evidence_summary,
        "candidate_gate": candidate_gate_detail(detection),
        "decision_signals": decision_signals,
        "decision_gate": decision_gate_detail(detection),
        "scan_calibration": detail_dict(detection, SCAN_CALIBRATION),
        "decision_geometry": detail_dict(detection, DECISION_GEOMETRY),
        "analysis_cache": dict(analysis_cache_metadata),
        "analysis_reuse": {"used": False},
        "schema_validation": schema_validation,
        "diagnostics": {
            "deskew": dict(deskew_detail),
            "detection": detail_dict(detection, DIAGNOSTICS),
        },
        "output": output,
    }
    return json_safe(schema)
