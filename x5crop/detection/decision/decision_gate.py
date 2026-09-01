from __future__ import annotations

from ...domain import EvidenceState
from ..candidate.assessment.model import CandidateGateAssessment
from ..gate_checks import (
    GATE_CHECK_DEPENDENCIES,
    GateCheck,
    GateGap,
    GateStage,
)
from .model import DecisionGateAssessment
from .vocabulary import (
    FINAL_REASON_ADJACENCY_CONTINUITY_UNRESOLVED,
    FINAL_REASON_ADJACENCY_TOPOLOGY_UNRESOLVED,
    FINAL_REASON_CONTENT_PROTECTION_CONFLICT,
    FINAL_REASON_DIRECT_USE_BUDGET_EXCEEDED,
    FINAL_REASON_ADJACENCY_RELATION_UNRESOLVED,
    FINAL_REASON_NO_LEGAL_PLACEMENT,
    FINAL_REASON_PLACEMENT_UNRESOLVED,
    FINAL_REASON_PRODUCER_BOUND_EXCEEDED,
    FINAL_REASON_SOURCE_LANE_AUTHORITY_UNAVAILABLE,
)


_REASON_BY_GAP = {
    GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.HOLDER_FULL_COUNT_UNRESOLVED: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.HOLDER_IDENTITY_UNRESOLVED: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.UNSUPPORTED_DUAL_COUNT: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.COMPLETE_PLACEMENT_UNAVAILABLE: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.SOURCE_SCAN_GEOMETRY_UNAVAILABLE: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.PLACEMENT_UNRESOLVED: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.PHASE_ANCHOR_UNAVAILABLE: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.GLOBAL_LATTICE_AUTHORITY_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.CALIBRATED_NOMINAL_GRID_AUTHORITY_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.CALIBRATED_NOMINAL_GRID_CONFLICT: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.NOMINAL_GRID_PHASE_ANCHOR_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.ADJACENCY_OBSERVATION_COVERAGE_INCOMPLETE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.DIRECT_ROLE_BINDING_AUTHORITY_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.DIRECT_ROLE_APERTURE_DOMAIN_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.SEPARATOR_MATERIAL_CONFLICT: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.OUTER_FRAME_OBSERVATION_AUTHORITY_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.SOURCE_FRAME_WIDTH_CONFLICT: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.PHASE_TEMPLATE_MISMATCH: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.PHASE_PLACEMENT_AMBIGUOUS: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.CROSS_AUTHORITY_UNAVAILABLE: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.APERTURE_ASPECT_RATIO_AUTHORITY_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.APERTURE_ASPECT_RATIO_PHYSICAL_PRIOR_CONFLICT: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.APERTURE_ASPECT_RATIO_DIRECT_CONFLICT: (
        FINAL_REASON_PLACEMENT_UNRESOLVED
    ),
    GateGap.APERTURE_ASPECT_RATIO_BUDGET_EXHAUSTED: (
        FINAL_REASON_DIRECT_USE_BUDGET_EXCEEDED
    ),
    GateGap.SHARED_AUTHORITY_UNAVAILABLE: FINAL_REASON_PLACEMENT_UNRESOLVED,
    GateGap.CONTENT_VETO_REJECTED: FINAL_REASON_CONTENT_PROTECTION_CONFLICT,
    GateGap.ADJACENCY_RELATION_UNRESOLVED: (
        FINAL_REASON_ADJACENCY_RELATION_UNRESOLVED
    ),
    GateGap.ADJACENCY_CONTINUITY_UNRESOLVED: (
        FINAL_REASON_ADJACENCY_CONTINUITY_UNRESOLVED
    ),
    GateGap.ADJACENCY_TOPOLOGY_UNRESOLVED: (
        FINAL_REASON_ADJACENCY_TOPOLOGY_UNRESOLVED
    ),
    GateGap.DUAL_LANE_NOT_FILLED: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.DUAL_LANE_FILL_UNRESOLVED: FINAL_REASON_NO_LEGAL_PLACEMENT,
    GateGap.SOURCE_LANE_AUTHORITY_INVALID: (
        FINAL_REASON_SOURCE_LANE_AUTHORITY_UNAVAILABLE
    ),
    GateGap.OUTPUT_FOOTPRINT_UNAVAILABLE: (
        FINAL_REASON_SOURCE_LANE_AUTHORITY_UNAVAILABLE
    ),
    GateGap.PRODUCER_BOUND_EXCEEDED: FINAL_REASON_PRODUCER_BOUND_EXCEEDED,
    GateGap.DIRECT_USE_BUDGET_EXCEEDED: (
        FINAL_REASON_DIRECT_USE_BUDGET_EXCEEDED
    ),
    GateGap.DIRECT_USE_BUDGET_UNAVAILABLE: (
        FINAL_REASON_NO_LEGAL_PLACEMENT
    ),
}


def apply_decision_gate(
    candidate_gate: CandidateGateAssessment,
) -> DecisionGateAssessment:
    candidate_by_code = {check.code: check for check in candidate_gate.checks}
    decision_checks: list[GateCheck] = []
    decision_by_code: dict[str, GateCheck] = {}
    for check in candidate_gate.checks:
        dependencies = GATE_CHECK_DEPENDENCIES.get(check.code, ())
        evaluated = check.evaluated and not any(
            decision_by_code.get(code, candidate_by_code[code]).state
            != EvidenceState.SUPPORTED
            for code in dependencies
        )
        if not evaluated:
            resolved = GateCheck(
                code=check.code,
                stage=GateStage.DECISION,
                state=EvidenceState.UNAVAILABLE,
                evaluated=False,
            )
        else:
            resolved = GateCheck(
                code=check.code,
                stage=GateStage.DECISION,
                state=check.state,
                gap=check.gap,
                failure=check.failure,
                final_review_reason=(
                    _REASON_BY_GAP[check.gap]
                    if check.blocks and check.gap is not None
                    else None
                ),
            )
        decision_checks.append(resolved)
        decision_by_code[check.code] = resolved
    return DecisionGateAssessment(
        checks=tuple(decision_checks)
    )
