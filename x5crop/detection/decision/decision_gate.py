from __future__ import annotations

from ...output.model import FrameBleedPlan
from ..candidate.assessment.model import CandidateGateAssessment
from ..candidate.selection.model import SelectionConsensus, SelectionResult
from x5crop.domain import EvidenceState
from ..gate_checks import GateCheck, GateStage
from ..evidence.transform_geometry import TransformGeometryEvidence
from .model import DECISION_GATE_REASON_BY_CODE, DecisionGateAssessment


def _decision_check(
    code: str,
    state: EvidenceState,
) -> GateCheck:
    return GateCheck(
        code=code,
        stage=GateStage.DECISION,
        state=state,
        final_review_reason=DECISION_GATE_REASON_BY_CODE[code],
    )


def _project_candidate_checks(
    candidate_gate: CandidateGateAssessment,
) -> tuple[GateCheck, ...]:
    checks: list[GateCheck] = []
    for check in candidate_gate.checks:
        if not check.blocks:
            continue
        code = f"candidate_{check.code}"
        if code not in DECISION_GATE_REASON_BY_CODE:
            raise ValueError(f"unowned candidate gate check: {check.code}")
        checks.append(
            _decision_check(
                code,
                EvidenceState.CONTRADICTED,
            )
        )
    return tuple(checks)


def decision_gate_assessment(
    *,
    candidate_gate: CandidateGateAssessment | None,
    automatic_processing: EvidenceState,
    selection_consensus: EvidenceState,
    output_protection: EvidenceState,
    transform_geometry: EvidenceState,
    count_resolution: EvidenceState,
    geometry_resolution: EvidenceState,
) -> DecisionGateAssessment:
    if (
        automatic_processing != EvidenceState.CONTRADICTED
        and candidate_gate is None
    ):
        raise ValueError("automatic processing requires CandidateGate")
    candidate_checks = (
        ()
        if automatic_processing == EvidenceState.CONTRADICTED
        or candidate_gate is None
        else _project_candidate_checks(candidate_gate)
    )
    checks = (
        *candidate_checks,
        _decision_check(
            "count_resolution",
            count_resolution,
        ),
        _decision_check(
            "geometry_resolution",
            geometry_resolution,
        ),
        _decision_check(
            "automatic_processing_eligibility",
            automatic_processing,
        ),
        _decision_check(
            "selection_geometry_consensus",
            selection_consensus,
        ),
        _decision_check(
            "output_content_protection",
            output_protection,
        ),
        _decision_check(
            "transform_geometry_integrity",
            transform_geometry,
        ),
    )
    return DecisionGateAssessment(checks=checks)


def apply_decision_gate(
    selection: SelectionResult,
    frame_bleed_plan: FrameBleedPlan,
    transform_geometry: TransformGeometryEvidence,
) -> DecisionGateAssessment:
    selected = selection.selected
    candidate_gate = selected.assessment.gate
    resolution = selection.geometry_resolution
    automatic_processing_state = (
        EvidenceState.SUPPORTED
        if selected.geometry.automatic_processing_supported
        else EvidenceState.CONTRADICTED
    )
    final_stage_applicable = bool(
        automatic_processing_state == EvidenceState.SUPPORTED
        and candidate_gate is not None
        and candidate_gate.passed
    )
    if final_stage_applicable:
        count_resolution_state = (
            EvidenceState.SUPPORTED
            if (
                resolution.count_resolved
                and resolution.larger_count_hypotheses_resolved
            )
            else EvidenceState.CONTRADICTED
        )
        if (
            count_resolution_state != EvidenceState.SUPPORTED
            or selection.consensus == SelectionConsensus.DISAGREED
        ):
            geometry_resolution_state = EvidenceState.NOT_APPLICABLE
        elif resolution.state == EvidenceState.SUPPORTED:
            geometry_resolution_state = EvidenceState.SUPPORTED
        else:
            geometry_resolution_state = EvidenceState.CONTRADICTED
        selection_consensus_state = (
            EvidenceState.CONTRADICTED
            if selection.consensus == SelectionConsensus.DISAGREED
            else EvidenceState.SUPPORTED
        )
        output_protection_state = (
            EvidenceState.SUPPORTED
            if frame_bleed_plan.feasible
            else EvidenceState.CONTRADICTED
        )
        transform_geometry_state = transform_geometry.state
    else:
        count_resolution_state = EvidenceState.NOT_APPLICABLE
        geometry_resolution_state = EvidenceState.NOT_APPLICABLE
        selection_consensus_state = EvidenceState.NOT_APPLICABLE
        output_protection_state = EvidenceState.NOT_APPLICABLE
        transform_geometry_state = EvidenceState.NOT_APPLICABLE
    decision_gate = decision_gate_assessment(
        candidate_gate=candidate_gate,
        automatic_processing=automatic_processing_state,
        selection_consensus=selection_consensus_state,
        output_protection=output_protection_state,
        transform_geometry=transform_geometry_state,
        count_resolution=count_resolution_state,
        geometry_resolution=geometry_resolution_state,
    )
    return decision_gate
