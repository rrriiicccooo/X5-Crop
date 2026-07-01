from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .app_info import VERSION
from .detection_detail import (
    CANDIDATE_DECISION,
    CONTENT_EVIDENCE,
    DECISION_POLICY_DETAIL,
    DESKEW,
    EVIDENCE_SUMMARY,
    LUCKY_PASS_RISK_SCORE,
    OUTER_CONTENT_ALIGNMENT,
    OVERLAP_BLEED_RISK,
    RISK_SUMMARY,
    candidate_competition,
    candidate_decision,
    decision_summary,
    detail_dict,
    policy_detail,
    policy_id_from_detail,
)
from .domain import Detection, ProcessResult
from .policies.runtime_policy import ReportPolicy
from .policies.decision_contract import decision_contract_for
from .policies.ids import REPORT_SCHEMA_VERSION
from .policies.registry import get_detection_policy
from .utils import json_safe


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
        "candidate_decision": candidate_decision(detection),
    }


def gate_records(detection: Detection) -> list[dict[str, Any]]:
    decision = candidate_decision(detection)
    gates: list[dict[str, Any]] = []
    hard = decision.get("separator_hard_evidence", {})
    if isinstance(hard, dict):
        gates.append(
            {
                "name": "separator_gate",
                "ok": bool(hard.get("ok", False)),
                "reason": str(hard.get("reason", "")),
                "detail": hard,
            }
        )
    partial = decision.get("partial_safe_extra_frames", {})
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
            "ok": bool(decision.get("auto_gate", False)),
            "reason": "auto_gate_passed" if decision.get("auto_gate", False) else "auto_gate_failed",
            "detail": {
                "joint_score": decision.get("joint_score"),
                "content_support": decision.get("content_support"),
                "geometry_score": decision.get("geometry_score"),
                "separator_score": decision.get("separator_score"),
                "content_score": decision.get("content_score"),
            },
        }
    )
    return gates


def report_policy_for_detection(detection: Detection) -> ReportPolicy:
    try:
        return get_detection_policy(detection.film_format, detection.strip_mode).report
    except ValueError:
        return ReportPolicy()


def report_schema_for_detection(detection: Detection, result: ProcessResult | None = None) -> dict[str, Any]:
    report_policy = report_policy_for_detection(detection)
    decision_contract = decision_contract_for(detection.film_format, detection.strip_mode)
    decision_detail = decision_summary(detection)
    output = {}
    if result is not None:
        output = {
            "status": result.status,
            "output_files": list(result.output_files),
            "review_copy": result.review_copy,
            "warnings": list(result.warnings),
        }
    policy = policy_detail(detection) or decision_contract.report_detail()
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
            "status": result.status if result is not None else ("approved_auto" if not detection.review_reasons else "needs_review"),
            "confidence": float(detection.confidence),
            "review_reasons": list(detection.review_reasons),
            "outer_box": asdict(detection.outer),
            "frame_boxes": [asdict(box) for box in detection.frames],
            "gaps": [asdict(gap) for gap in detection.gaps],
        },
        "selected_candidate": selected_candidate(detection),
        "candidate_table": candidate_table(detection),
        "policy": policy,
        "evidence": {
            "content": detail_dict(detection, CONTENT_EVIDENCE),
            "separator": detail_dict(detection, CANDIDATE_DECISION).get("separator_hard_evidence", {}),
            "outer_content_alignment": detail_dict(detection, OUTER_CONTENT_ALIGNMENT),
        },
        "gates": gate_records(detection),
        "finalization": {
            "lucky_pass_risk": detail_dict(detection, LUCKY_PASS_RISK_SCORE),
            "overlap_bleed_risk": detail_dict(detection, OVERLAP_BLEED_RISK),
            "deskew": detail_dict(detection, DESKEW),
        },
        "evidence_summary": detail_dict(detection, EVIDENCE_SUMMARY) or decision_detail.get(EVIDENCE_SUMMARY, {}),
        "risk_summary": detail_dict(detection, RISK_SUMMARY) or decision_detail.get(RISK_SUMMARY, {}),
        "decision_policy_detail": (
            detail_dict(detection, DECISION_POLICY_DETAIL)
            or decision_detail.get(DECISION_POLICY_DETAIL, decision_contract.report_detail())
        ),
        "policy_id": (
            policy_id_from_detail(detection)
            or policy.get("policy_id")
            or decision_contract.policy_id
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
        "review_reasons": section_values["result"]["review_reasons"],
        "outer_box": section_values["result"]["outer_box"],
        "frame_boxes": section_values["result"]["frame_boxes"],
        "gaps": section_values["result"]["gaps"],
        "selected_candidate": section_values["selected_candidate"],
        "evidence_summary": section_values["evidence_summary"],
        "risk_summary": section_values["risk_summary"],
        "decision_policy_detail": section_values["decision_policy_detail"],
        "policy_id": section_values["policy_id"],
    }
    for section in report_policy.sections:
        if section in section_values:
            schema[section] = section_values[section]
    return json_safe(schema)


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "candidate_table",
    "gate_records",
    "report_policy_for_detection",
    "report_schema_for_detection",
    "selected_candidate",
]
