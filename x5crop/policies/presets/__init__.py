from __future__ import annotations

from collections.abc import Callable

from .base import (
    ApprovedGeometryAdjustmentParameters,
    BaseOuterCandidateParameters,
    BaseDetectionScoreParameters,
    CandidateCompetitionParameters,
    ContentCandidateParameters,
    ContentEvidenceParameters,
    ContentFloatingOuterParameters,
    ContentMaskParameters,
    ContentProfileParameters,
    ContentSupportParameters,
    DebugGapOverlayParameters,
    DiagnosticOverlapRiskParameters,
    EdgeRefineProfileParameters,
    EdgePairParams,
    EdgeAnchorOuterParameters,
    EnhancedSeparatorParameters,
    FormatGeometryRetryParameters,
    FormatParameters,
    GapSearchParameters,
    GeometrySupportScoreParameters,
    GridOuterRefineParameters,
    HardGapTrustParameters,
    LeadingGridFailureParameters,
    LuckyPassRiskParameters,
    NearbySeparatorCorrectionParameters,
    NearbySeparatorDiagnosticsParameters,
    OuterContentAlignmentParameters,
    OuterMaskProfile,
    OuterStrategyParameters,
    PartialCountParameters,
    PartialEdgeHintParameters,
    PartialHolderParameters,
    PostprocessParameters,
    RobustGridParameters,
    ScoringCalibrationParameters,
    SeparatorGateParameters,
    SeparatorGeometryOuterParameters,
    SeparatorGeometrySupportParameters,
    SeparatorOuterBandParameters,
    SeparatorProfileParameters,
    SeparatorSupportScoreParameters,
    ShortAxisAspectRetryParameters,
    WideRetryParameters,
    base_medium_format_parameters,
)
from .dense_half_frame import parameters as _dense_half_frame_parameters
from .medium_rectangle import parameters as _medium_rectangle_parameters
from .medium_square import parameters as _medium_square_parameters
from .medium_wide import parameters as _medium_wide_parameters
from .panoramic_strip import parameters as _panoramic_strip_parameters
from .parallel_lane import parameters as _parallel_lane_parameters
from .standard_strip import parameters as _standard_strip_parameters

PARAMETER_PRESETS: dict[str, Callable[[], FormatParameters]] = {
    "135": _standard_strip_parameters,
    "135-dual": _parallel_lane_parameters,
    "half": _dense_half_frame_parameters,
    "xpan": _panoramic_strip_parameters,
    "120-645": _medium_rectangle_parameters,
    "120-66": _medium_square_parameters,
    "120-67": _medium_wide_parameters,
}


def format_parameters(format_name: str) -> FormatParameters:
    try:
        factory = PARAMETER_PRESETS[format_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported format parameters: {format_name}") from exc
    return factory()


__all__ = [
    "ApprovedGeometryAdjustmentParameters",
    "BaseOuterCandidateParameters",
    "BaseDetectionScoreParameters",
    "CandidateCompetitionParameters",
    "ContentCandidateParameters",
    "ContentEvidenceParameters",
    "ContentFloatingOuterParameters",
    "ContentMaskParameters",
    "ContentProfileParameters",
    "ContentSupportParameters",
    "DebugGapOverlayParameters",
    "DiagnosticOverlapRiskParameters",
    "EdgeRefineProfileParameters",
    "EdgePairParams",
    "EdgeAnchorOuterParameters",
    "EnhancedSeparatorParameters",
    "FormatGeometryRetryParameters",
    "FormatParameters",
    "GapSearchParameters",
    "GeometrySupportScoreParameters",
    "GridOuterRefineParameters",
    "HardGapTrustParameters",
    "LeadingGridFailureParameters",
    "LuckyPassRiskParameters",
    "NearbySeparatorCorrectionParameters",
    "NearbySeparatorDiagnosticsParameters",
    "OuterContentAlignmentParameters",
    "OuterMaskProfile",
    "OuterStrategyParameters",
    "PARAMETER_PRESETS",
    "PartialCountParameters",
    "PartialEdgeHintParameters",
    "PartialHolderParameters",
    "PostprocessParameters",
    "RobustGridParameters",
    "ScoringCalibrationParameters",
    "SeparatorGateParameters",
    "SeparatorGeometryOuterParameters",
    "SeparatorGeometrySupportParameters",
    "SeparatorOuterBandParameters",
    "SeparatorProfileParameters",
    "SeparatorSupportScoreParameters",
    "ShortAxisAspectRetryParameters",
    "WideRetryParameters",
    "base_medium_format_parameters",
    "format_parameters",
]
