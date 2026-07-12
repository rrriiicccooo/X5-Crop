from __future__ import annotations

from dataclasses import dataclass
from ...output.model import FrameBleedPlan, OutputGeometry
from ...strip_modes import FULL, PARTIAL
from ...units import ScanCalibration
from ..gate_checks import GateCheck


@dataclass(frozen=True)
class DecisionGateAssessment:
    checks: tuple[GateCheck, ...]

    def __post_init__(self) -> None:
        if not self.checks:
            raise ValueError("decision gate requires checks")
        if any(check.stage != "decision" for check in self.checks):
            raise ValueError("decision gate can contain only decision-stage checks")
        codes = tuple(check.code for check in self.checks)
        if len(set(codes)) != len(codes):
            raise ValueError("decision gate check codes must be unique")

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

    def __post_init__(self) -> None:
        if not self.format_id:
            raise ValueError("final detection requires a format identity")
        if self.layout not in {"horizontal", "vertical"}:
            raise ValueError(f"unsupported final detection layout: {self.layout}")
        if self.strip_mode not in {FULL, PARTIAL}:
            raise ValueError(
                f"unsupported final detection strip mode: {self.strip_mode}"
            )
        if self.count <= 0:
            raise ValueError("final detection count must be positive")
        if (
            self.decision_geometry.crop_envelope
            != self.output_geometry.crop_envelope
        ):
            raise ValueError("final output must preserve the decision crop envelope")
        decision_frame_count = len(self.decision_geometry.frames)
        if decision_frame_count not in {0, self.count}:
            raise ValueError("final detection has incomplete decision frames")
        if self.decision_gate.passed and decision_frame_count != self.count:
            raise ValueError("approved final detection requires one frame per count")
        if len(self.output_geometry.frames) != decision_frame_count:
            raise ValueError("final output must preserve decision frame identity")
        if len(self.frame_bleed_plan.frame_sides) != decision_frame_count:
            raise ValueError("final bleed plan must match decision frames")
        if any(not item for item in self.diagnostics) or len(
            set(self.diagnostics)
        ) != len(self.diagnostics):
            raise ValueError("final diagnostics must be non-empty and unique")

    @property
    def status(self) -> str:
        return "approved_auto" if self.decision_gate.passed else "needs_review"

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return self.decision_gate.final_review_reasons
