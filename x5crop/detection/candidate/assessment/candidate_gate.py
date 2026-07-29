from __future__ import annotations

from ...gate_checks import GateCheck, GateRequirement, GateStage
from ..assessment.model import CandidateGateAssessment
from ...source_core import SourceCoreEvidence


def candidate_gate_assessment(
    source_core: SourceCoreEvidence,
) -> CandidateGateAssessment:
    return CandidateGateAssessment(
        checks=(
            GateCheck(
                code="scan_canvas_authority",
                stage=GateStage.CANDIDATE,
                state=source_core.scan_canvas_state,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
            ),
            GateCheck(
                code="source_content_measurement",
                stage=GateStage.CANDIDATE,
                state=source_core.content_state,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
            ),
            GateCheck(
                code="frame_grid_authority",
                stage=GateStage.CANDIDATE,
                state=source_core.grid.state,
                requirement=GateRequirement.SUPPORTED_REQUIRED,
            ),
        )
    )
