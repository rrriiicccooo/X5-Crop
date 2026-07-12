from __future__ import annotations

from dataclasses import dataclass
from ...output.model import FrameBleedPlan, OutputGeometry
from ...units import ScanCalibration
from ..gate_checks import GateCheck


@dataclass(frozen=True)
class DecisionGateAssessment:
    checks: tuple[GateCheck, ...]

    @property
    def blocking_checks(self) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if check.blocks)

    @property
    def passed(self) -> bool:
        return not self.blocking_checks

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                check.final_review_reason
                for check in self.blocking_checks
                if check.final_review_reason is not None
            )
        )

    @property
    def reason_inputs(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (check.code, check.final_review_reason)
            for check in self.blocking_checks
            if check.final_review_reason is not None
        )


@dataclass(frozen=True)
class FinalDetection:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    decision_gate: DecisionGateAssessment
    decision_geometry: OutputGeometry
    output_geometry: OutputGeometry
    frame_bleed_plan: FrameBleedPlan
    scan_calibration: ScanCalibration
    diagnostics: tuple[str, ...]

    @property
    def status(self) -> str:
        return "approved_auto" if self.decision_gate.passed else "needs_review"

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return self.decision_gate.final_review_reasons
