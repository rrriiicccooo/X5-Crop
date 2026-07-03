from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .runtime_base import (
    CountPolicy,
    DetectorPolicy,
    FrameFitPolicy,
)
from .runtime_candidate import (
    CandidatePlanPolicy,
    GatePolicy,
    PartialEdgeHintPolicy,
    PartialHolderPolicy,
    ScoringPolicy,
    SelectionPolicy,
)
from .runtime_content import ContentPolicy
from .runtime_diagnostics import (
    ReportPolicy,
    RuntimeDiagnosticsPolicy,
)
from .runtime_final import (
    FinalizationPolicy,
    OutputPolicy,
)
from .runtime_outer import OuterPolicy
from .runtime_separator import SeparatorPolicy

if TYPE_CHECKING:
    from .parameter_aggregate import FormatParameters


@dataclass(frozen=True)
class DetectionPolicy:
    policy_id: str
    format_id: str
    strip_mode: str
    family: str
    role: str
    detector: DetectorPolicy
    source_parameters: FormatParameters
    counts: CountPolicy
    outer: OuterPolicy
    separator: SeparatorPolicy
    content: ContentPolicy
    partial_holder: PartialHolderPolicy
    partial_edge_hint: PartialEdgeHintPolicy
    frame_fit: FrameFitPolicy
    gates: GatePolicy
    scoring: ScoringPolicy
    candidate_selection: SelectionPolicy
    candidate_plan: CandidatePlanPolicy
    finalization: FinalizationPolicy
    output: OutputPolicy = field(default_factory=OutputPolicy)
    diagnostics: RuntimeDiagnosticsPolicy = field(default_factory=RuntimeDiagnosticsPolicy)
    report: ReportPolicy = field(default_factory=ReportPolicy)
    notes: tuple[str, ...] = ()

    def report_detail(self) -> dict[str, Any]:
        from .reporting import detection_policy_report_detail

        return detection_policy_report_detail(self)


__all__ = [
    "DetectionPolicy",
]
