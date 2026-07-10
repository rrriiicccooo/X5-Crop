from __future__ import annotations

from dataclasses import dataclass

from ...formats import FormatPhysicalSpec
from ..parameters.base import PartialEdgeHintParameters
from ..parameters.candidate import CandidatePlanParameters, FrameFitParameters
from ..parameters.decision import DecisionEvidenceParameters, DecisionReviewParameters
from ..parameters.exposure_overlap import ExposureOverlapEvidenceParameters
from ..parameters.scoring import CandidateCompetitionParameters
from .base import (
    CountHypothesisPolicy,
    DetectorPolicy,
)
from .candidate import (
    PartialHolderPolicy,
    ScoringPolicy,
)
from .content import ContentPolicy
from .diagnostics import RuntimeDiagnosticsPolicy
from .final import FinalizationPolicy
from .outer import OuterPolicy
from .output import OutputPolicy
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
    partial_edge_hint: PartialEdgeHintParameters
    frame_fit: FrameFitParameters
    scoring: ScoringPolicy
    candidate_selection: CandidateCompetitionParameters
    candidate_plan: CandidatePlanParameters
    exposure_overlap_evidence: ExposureOverlapEvidenceParameters
    decision_evidence: DecisionEvidenceParameters
    decision: DecisionReviewParameters
    finalization: FinalizationPolicy
    output: OutputPolicy
    diagnostics: RuntimeDiagnosticsPolicy
