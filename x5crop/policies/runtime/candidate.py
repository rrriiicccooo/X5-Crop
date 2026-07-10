from __future__ import annotations

from dataclasses import dataclass, field

from ..parameters.candidate import PartialHolderParameters
from ..parameters.scoring import (
    BaseDetectionScoreParameters,
    GeometrySupportScoreParameters,
    ScoringCalibrationParameters,
    SeparatorSupportScoreParameters,
)


@dataclass(frozen=True)
class PartialHolderPolicy:
    enabled: bool
    parameters: PartialHolderParameters
    max_frame_aspect_error: float


@dataclass(frozen=True)
class ScoringPolicy:
    calibration: ScoringCalibrationParameters
    base_detection: BaseDetectionScoreParameters
    geometry_support: GeometrySupportScoreParameters
    separator_support: SeparatorSupportScoreParameters


@dataclass(frozen=True)
class SeparatorFullWidthCompetitionPolicy:
    content_outer_max_median_aspect: float = 1.045
    general_min_median_aspect: float = 1.090


@dataclass(frozen=True)
class CandidateExecutionBudgetPolicy:
    reliable_confidence_margin: float = 0.02


@dataclass(frozen=True)
class EvidenceIndependencePolicy:
    max_dependent_gap_count_without_validation: int = 0
    min_standard_detected_gaps: int = 1
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    max_photo_width_cv: float = 0.040


@dataclass(frozen=True)
class ContentGuidedSeparatorCandidatePolicy:
    max_hint_offset_ratio: float = 0.28
    max_hint_offset_min: int = 18
    max_hint_offset_max: int = 420

@dataclass(frozen=True)
class CandidatePlanPolicy:
    content_guided_separator: ContentGuidedSeparatorCandidatePolicy = field(
        default_factory=ContentGuidedSeparatorCandidatePolicy
    )
    separator_full_width_competition: SeparatorFullWidthCompetitionPolicy = field(
        default_factory=SeparatorFullWidthCompetitionPolicy
    )
    execution_budget: CandidateExecutionBudgetPolicy = field(default_factory=CandidateExecutionBudgetPolicy)
    evidence_independence: EvidenceIndependencePolicy = field(default_factory=EvidenceIndependencePolicy)
