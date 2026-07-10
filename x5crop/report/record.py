from __future__ import annotations

from dataclasses import asdict

from ..app_info import VERSION
from ..detection.detail import (
    CANDIDATE_ASSESSMENT,
    CONTENT_EVIDENCE,
    DECISION_POLICY_DETAIL,
    DESKEW,
    DECISION_SIGNALS,
    EVIDENCE_SUMMARY,
    EXPOSURE_OVERLAP_EVIDENCE,
    OUTER_CONTENT_ALIGNMENT,
    OUTPUT_PROTECTION_PLAN,
    decision_schema_diagnostics,
    detail_dict,
    HOLDER_OCCUPANCY,
    policy_id_from_detail,
    runtime_policy_detail,
    SCAN_CALIBRATION,
    STRIP_COMPLETENESS,
)
from ..domain import FinalDetection, ProcessResult
from .identity import REPORT_SCHEMA_ID, REPORT_SCHEMA_REVISION
from ..utils import json_safe
from .read_models import (
    candidate_gate_detail,
    candidate_table,
    decision_gate_detail,
    selected_candidate,
)


def _missing_schema_diagnostic(owner: str, reason: str) -> dict[str, str]:
    return {"owner": owner, "reason": reason}


def _schema_validation(detection: FinalDetection, runtime_policy: dict, decision_policy: dict) -> list[dict[str, str]]:
    diagnostics = decision_schema_diagnostics(detection)
    if not runtime_policy:
        diagnostics.append(_missing_schema_diagnostic("runtime_policy", "runtime_policy_detail_missing"))
    if not decision_policy:
        diagnostics.append(_missing_schema_diagnostic("decision_policy", "decision_policy_detail_missing"))
    if not detail_dict(detection, EVIDENCE_SUMMARY):
        diagnostics.append(_missing_schema_diagnostic("evidence_summary", "evidence_summary_missing"))
    if not detail_dict(detection, DECISION_SIGNALS):
        diagnostics.append(_missing_schema_diagnostic("decision_signals", "decision_signals_missing"))
    if not policy_id_from_detail(detection):
        diagnostics.append(_missing_schema_diagnostic("policy", "policy_id_missing"))
    return diagnostics


def report_record_for_final_detection(
    detection: FinalDetection,
    result: ProcessResult,
) -> dict:
    output = {
        "protection_plan": detail_dict(detection, OUTPUT_PROTECTION_PLAN),
    }
    source = str(result.source)
    profile = dict(result.profile)
    report_detail = json_safe(dict(result.detail))
    output.update({
        "output_files": list(result.output_files),
        "review_copy": result.review_copy,
        "warnings": list(result.warnings),
    })
    runtime_policy = runtime_policy_detail(detection)
    decision_policy = detail_dict(detection, DECISION_POLICY_DETAIL)
    schema_validation = _schema_validation(detection, runtime_policy, decision_policy)
    policy_detail = {
        "runtime_policy": runtime_policy or {"missing": True, "reason": "runtime_policy_detail_missing"},
        "decision_policy": decision_policy or {"missing": True, "reason": "decision_policy_detail_missing"},
    }
    evidence_summary = detail_dict(detection, EVIDENCE_SUMMARY)
    decision_signals = detail_dict(detection, DECISION_SIGNALS)
    policy_id = policy_id_from_detail(detection)
    schema = {
        "schema_id": REPORT_SCHEMA_ID,
        "schema_revision": REPORT_SCHEMA_REVISION,
        "script_version": VERSION,
        "source": source,
        "profile": profile,
        "detail": report_detail,
        "format_id": detection.format_id,
        "strip_mode": detection.strip_mode,
        "layout": detection.layout,
        "count": int(detection.count),
        "strip_completeness": detail_dict(detection, STRIP_COMPLETENESS),
        "holder_occupancy": detail_dict(detection, HOLDER_OCCUPANCY),
        "status": detection.status,
        "confidence": float(detection.confidence),
        "final_review_reasons": list(detection.final_review_reasons),
        "outer_box": asdict(detection.outer),
        "frame_boxes": [asdict(box) for box in detection.frames],
        "gaps": [asdict(gap) for gap in detection.gaps],
        "selected_candidate": selected_candidate(detection),
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
        "schema_validation": schema_validation,
        "diagnostics": {
            "deskew": detail_dict(detection, DESKEW),
        },
        "output": output,
    }
    return json_safe(schema)
