from __future__ import annotations

from ...physical.model import DualLaneSolution
from ..model import (
    AssessedCandidate,
    BuiltCandidate,
    CandidateAssessment,
    CandidateEvidence,
    DualLaneEvidence,
    _combined_evidence_state,
    boundary_proof_paths_for_dual_lane,
)
from .candidate_gate import (
    CandidateGateInput,
    candidate_gate_assessment,
)


def assess_dual_lane_candidate(
    candidate: BuiltCandidate,
    lanes: tuple[AssessedCandidate, ...],
    *,
    lane_geometry_resolved: tuple[bool, ...],
) -> AssessedCandidate:
    geometry = candidate.geometry
    if not isinstance(geometry, DualLaneSolution):
        raise ValueError("dual-lane assessment requires dual-lane geometry")
    if len(lanes) <= 1 or len(lane_geometry_resolved) != len(lanes):
        raise ValueError("dual-lane assessment requires one resolution per lane")
    if len(geometry.lane_solutions) != len(lanes):
        raise ValueError("dual-lane assessment must match component geometry")
    if tuple(lane.geometry for lane in lanes) != geometry.lane_solutions:
        raise ValueError("dual-lane assessment requires exact component geometry")
    lane_evidence = tuple(lane.assessment.evidence for lane in lanes)
    lane_gates = tuple(lane.assessment.gate for lane in lanes)
    if not all(isinstance(evidence, CandidateEvidence) for evidence in lane_evidence):
        raise ValueError("dual-lane components require standard physical evidence")
    if any(gate is None for gate in lane_gates):
        raise ValueError("dual-lane components require CandidateGate")
    physical_evidence = tuple(
        evidence for evidence in lane_evidence if isinstance(evidence, CandidateEvidence)
    )
    physical_gates = tuple(gate for gate in lane_gates if gate is not None)
    dual_lane_evidence = DualLaneEvidence(
        physical_evidence,
        physical_gates,
        lane_geometry_resolved,
    )
    diagnostics = tuple(
        dict.fromkeys(
            (
                *candidate.build_diagnostics,
                *(item for gate in physical_gates for item in gate.diagnostics),
            )
        )
    )
    gate = candidate_gate_assessment(
        CandidateGateInput(
            content_preservation=_combined_evidence_state(
                tuple(item.content_preservation_state for item in physical_evidence)
            ),
            photo_geometry=_combined_evidence_state(
                tuple(item.frame_dimensions.state for item in physical_evidence)
            ),
            sequence_conservation=_combined_evidence_state(
                tuple(
                    item.sequence_conservation.state
                    for item in physical_evidence
                )
            ),
            evidence_independence=_combined_evidence_state(
                tuple(item.independence.state for item in physical_evidence)
            ),
            proof_paths=boundary_proof_paths_for_dual_lane(
                geometry,
                dual_lane_evidence,
            ),
            diagnostics=diagnostics,
        )
    )
    return AssessedCandidate(
        geometry=geometry,
        count_hypothesis=candidate.count_hypothesis,
        assessment=CandidateAssessment(
            evidence=dual_lane_evidence,
            gate=gate,
        ),
    )
