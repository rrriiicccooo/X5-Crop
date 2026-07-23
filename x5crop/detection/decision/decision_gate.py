from __future__ import annotations

from ...output.model import FrameBleedPlan
from ..candidate.assessment.model import CandidateGateAssessment
from ..candidate.selection.model import SelectionConsensus, SelectionResult
from x5crop.domain import EvidenceState
from ..gate_checks import GateCheck, GateRequirement, GateStage
from ..evidence.scan_canvas import ScanCanvasEvidence
from ..evidence.transform_geometry import TransformGeometryEvidence
from .model import DECISION_GATE_REASON_BY_CODE, DecisionGateAssessment


def _decision_check(
    code: str,
    state: EvidenceState,
    requirement: GateRequirement,
) -> GateCheck:
    return GateCheck(
        code=code,
        stage=GateStage.DECISION,
        state=state,
        requirement=requirement,
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
                check.state,
                check.requirement,
            )
        )
    return tuple(checks)


def decision_gate_assessment(
    *,
    candidate_gate: CandidateGateAssessment | None,
    automatic_processing_eligibility: EvidenceState,
    selection_consensus: EvidenceState,
    output_protection: EvidenceState,
    scan_canvas_geometry: EvidenceState,
    transform_geometry: EvidenceState,
    count_resolution: EvidenceState,
    geometry_resolution: EvidenceState,
) -> DecisionGateAssessment:
    if automatic_processing_eligibility not in {
        EvidenceState.SUPPORTED,
        EvidenceState.CONTRADICTED,
    }:
        raise ValueError("automatic processing eligibility must be explicit")
    candidate_checks = (
        ()
        if automatic_processing_eligibility == EvidenceState.CONTRADICTED
        or candidate_gate is None
        else _project_candidate_checks(candidate_gate)
    )
    checks = (
        *candidate_checks,
        _decision_check(
            "count_resolution",
            count_resolution,
            (
                GateRequirement.NOT_CONTRADICTED
                if count_resolution == EvidenceState.NOT_APPLICABLE
                else GateRequirement.SUPPORTED_REQUIRED
            ),
        ),
        _decision_check(
            "geometry_resolution",
            geometry_resolution,
            (
                GateRequirement.NOT_CONTRADICTED
                if geometry_resolution == EvidenceState.NOT_APPLICABLE
                else GateRequirement.SUPPORTED_REQUIRED
            ),
        ),
        _decision_check(
            "automatic_processing_eligibility",
            automatic_processing_eligibility,
            GateRequirement.SUPPORTED_REQUIRED,
        ),
        _decision_check(
            "selection_geometry_consensus",
            selection_consensus,
            (
                GateRequirement.NOT_CONTRADICTED
                if selection_consensus == EvidenceState.NOT_APPLICABLE
                else GateRequirement.SUPPORTED_REQUIRED
            ),
        ),
        _decision_check(
            "output_content_protection",
            output_protection,
            (
                GateRequirement.NOT_CONTRADICTED
                if output_protection == EvidenceState.NOT_APPLICABLE
                else GateRequirement.SUPPORTED_REQUIRED
            ),
        ),
        _decision_check(
            "scan_canvas_geometry",
            scan_canvas_geometry,
            (
                GateRequirement.NOT_CONTRADICTED
                if scan_canvas_geometry == EvidenceState.NOT_APPLICABLE
                else GateRequirement.SUPPORTED_REQUIRED
            ),
        ),
        _decision_check(
            "transform_geometry_integrity",
            transform_geometry,
            GateRequirement.SUPPORTED_REQUIRED,
        ),
    )
    return DecisionGateAssessment(checks=checks)


def apply_decision_gate(
    selection: SelectionResult,
    frame_bleed_plan: FrameBleedPlan,
    scan_canvas_evidence: ScanCanvasEvidence,
    transform_geometry: TransformGeometryEvidence,
    *,
    automatic_processing_eligibility: EvidenceState,
) -> DecisionGateAssessment:
    selected = selection.selected
    candidate_gate = selected.assessment.gate
    resolution = selection.geometry_resolution
    if automatic_processing_eligibility == EvidenceState.SUPPORTED:
        count_resolution_state = (
            EvidenceState.SUPPORTED
            if (
                resolution.count_resolved
                and resolution.larger_count_search_complete
            )
            else EvidenceState.UNAVAILABLE
        )
        if (
            count_resolution_state != EvidenceState.SUPPORTED
            or selection.consensus == SelectionConsensus.DISAGREED
        ):
            geometry_resolution_state = EvidenceState.NOT_APPLICABLE
        elif resolution.state == EvidenceState.SUPPORTED:
            geometry_resolution_state = EvidenceState.SUPPORTED
        else:
            geometry_resolution_state = EvidenceState.UNAVAILABLE
        selection_consensus_state = (
            EvidenceState.CONTRADICTED
            if selection.consensus == SelectionConsensus.DISAGREED
            else EvidenceState.SUPPORTED
        )
        output_protection_state = (
            (
                EvidenceState.SUPPORTED
                if frame_bleed_plan.feasible
                else EvidenceState.CONTRADICTED
            )
            if resolution.supported
            else EvidenceState.NOT_APPLICABLE
        )
    else:
        count_resolution_state = EvidenceState.NOT_APPLICABLE
        geometry_resolution_state = EvidenceState.NOT_APPLICABLE
        selection_consensus_state = EvidenceState.NOT_APPLICABLE
        output_protection_state = EvidenceState.NOT_APPLICABLE
    scan_canvas_geometry_state = scan_canvas_evidence.state
    transform_geometry_state = transform_geometry.state
    decision_gate = decision_gate_assessment(
        candidate_gate=candidate_gate,
        automatic_processing_eligibility=automatic_processing_eligibility,
        selection_consensus=selection_consensus_state,
        output_protection=output_protection_state,
        scan_canvas_geometry=scan_canvas_geometry_state,
        transform_geometry=transform_geometry_state,
        count_resolution=count_resolution_state,
        geometry_resolution=geometry_resolution_state,
    )
    return decision_gate
