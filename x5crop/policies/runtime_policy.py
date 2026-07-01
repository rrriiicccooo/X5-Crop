from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .runtime_base import (
    FULL,
    PARTIAL,
    CountPolicy,
    DetectorPolicy,
    DualLanePolicy,
    FrameFitPolicy,
)
from .runtime_candidate import (
    BaseDetectionScorePolicy,
    CandidateRunPolicy,
    ContentCandidateRunPolicy,
    ContentMismatchReviewSelectionPolicy,
    DarkBandCandidateRunPolicy,
    EqualFirstWideRetryPolicy,
    FallbackPolicy,
    GatePolicy,
    GeometrySupportScorePolicy,
    PartialEdgeHintPolicy,
    PartialHolderPolicy,
    PartialStopPolicy,
    ScoringPolicy,
    SelectionPolicy,
    SeparatorGeometryCompetitionPolicy,
    SeparatorSupportScorePolicy,
)
from .runtime_content import (
    ContentCandidatePolicy,
    ContentEvidencePolicy,
    ContentMaskPolicy,
    ContentPolicy,
    ContentProfilePolicy,
)
from .runtime_diagnostics import (
    DebugGapOverlayPolicy,
    DebugPanelPolicy,
    LuckyPassRiskPolicy,
    NearbySeparatorDiagnosticsPolicy,
    OverlapBleedRiskPolicy,
    ReportPolicy,
    RuntimeDiagnosticsPolicy,
)
from .runtime_final import (
    ApprovedGeometryAdjustmentPolicy,
    EdgeBleedProtectionPolicy,
    FinalizationPolicy,
    OutputPolicy,
)
from .runtime_outer import (
    ContentFloatingOuterPolicy,
    DarkBandOuterPolicy,
    EdgeAnchorOuterPolicy,
    FormatGeometryRetryPolicy,
    GridOuterRefinePolicy,
    OuterBoxDetectionPolicy,
    OuterContentAlignmentPolicy,
    OuterMaskProfilePolicy,
    OuterPolicy,
    SeparatorGeometryOuterPolicy,
    SeparatorOuterBandPolicy,
    ShortAxisAspectRetryPolicy,
)
from .runtime_separator import (
    EdgeRefineProfilePolicy,
    EnhancedSeparatorPolicy,
    GapSearchPolicy,
    HardGapTrustPolicy,
    LeadingGridFailurePolicy,
    NearbySeparatorCorrectionPolicy,
    RobustGridPolicy,
    SeparatorEdgePairPolicy,
    SeparatorGatePolicy,
    SeparatorGeometrySupportModePolicy,
    SeparatorGeometrySupportPolicy,
    SeparatorPolicy,
    SeparatorProfilePolicy,
)

if TYPE_CHECKING:
    from .parameters import FormatParameters


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
    candidate_run: CandidateRunPolicy
    finalization: FinalizationPolicy
    output: OutputPolicy = field(default_factory=OutputPolicy)
    diagnostics: RuntimeDiagnosticsPolicy = field(default_factory=RuntimeDiagnosticsPolicy)
    report: ReportPolicy = field(default_factory=ReportPolicy)
    notes: tuple[str, ...] = ()

    def report_detail(self) -> dict[str, Any]:
        from .reporting import detection_policy_report_detail

        return detection_policy_report_detail(self)


__all__ = [
    "FULL",
    "PARTIAL",
    "ApprovedGeometryAdjustmentPolicy",
    "BaseDetectionScorePolicy",
    "CandidateRunPolicy",
    "ContentCandidatePolicy",
    "ContentCandidateRunPolicy",
    "ContentEvidencePolicy",
    "ContentFloatingOuterPolicy",
    "ContentMaskPolicy",
    "ContentMismatchReviewSelectionPolicy",
    "ContentPolicy",
    "ContentProfilePolicy",
    "CountPolicy",
    "DarkBandCandidateRunPolicy",
    "DarkBandOuterPolicy",
    "DebugGapOverlayPolicy",
    "DebugPanelPolicy",
    "DetectionPolicy",
    "DetectorPolicy",
    "DualLanePolicy",
    "EdgeAnchorOuterPolicy",
    "EdgeBleedProtectionPolicy",
    "EdgeRefineProfilePolicy",
    "EnhancedSeparatorPolicy",
    "EqualFirstWideRetryPolicy",
    "FallbackPolicy",
    "FinalizationPolicy",
    "FormatGeometryRetryPolicy",
    "FrameFitPolicy",
    "GapSearchPolicy",
    "GatePolicy",
    "GeometrySupportScorePolicy",
    "GridOuterRefinePolicy",
    "HardGapTrustPolicy",
    "LeadingGridFailurePolicy",
    "LuckyPassRiskPolicy",
    "NearbySeparatorCorrectionPolicy",
    "NearbySeparatorDiagnosticsPolicy",
    "OuterBoxDetectionPolicy",
    "OuterContentAlignmentPolicy",
    "OuterMaskProfilePolicy",
    "OuterPolicy",
    "OutputPolicy",
    "OverlapBleedRiskPolicy",
    "PartialEdgeHintPolicy",
    "PartialHolderPolicy",
    "PartialStopPolicy",
    "ReportPolicy",
    "RobustGridPolicy",
    "RuntimeDiagnosticsPolicy",
    "ScoringPolicy",
    "SelectionPolicy",
    "SeparatorEdgePairPolicy",
    "SeparatorGatePolicy",
    "SeparatorGeometryCompetitionPolicy",
    "SeparatorGeometryOuterPolicy",
    "SeparatorGeometrySupportModePolicy",
    "SeparatorGeometrySupportPolicy",
    "SeparatorOuterBandPolicy",
    "SeparatorPolicy",
    "SeparatorProfilePolicy",
    "SeparatorSupportScorePolicy",
    "ShortAxisAspectRetryPolicy",
]
