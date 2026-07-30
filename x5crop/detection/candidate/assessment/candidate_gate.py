from __future__ import annotations

from ...gate_checks import GateCheck, GateRequirement, GateStage
from ..assessment.model import CandidateGateAssessment


def candidate_gate_assessment(
    *,
    scan_canvas_state,
    source_content_state,
    grid_search_coverage_state,
    frame_count_state,
    slot_ordinal_state,
    slot_ownership_state,
    known_content_containment_state,
    source_lane_geometry_state,
    output_protection_state,
    output_transform_state,
) -> CandidateGateAssessment:
    return CandidateGateAssessment(
        checks=(
            GateCheck(
                code="scan_canvas_authority",
                stage=GateStage.CANDIDATE,
                state=scan_canvas_state,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
            ),
            GateCheck(
                code="source_content_measurement",
                stage=GateStage.CANDIDATE,
                state=source_content_state,
                requirement=GateRequirement.NOT_CONTRADICTED,
            ),
            GateCheck(
                code="grid_search_coverage",
                stage=GateStage.CANDIDATE,
                state=grid_search_coverage_state,
                requirement=GateRequirement.NOT_CONTRADICTED,
            ),
            GateCheck(
                code="frame_count",
                stage=GateStage.CANDIDATE,
                state=frame_count_state,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
            ),
            GateCheck(
                code="slot_ordinal_assignment",
                stage=GateStage.CANDIDATE,
                state=slot_ordinal_state,
                requirement=GateRequirement.NOT_CONTRADICTED,
            ),
            GateCheck(
                code="slot_ownership",
                stage=GateStage.CANDIDATE,
                state=slot_ownership_state,
                requirement=GateRequirement.NOT_CONTRADICTED,
            ),
            GateCheck(
                code="known_content_containment",
                stage=GateStage.CANDIDATE,
                state=known_content_containment_state,
                requirement=GateRequirement.NOT_CONTRADICTED,
            ),
            GateCheck(
                code="source_lane_geometry",
                stage=GateStage.CANDIDATE,
                state=source_lane_geometry_state,
                requirement=GateRequirement.NOT_CONTRADICTED,
            ),
            GateCheck(
                code="output_protection",
                stage=GateStage.CANDIDATE,
                state=output_protection_state,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
            ),
            GateCheck(
                code="output_transform",
                stage=GateStage.CANDIDATE,
                state=output_transform_state,
                requirement=GateRequirement.NOT_CONTRADICTED,
            ),
        )
    )
