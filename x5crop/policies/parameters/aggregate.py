from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import (
    EdgePairParameters,
    EdgeRefineProfileParameters,
    GapSearchParameters,
    HardGapTrustParameters,
    NearbySeparatorRefinementParameters,
    OuterBoxDetectionParameters,
    SeparatorProfileParameters,
    SeparatorWidthProfileSearchParameters,
)
from ...image.deskew_parameters import DeskewParameters
from .base import PartialCountParameters
from .candidate import CandidatePlanParameters
from .content import (
    ContentEvidenceParameters,
    ContentMaskParameters,
    ContentProfileParameters,
    ContentSupportParameters,
)
from .diagnostics import DebugGapOverlayParameters
from .finalization import ApprovedGeometryAdjustmentParameters
from .outer import (
    ContentContainmentCorrectionParameters,
    EdgeAnchoredContentPositionParameters,
    FloatingContentPositionParameters,
    FullWidthSeparatorOuterParameters,
    LongAxisGeometryCorrectionParameters,
    OuterAlignmentEvidenceParameters,
    OuterStrategyParameters,
    SeparatorOuterBandParameters,
    ShortAxisGeometryCorrectionParameters,
)
from .exposure_overlap import (
    EdgeBleedProtectionParameters,
    ExposureOverlapEvidenceParameters,
    ExposureOverlapProtectionParameters,
)
from .scoring import (
    BaseDetectionScoreParameters,
    SelectionConsensusParameters,
    GeometrySupportScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)
from .separator import (
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
    content_support: ContentSupportParameters = field(default_factory=ContentSupportParameters)


@dataclass(frozen=True)
class OuterParameters:
    outer_strategy: OuterStrategyParameters = field(default_factory=OuterStrategyParameters)
    floating_content_position: FloatingContentPositionParameters = field(default_factory=FloatingContentPositionParameters)
    edge_anchored_content_position: EdgeAnchoredContentPositionParameters = field(default_factory=EdgeAnchoredContentPositionParameters)
    base_sequence_span_candidates: OuterBoxDetectionParameters = field(default_factory=OuterBoxDetectionParameters)
    separator_outer_band: SeparatorOuterBandParameters = field(default_factory=SeparatorOuterBandParameters)
    separator_full_width_outer: FullWidthSeparatorOuterParameters = field(default_factory=FullWidthSeparatorOuterParameters)
    long_axis_geometry_correction: LongAxisGeometryCorrectionParameters = field(default_factory=LongAxisGeometryCorrectionParameters)
    short_axis_geometry_correction: ShortAxisGeometryCorrectionParameters = field(default_factory=ShortAxisGeometryCorrectionParameters)
    content_containment_correction: ContentContainmentCorrectionParameters = field(default_factory=ContentContainmentCorrectionParameters)
    outer_alignment_evidence: OuterAlignmentEvidenceParameters = field(default_factory=OuterAlignmentEvidenceParameters)


@dataclass(frozen=True)
class SeparatorParameters:
    separator_width_profile: SeparatorWidthProfileParameters = field(default_factory=SeparatorWidthProfileParameters)
    separator_width_profile_search: SeparatorWidthProfileSearchParameters = field(default_factory=SeparatorWidthProfileSearchParameters)
    edge_pair: EdgePairParameters = field(default_factory=EdgePairParameters)
    nearby_separator_refinement: NearbySeparatorRefinementParameters = field(default_factory=NearbySeparatorRefinementParameters)
    gap_search: GapSearchParameters = field(default_factory=GapSearchParameters)
    separator_profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)
    edge_refine_profile: EdgeRefineProfileParameters = field(default_factory=EdgeRefineProfileParameters)
    hard_gap_trust: HardGapTrustParameters = field(default_factory=HardGapTrustParameters)


@dataclass(frozen=True)
class CandidateParameters:
    partial_counts: PartialCountParameters = field(default_factory=PartialCountParameters)
    candidate_plan: CandidatePlanParameters = field(default_factory=CandidatePlanParameters)
    scoring_calibration: ScoringCalibrationParameters = field(default_factory=ScoringCalibrationParameters)
    base_detection_score: BaseDetectionScoreParameters = field(default_factory=BaseDetectionScoreParameters)
    separator_support_score: SeparatorSupportScoreParameters = field(default_factory=SeparatorSupportScoreParameters)
    geometry_support_score: GeometrySupportScoreParameters = field(default_factory=GeometrySupportScoreParameters)
    selection_consensus: SelectionConsensusParameters = field(default_factory=SelectionConsensusParameters)


@dataclass(frozen=True)
class OutputParameters:
    exposure_overlap_evidence: ExposureOverlapEvidenceParameters = field(
        default_factory=ExposureOverlapEvidenceParameters
    )
    exposure_overlap_protection: ExposureOverlapProtectionParameters = field(
        default_factory=ExposureOverlapProtectionParameters
    )
    edge_bleed_protection: EdgeBleedProtectionParameters = field(
        default_factory=EdgeBleedProtectionParameters
    )
    approved_geometry_adjustment: ApprovedGeometryAdjustmentParameters = field(default_factory=ApprovedGeometryAdjustmentParameters)


@dataclass(frozen=True)
class DiagnosticsParameters:
    debug_gap_overlay: DebugGapOverlayParameters = field(default_factory=DebugGapOverlayParameters)


@dataclass(frozen=True)
class FormatParameters:
    preprocess: PreprocessParameters = field(default_factory=PreprocessParameters)
    content: ContentParameters = field(default_factory=ContentParameters)
    outer: OuterParameters = field(default_factory=OuterParameters)
    separator: SeparatorParameters = field(default_factory=SeparatorParameters)
    candidate: CandidateParameters = field(default_factory=CandidateParameters)
    output: OutputParameters = field(default_factory=OutputParameters)
    diagnostics: DiagnosticsParameters = field(default_factory=DiagnosticsParameters)
