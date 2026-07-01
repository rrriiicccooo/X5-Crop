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
    base_120_parameters,
)
from .format_120_645 import parameters as _format_120_645_parameters
from .format_120_66 import parameters as _format_120_66_parameters
from .format_120_67 import parameters as _format_120_67_parameters
from .format_135 import parameters as _format_135_parameters
from .format_135_dual import parameters as _format_135_dual_parameters
from .format_half import parameters as _format_half_parameters
from .format_xpan import parameters as _format_xpan_parameters

PARAMETER_PRESETS: dict[str, Callable[[], FormatParameters]] = {
    "135": _format_135_parameters,
    "135-dual": _format_135_dual_parameters,
    "half": _format_half_parameters,
    "xpan": _format_xpan_parameters,
    "120-645": _format_120_645_parameters,
    "120-66": _format_120_66_parameters,
    "120-67": _format_120_67_parameters,
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
    "base_120_parameters",
    "format_parameters",
]
