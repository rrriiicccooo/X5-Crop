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
    decision_summary,
    detail_dict,
    final_review_reasons_from_detail,
    policy_id_from_detail,
    runtime_policy_detail,
)
from ..domain import Detection, ProcessResult
from ..policies.ids import REPORT_SCHEMA_VERSION
from ..policies.runtime.policy import DetectionPolicy
from ..utils import json_safe
from .sections import candidate_gate_detail, candidate_table, decision_gate_detail, selected_candidate


def _report_status(
    result: ProcessResult | None,
    decision_detail: dict,
) -> str:
    if result is not None:
        return str(result.status)
    status = decision_detail.get("status")
    if status:
        return str(status)
    return "unknown"


def report_schema_for_detection(
    detection: Detection,
    result: ProcessResult | None = None,
    *,
    policy: DetectionPolicy,
) -> dict:
    report_policy = policy.report
    decision_detail = decision_summary(detection)
    status = _report_status(result, decision_detail)
    output = {}
    if result is not None:
        output = {
            "status": result.status,
            "output_files": list(result.output_files),
            "review_copy": result.review_copy,
            "warnings": list(result.warnings),
        }
    runtime_policy = runtime_policy_detail(detection) or {
        "missing": True,
        "reason": "runtime_policy_detail_missing",
    }
    decision_policy = (
        detail_dict(detection, DECISION_POLICY_DETAIL)
        or decision_detail.get(DECISION_POLICY_DETAIL)
        or {
            "missing": True,
            "reason": "decision_policy_detail_missing",
        }
    )
    policy = {
        "runtime_policy": runtime_policy,
        "decision_policy": decision_policy,
    }
    section_values = {
        "version": {
            "script_version": VERSION,
            "schema_version": report_policy.schema_version,
        },
        "format": {
            "format_id": detection.film_format,
            "strip_mode": detection.strip_mode,
            "count": int(detection.count),
            "layout": detection.layout,
        },
        "result": {
            "status": status,
            "confidence": float(detection.confidence),
            "final_review_reasons": final_review_reasons_from_detail(detection),
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
        },
        "candidate_gate": candidate_gate_detail(detection),
        "decision_gate": decision_gate_detail(detection),
        "diagnostics": {
            "output_overlap_evidence": detail_dict(detection, OUTPUT_OVERLAP_EVIDENCE),
            "deskew": detail_dict(detection, DESKEW),
        },
        "evidence_summary": detail_dict(detection, EVIDENCE_SUMMARY) or decision_detail.get(EVIDENCE_SUMMARY, {}),
        "decision_signals": detail_dict(detection, DECISION_SIGNALS) or decision_detail.get(DECISION_SIGNALS, {}),
        "decision_policy_detail": decision_policy,
        "policy_id": (
            policy_id_from_detail(detection)
            or decision_policy.get("policy_id")
            or runtime_policy.get("policy_id")
            or "unknown_policy"
        ),
        "output": output,
    }
    schema = {
        "schema_version": report_policy.schema_version,
        "version": VERSION,
        "format_id": detection.film_format,
        "strip_mode": detection.strip_mode,
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
        "policy_id": section_values["policy_id"],
    }
    for section in report_policy.sections:
        if section in section_values:
            schema[section] = section_values[section]
    return json_safe(schema)


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "report_schema_for_detection",
]
