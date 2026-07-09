from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import SeparatorWidthProfileSearchParameters
from ...image.deskew_parameters import DeskewParameters
from .base import PartialCountParameters, PartialEdgeHintParameters
from .content import (
    ContentCandidateParameters,
    ContentEvidenceParameters,
    ContentMaskParameters,
    ContentProfileParameters,
    ContentSupportParameters,
)
from .decision import DecisionReviewParameters
from .diagnostics import DebugGapOverlayParameters, NearbySeparatorDiagnosticsParameters
from .finalization import ApprovedGeometryAdjustmentParameters, PartialHolderParameters
from .outer import (
    BaseOuterCandidateParameters,
    ContentContainmentCorrectionParameters,
    EdgeAnchoredContentPositionParameters,
    FloatingContentPositionParameters,
    FullWidthSeparatorOuterParameters,
    GridOuterRefineParameters,
    LongAxisGeometryCorrectionParameters,
    OuterStrategyParameters,
    SeparatorOuterBandParameters,
    ShortAxisGeometryCorrectionParameters,
)
from .output_evidence import OutputOverlapEvidenceParameters
from .scoring import (
    BaseDetectionScoreParameters,
    CandidateCompetitionParameters,
    GeometrySupportScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)
from .separator import (
    EdgeRefineProfileParameters,
    GapSearchParameters,
    HardGapTrustParameters,
    LeadingGridFailureParameters,
    NearbySeparatorRefinementParameters,
    SeparatorGeometrySupportParameters,
    SeparatorProfileParameters,
    SeparatorSupportParameters,
    SeparatorWidthProfileParameters,
)


@dataclass(frozen=True)
class PreprocessParameters:
    deskew: DeskewParameters = field(default_factory=DeskewParameters)


@dataclass(frozen=True)
class ContentParameters:
    content_evidence: ContentEvidenceParameters = field(default_factory=ContentEvidenceParameters)
    content_profile: ContentProfileParameters = field(default_factory=ContentProfileParameters)
    content_mask: ContentMaskParameters = field(default_factory=ContentMaskParameters)
    content_candidate: ContentCandidateParameters = field(default_factory=ContentCandidateParameters)
    content_support: ContentSupportParameters = field(default_factory=ContentSupportParameters)


@dataclass(frozen=True)
class OuterParameters:
    outer_strategy: OuterStrategyParameters = field(default_factory=OuterStrategyParameters)
    floating_content_position: FloatingContentPositionParameters = field(default_factory=FloatingContentPositionParameters)
    edge_anchored_content_position: EdgeAnchoredContentPositionParameters = field(default_factory=EdgeAnchoredContentPositionParameters)
    base_outer_candidates: BaseOuterCandidateParameters = field(default_factory=BaseOuterCandidateParameters)
    separator_outer_band: SeparatorOuterBandParameters = field(default_factory=SeparatorOuterBandParameters)
    separator_full_width_outer: FullWidthSeparatorOuterParameters = field(default_factory=FullWidthSeparatorOuterParameters)
    long_axis_geometry_correction: LongAxisGeometryCorrectionParameters = field(default_factory=LongAxisGeometryCorrectionParameters)
    grid_outer_refine: GridOuterRefineParameters = field(default_factory=GridOuterRefineParameters)
    short_axis_geometry_correction: ShortAxisGeometryCorrectionParameters = field(default_factory=ShortAxisGeometryCorrectionParameters)
    content_containment_correction: ContentContainmentCorrectionParameters = field(default_factory=ContentContainmentCorrectionParameters)


@dataclass(frozen=True)
class SeparatorParameters:
    separator_support: SeparatorSupportParameters = field(default_factory=SeparatorSupportParameters)
    leading_grid_failure: LeadingGridFailureParameters = field(default_factory=LeadingGridFailureParameters)
    separator_geometry_support: SeparatorGeometrySupportParameters = field(default_factory=SeparatorGeometrySupportParameters)
    separator_width_profile: SeparatorWidthProfileParameters = field(default_factory=SeparatorWidthProfileParameters)
    separator_width_profile_search: SeparatorWidthProfileSearchParameters = field(default_factory=SeparatorWidthProfileSearchParameters)
    nearby_separator_refinement: NearbySeparatorRefinementParameters = field(default_factory=NearbySeparatorRefinementParameters)
    gap_search: GapSearchParameters = field(default_factory=GapSearchParameters)
    separator_profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)
    edge_refine_profile: EdgeRefineProfileParameters = field(default_factory=EdgeRefineProfileParameters)
    hard_gap_trust: HardGapTrustParameters = field(default_factory=HardGapTrustParameters)


@dataclass(frozen=True)
class CandidateParameters:
    partial_counts: PartialCountParameters = field(default_factory=PartialCountParameters)
    partial_edge_hint: PartialEdgeHintParameters = field(default_factory=PartialEdgeHintParameters)
    partial_holder: PartialHolderParameters = field(default_factory=PartialHolderParameters)
    scoring_calibration: ScoringCalibrationParameters = field(default_factory=ScoringCalibrationParameters)
    base_detection_score: BaseDetectionScoreParameters = field(default_factory=BaseDetectionScoreParameters)
    separator_support_score: SeparatorSupportScoreParameters = field(default_factory=SeparatorSupportScoreParameters)
    geometry_support_score: GeometrySupportScoreParameters = field(default_factory=GeometrySupportScoreParameters)
    candidate_competition: CandidateCompetitionParameters = field(default_factory=CandidateCompetitionParameters)


@dataclass(frozen=True)
class DecisionParameters:
    decision_review: DecisionReviewParameters = field(default_factory=DecisionReviewParameters)


@dataclass(frozen=True)
class OutputParameters:
    output_overlap: OutputOverlapEvidenceParameters = field(default_factory=OutputOverlapEvidenceParameters)
    approved_geometry_adjustment: ApprovedGeometryAdjustmentParameters = field(default_factory=ApprovedGeometryAdjustmentParameters)


@dataclass(frozen=True)
class DiagnosticsParameters:
    debug_gap_overlay: DebugGapOverlayParameters = field(default_factory=DebugGapOverlayParameters)
    nearby_separator_diagnostics: NearbySeparatorDiagnosticsParameters = field(default_factory=NearbySeparatorDiagnosticsParameters)


@dataclass(frozen=True)
class FormatParameters:
    name: str
    preprocess: PreprocessParameters = field(default_factory=PreprocessParameters)
    content: ContentParameters = field(default_factory=ContentParameters)
    outer: OuterParameters = field(default_factory=OuterParameters)
    separator: SeparatorParameters = field(default_factory=SeparatorParameters)
    candidate: CandidateParameters = field(default_factory=CandidateParameters)
    decision: DecisionParameters = field(default_factory=DecisionParameters)
    output: OutputParameters = field(default_factory=OutputParameters)
    diagnostics: DiagnosticsParameters = field(default_factory=DiagnosticsParameters)


__all__ = [
    "CandidateParameters",
    "ContentParameters",
    "DecisionParameters",
    "DiagnosticsParameters",
    "FormatParameters",
    "OuterParameters",
    "OutputParameters",
    "PreprocessParameters",
    "SeparatorParameters",
]
