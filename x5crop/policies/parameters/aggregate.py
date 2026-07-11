from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry.detection_parameters import (
    SeparatorContinuityParameters,
    SeparatorProfileParameters,
)
from ...image.deskew_parameters import DeskewParameters
from .candidate import CandidatePlanParameters
from .content import (
    ContentEvidenceParameters,
    ContentProfileParameters,
    ContentSupportParameters,
)
from .diagnostics import SeparatorOverlayParameters
from .sequence import SequenceParameters
from .output import (
    OverlapBleedParameters,
)
from .scoring import (
    BaseDetectionScoreParameters,
    SelectionConsensusParameters,
    GeometrySupportScoreParameters,
    ScoringCalibrationParameters,
)
from .separator import (
    FrameDimensionEstimateParameters,
    SeparatorObservationParameters,
)


@dataclass(frozen=True)
class PreprocessParameters:
    deskew: DeskewParameters = field(default_factory=DeskewParameters)


@dataclass(frozen=True)
class ContentParameters:
    content_evidence: ContentEvidenceParameters = field(default_factory=ContentEvidenceParameters)
    content_profile: ContentProfileParameters = field(default_factory=ContentProfileParameters)
    content_support: ContentSupportParameters = field(default_factory=ContentSupportParameters)


@dataclass(frozen=True)
class SeparatorParameters:
    separator_observation: SeparatorObservationParameters = field(
        default_factory=SeparatorObservationParameters
    )
    frame_dimension_estimate: FrameDimensionEstimateParameters = field(
        default_factory=FrameDimensionEstimateParameters
    )
    separator_continuity: SeparatorContinuityParameters = field(
        default_factory=SeparatorContinuityParameters
    )
    separator_profile: SeparatorProfileParameters = field(default_factory=SeparatorProfileParameters)


@dataclass(frozen=True)
class CandidateParameters:
    candidate_plan: CandidatePlanParameters = field(default_factory=CandidatePlanParameters)
    scoring_calibration: ScoringCalibrationParameters = field(default_factory=ScoringCalibrationParameters)
    base_detection_score: BaseDetectionScoreParameters = field(default_factory=BaseDetectionScoreParameters)
    geometry_support_score: GeometrySupportScoreParameters = field(default_factory=GeometrySupportScoreParameters)
    selection_consensus: SelectionConsensusParameters = field(default_factory=SelectionConsensusParameters)


@dataclass(frozen=True)
class DiagnosticsParameters:
    separator_overlay: SeparatorOverlayParameters = field(default_factory=SeparatorOverlayParameters)


@dataclass(frozen=True)
class FormatParameters:
    preprocess: PreprocessParameters = field(default_factory=PreprocessParameters)
    content: ContentParameters = field(default_factory=ContentParameters)
    sequence: SequenceParameters = field(default_factory=SequenceParameters)
    separator: SeparatorParameters = field(default_factory=SeparatorParameters)
    candidate: CandidateParameters = field(default_factory=CandidateParameters)
    output: OverlapBleedParameters = field(default_factory=OverlapBleedParameters)
    diagnostics: DiagnosticsParameters = field(default_factory=DiagnosticsParameters)
