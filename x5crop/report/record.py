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
    OUTER_CONTENT_ALIGNMENT,
    OUTPUT_OVERLAP_EVIDENCE,
    decision_schema_diagnostics,
    detail_dict,
    HOLDER_OCCUPANCY,
    policy_id_from_detail,
    runtime_policy_detail,
    SCAN_CALIBRATION,
    STRIP_COMPLETENESS,
)
from ..domain import FinalDetection, ProcessResult
from ..policies.runtime.policy import DetectionPolicy
from ..utils import json_safe
from .sections import candidate_gate_detail, candidate_table, decision_gate_detail, selected_candidate


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
    result: ProcessResult | None = None,
    *,
    policy: DetectionPolicy,
) -> dict:
    report_policy = policy.report
    output = {}
    source = ""
    profile = {}
    report_detail = json_safe(dict(detection.detail))
    if result is not None:
        source = str(result.source)
        profile = dict(result.profile)
        report_detail = json_safe(dict(result.detail))
        output = {
            "status": result.status,
            "output_files": list(result.output_files),
            "review_copy": result.review_copy,
            "warnings": list(result.warnings),
        }
    runtime_policy = runtime_policy_detail(detection)
    decision_policy = detail_dict(detection, DECISION_POLICY_DETAIL)
    schema_validation = _schema_validation(detection, runtime_policy, decision_policy)
    policy = {
        "runtime_policy": runtime_policy or {"missing": True, "reason": "runtime_policy_detail_missing"},
        "decision_policy": decision_policy or {"missing": True, "reason": "decision_policy_detail_missing"},
    }
    evidence_summary = detail_dict(detection, EVIDENCE_SUMMARY)
    decision_signals = detail_dict(detection, DECISION_SIGNALS)
    policy_id = policy_id_from_detail(detection)
    section_values = {
        "version": {
            "script_version": VERSION,
            "schema_id": report_policy.schema_id,
            "schema_revision": report_policy.schema_revision,
        },
        "source": source,
        "profile": profile,
        "detail": report_detail,
        "format": {
            "format_id": detection.film_format,
            "strip_mode": detection.strip_mode,
            "count": int(detection.count),
            "layout": detection.layout,
            "strip_completeness": detail_dict(detection, STRIP_COMPLETENESS),
            "holder_occupancy": detail_dict(detection, HOLDER_OCCUPANCY),
        },
        "result": {
            "status": detection.status,
            "confidence": float(detection.confidence),
            "final_review_reasons": list(detection.final_review_reasons),
            "outer_box": asdict(detection.outer),
            "frame_boxes": [asdict(box) for box in detection.frames],
            "gaps": [asdict(gap) for gap in detection.gaps],
        },
        "selected_candidate": selected_candidate(detection),
        "candidate_table": candidate_table(detection),
        "policy": policy,
        "evidence": {
            "content": detail_dict(detection, CONTENT_EVIDENCE),
            "separator": detail_dict(detection, CANDIDATE_ASSESSMENT).get("separator_support", {}),
            "outer_content_alignment": detail_dict(detection, OUTER_CONTENT_ALIGNMENT),
            "strip_completeness": detail_dict(detection, STRIP_COMPLETENESS),
            "holder_occupancy": detail_dict(detection, HOLDER_OCCUPANCY),
        },
        "candidate_gate": candidate_gate_detail(detection),
        "decision_gate": decision_gate_detail(detection),
        "diagnostics": {
            "schema_validation": schema_validation,
            "output_overlap_evidence": detail_dict(detection, OUTPUT_OVERLAP_EVIDENCE),
            "deskew": detail_dict(detection, DESKEW),
            "scan_calibration": detail_dict(detection, SCAN_CALIBRATION),
        },
        "schema_validation": schema_validation,
        "evidence_summary": evidence_summary,
        "decision_signals": decision_signals,
        "decision_policy_detail": policy["decision_policy"],
        "policy_id": policy_id,
        "scan_calibration": detail_dict(detection, SCAN_CALIBRATION),
        "strip_completeness": detail_dict(detection, STRIP_COMPLETENESS),
        "holder_occupancy": detail_dict(detection, HOLDER_OCCUPANCY),
        "output": output,
    }
    schema = {
        "schema_id": report_policy.schema_id,
        "schema_revision": report_policy.schema_revision,
        "version": VERSION,
        "source": section_values["source"],
        "profile": section_values["profile"],
        "detail": section_values["detail"],
        "format_id": detection.film_format,
        "strip_mode": detection.strip_mode,
        "layout": detection.layout,
        "count": int(detection.count),
        "status": section_values["result"]["status"],
        "confidence": section_values["result"]["confidence"],
        "final_review_reasons": section_values["result"]["final_review_reasons"],
        "outer_box": section_values["result"]["outer_box"],
        "frame_boxes": section_values["result"]["frame_boxes"],
        "gaps": section_values["result"]["gaps"],
        "selected_candidate": section_values["selected_candidate"],
        "evidence_summary": section_values["evidence_summary"],
        "decision_signals": section_values["decision_signals"],
        "candidate_gate": section_values["candidate_gate"],
        "decision_gate": section_values["decision_gate"],
        "decision_policy_detail": section_values["decision_policy_detail"],
        "scan_calibration": section_values["scan_calibration"],
        "strip_completeness": section_values["strip_completeness"],
        "holder_occupancy": section_values["holder_occupancy"],
        "policy_id": section_values["policy_id"],
        "schema_validation": section_values["schema_validation"],
    }
    for section in report_policy.sections:
        if section in section_values:
            schema[section] = section_values[section]
    return json_safe(schema)


__all__ = [
    "report_record_for_final_detection",
]
