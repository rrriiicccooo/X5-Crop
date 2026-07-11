from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate


def candidate_reliability_detail(detection: DetectionCandidate) -> dict[str, Any]:
    assessment = detection.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    gate = assessment.get("candidate_gate", {})
    gate = dict(gate) if isinstance(gate, dict) else {}
    proof_paths = gate.get("proof_paths", [])
    supported_paths = [
        str(path.get("code"))
        for path in proof_paths
        if isinstance(path, dict) and path.get("state") == "supported"
    ]
    reliable = bool(gate.get("passed", False) and supported_paths)
    return {
        "reliable": reliable,
        "supported_proof_paths": supported_paths,
        "confidence": float(detection.confidence),
        "confidence_role": "candidate_ranking_only",
    }


def candidate_is_reliable_for_execution_budget(detection: DetectionCandidate) -> bool:
    return bool(candidate_reliability_detail(detection)["reliable"])
