from __future__ import annotations

from dataclasses import dataclass
from ...domain import Box, OutputProtectionPlan, SeparatorBandObservation
from ...output.model import OutputGeometry
from ...units import ScanCalibration
from ..candidate.selection.model import SelectionResult
from ..evidence.exposure_overlap import ExposureOverlapEvidence
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
class FinalDetectionTrace:
    selection: SelectionResult
    exposure_overlap: ExposureOverlapEvidence


@dataclass(frozen=True)
class FinalDetection:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    confidence: float
    work_film_span: Box
    pitch: float
    decision_gate: DecisionGateAssessment
    decision_geometry: OutputGeometry
    output_geometry: OutputGeometry
    separator_observations: tuple[SeparatorBandObservation, ...]
    output_protection: OutputProtectionPlan
    scan_calibration: ScanCalibration
    diagnostics: tuple[str, ...]
    trace: FinalDetectionTrace | None

    def require_trace(self) -> FinalDetectionTrace:
        if self.trace is None:
            raise RuntimeError("final detection audit trace is unavailable")
        return self.trace

    @property
    def status(self) -> str:
        return "approved_auto" if self.decision_gate.passed else "needs_review"

    @property
    def final_review_reasons(self) -> tuple[str, ...]:
        return self.decision_gate.final_review_reasons
