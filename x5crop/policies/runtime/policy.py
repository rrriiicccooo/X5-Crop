from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...formats import FormatPhysicalSpec
from .base import (
    CountHypothesisPolicy,
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
from .exposure_overlap import ExposureOverlapEvidencePolicy
from .preprocess import RuntimePreprocessPolicy
from .separator import SeparatorPolicy


@dataclass(frozen=True)
class DetectionPolicy:
    policy_id: str
    physical_spec: FormatPhysicalSpec
    strip_mode: str
    preprocess: RuntimePreprocessPolicy
    detector: DetectorPolicy
    count_hypotheses: CountHypothesisPolicy
    outer: OuterPolicy
    separator: SeparatorPolicy
    content: ContentPolicy
    partial_holder: PartialHolderPolicy
    partial_edge_hint: PartialEdgeHintPolicy
    frame_fit: FrameFitPolicy
    scoring: ScoringPolicy
    candidate_selection: SelectionPolicy
    candidate_plan: CandidatePlanPolicy
    exposure_overlap_evidence: ExposureOverlapEvidencePolicy
    decision: RuntimeDecisionPolicy
    finalization: FinalizationPolicy
    output: OutputPolicy
    diagnostics: RuntimeDiagnosticsPolicy
    report: ReportPolicy

    def report_detail(self) -> dict[str, Any]:
        from ..reporting import detection_policy_report_detail

        return detection_policy_report_detail(self)


__all__ = [
    "DetectionPolicy",
]
