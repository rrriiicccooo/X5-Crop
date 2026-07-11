from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
from ...evidence.state import EvidenceState
from .candidate_gate import BoundaryProofPath, CandidateGateInput, candidate_gate_assessment


def apply_mode_candidate_assessment(
    detection: DetectionCandidate,
    *,
    source: str,
    automatic_processing_supported: bool,
    component_candidate_gates: list[dict[str, Any]],
) -> DetectionCandidate:
    components_supported = all(
        bool(gate.get("passed", False)) for gate in component_candidate_gates
    )
    topology_state = (
        EvidenceState.NOT_APPLICABLE
        if not automatic_processing_supported
        else (
            EvidenceState.SUPPORTED
            if len(detection.frames) == detection.count
            else EvidenceState.CONTRADICTED
        )
    )
    proof_supported = bool(
        not automatic_processing_supported
        or (components_supported and topology_state == EvidenceState.SUPPORTED)
    )
    gate = candidate_gate_assessment(
        CandidateGateInput(
            frame_topology=topology_state,
            content_preservation=EvidenceState.NOT_APPLICABLE,
            photo_geometry=EvidenceState.NOT_APPLICABLE,
            evidence_independence=EvidenceState.NOT_APPLICABLE,
            proof_paths=(
                BoundaryProofPath(
                    code="mode_composition",
                    state=(
                        EvidenceState.SUPPORTED
                        if proof_supported
                        else EvidenceState.CONTRADICTED
                    ),
                    detail={"component_count": len(component_candidate_gates)},
                ),
            ),
        )
    )
    detection.detail["automatic_processing_supported"] = bool(
        automatic_processing_supported
    )
    detection.detail["candidate_assessment"] = {
        "source": source,
        "candidate_gate": gate.report_detail(),
        "failed_checks": list(gate.failed_checks),
        "diagnostics": list(detection.detail.get("mode_diagnostics", [])),
    }
    return detection
