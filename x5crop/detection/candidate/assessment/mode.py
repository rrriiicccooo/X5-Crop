from __future__ import annotations

from typing import Any

from ....domain import DetectionCandidate
from ...detail import candidate_signals_from_detail
from ...gate_checks import GateCheck
from .candidate_gate import CandidateGateAssessment, candidate_signal_gate_checks


def apply_mode_candidate_assessment(
    detection: DetectionCandidate,
    *,
    source: str,
    source_auto_allowed: bool,
    component_candidate_gates: list[dict[str, Any]],
) -> DetectionCandidate:
    checks = [
        GateCheck(
            code="candidate_source_auto_allowed",
            stage="candidate",
            bucket="source",
            passed=source_auto_allowed,
            severity="blocker",
            signal=(
                "candidate_source_allowed"
                if source_auto_allowed
                else "candidate_source_not_auto_allowed"
            ),
            detail={"source": source},
        ),
        GateCheck(
            code="component_candidate_gates",
            stage="candidate",
            bucket="composition",
            passed=all(bool(gate.get("passed", False)) for gate in component_candidate_gates),
            severity="blocker",
            signal="component_candidate_gate_failed",
            detail={"component_count": len(component_candidate_gates)},
        ),
        *candidate_signal_gate_checks(candidate_signals_from_detail(detection)),
    ]
    blockers = sorted(
        {
            check.signal
            for check in checks
            if not check.passed and check.severity == "blocker"
        }
    )
    diagnostics = sorted(
        {
            check.signal
            for check in checks
            if not check.passed and check.severity == "diagnostic"
        }
    )
    gate = CandidateGateAssessment(
        passed=not blockers,
        checks=checks,
        blockers=blockers,
        diagnostics=diagnostics,
    )
    detection.detail["candidate_assessment"] = {
        "source": source,
        "candidate_gate": gate.report_detail(),
        "blockers": blockers,
        "diagnostics": diagnostics,
    }
    return detection
