from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..common import Detection, ProcessResult, json_safe


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


def report_schema_for_detection(detection: Detection, result: ProcessResult | None = None) -> dict[str, Any]:
    output = {}
    if result is not None:
        output = {
            "status": result.status,
            "output_files": list(result.output_files),
            "review_copy": result.review_copy,
            "warnings": list(result.warnings),
        }
    schema = {
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
        "policy": detection.detail.get("policy", {}),
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
        "output": output,
    }
    return json_safe(schema)


__all__ = [
    "candidate_table",
    "gate_records",
    "report_schema_for_detection",
    "selected_candidate",
]
