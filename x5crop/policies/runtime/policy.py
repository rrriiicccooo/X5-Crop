from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import (
    CountPolicy,
    DetectorPolicy,
    FrameFitPolicy,
)
from .candidate import (
    CandidatePlanPolicy,
    PartialEdgeHintPolicy,
    PartialHolderPolicy,
    ScoringPolicy,
    SelectionPolicy,
)
from .content import ContentPolicy
from .diagnostics import RuntimeDiagnosticsPolicy
from .decision import RuntimeDecisionPolicy
from .final import FinalizationPolicy
from .outer import OuterPolicy
from .output import OutputPolicy
from .report import ReportPolicy
from .output_evidence import RuntimeOutputEvidencePolicy
from .preprocess import RuntimePreprocessPolicy
from .separator import SeparatorPolicy


@dataclass(frozen=True)
class DetectionPolicy:
    policy_id: str
    format_id: str
    strip_mode: str
    family: str
    preprocess: RuntimePreprocessPolicy
    detector: DetectorPolicy
    counts: CountPolicy
    outer: OuterPolicy
    separator: SeparatorPolicy
    content: ContentPolicy
    partial_holder: PartialHolderPolicy
    partial_edge_hint: PartialEdgeHintPolicy
    frame_fit: FrameFitPolicy
    scoring: ScoringPolicy
    candidate_selection: SelectionPolicy
    candidate_plan: CandidatePlanPolicy
    output_evidence: RuntimeOutputEvidencePolicy
    decision: RuntimeDecisionPolicy
    finalization: FinalizationPolicy
    output: OutputPolicy = field(default_factory=OutputPolicy)
    diagnostics: RuntimeDiagnosticsPolicy = field(default_factory=RuntimeDiagnosticsPolicy)
    report: ReportPolicy = field(default_factory=ReportPolicy)

    def report_detail(self) -> dict[str, Any]:
        from ..reporting import detection_policy_report_detail

        return detection_policy_report_detail(self)


__all__ = [
    "DetectionPolicy",
]
