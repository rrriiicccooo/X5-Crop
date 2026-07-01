from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..app_info import VERSION
from ..domain import Detection, ProcessResult
from ..policies.clean_room import clean_room_policy_for
from ..policies.base import ReportPolicy
from ..policies.registry import get_detection_policy
from ..utils import json_safe

REPORT_SCHEMA_VERSION = ReportPolicy().schema_version


def candidate_table(detection: Detection) -> list[dict[str, Any]]:
    competition = detection.detail.get("candidate_competition", {})
    if not isinstance(competition, dict):
        return []
    candidates = competition.get("top_candidates", [])
    return list(candidates) if isinstance(candidates, list) else []


def selected_candidate(detection: Detection) -> dict[str, Any]:
    competition = detection.detail.get("candidate_competition", {})
    if isinstance(competition, dict) and isinstance(competition.get("selected_candidate"), dict):
        return dict(competition["selected_candidate"])
    return {
        "format": detection.film_format,
        "count": int(detection.count),
        "strip_mode": detection.strip_mode,
        "confidence": float(detection.confidence),
        "review_reasons": list(detection.review_reasons),
        "candidate_decision": detection.detail.get("candidate_decision", {}),
    }


def gate_records(detection: Detection) -> list[dict[str, Any]]:
    decision = detection.detail.get("candidate_decision", {})
    gates: list[dict[str, Any]] = []
    if isinstance(decision, dict):
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
    clean_policy = clean_room_policy_for(detection.film_format, detection.strip_mode)
    decision_detail = detection.detail.get("v4_9_decision", {})
    if not isinstance(decision_detail, dict):
        decision_detail = {}
    output = {}
    if result is not None:
        output = {
            "status": result.status,
            "output_files": list(result.output_files),
            "review_copy": result.review_copy,
            "warnings": list(result.warnings),
        }
    policy_detail = detection.detail.get("policy", clean_policy.report_detail())
    if not isinstance(policy_detail, dict):
        policy_detail = clean_policy.report_detail()
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
        "policy": policy_detail,
        "evidence": {
            "content": detection.detail.get("content_evidence", {}),
            "separator": (
                detection.detail.get("candidate_decision", {}).get("separator_hard_evidence", {})
                if isinstance(detection.detail.get("candidate_decision", {}), dict)
                else {}
            ),
            "outer_content_alignment": detection.detail.get("outer_content_alignment", {}),
        },
        "gates": gate_records(detection),
        "postprocess": {
            "lucky_pass_risk": detection.detail.get("lucky_pass_risk_score", {}),
            "overlap_bleed_risk": detection.detail.get("overlap_bleed_risk", {}),
            "deskew": detection.detail.get("deskew", {}),
        },
        "evidence_summary": detection.detail.get(
            "evidence_summary",
            decision_detail.get("evidence_summary", {}),
        ),
        "risk_summary": detection.detail.get(
            "risk_summary",
            decision_detail.get("risk_summary", {}),
        ),
        "decision_policy_detail": detection.detail.get(
            "decision_policy_detail",
            decision_detail.get("decision_policy_detail", clean_policy.report_detail()),
        ),
        "policy_id": (
            detection.detail.get("policy_id")
            or policy_detail.get("policy_id")
            or clean_policy.policy_id
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
