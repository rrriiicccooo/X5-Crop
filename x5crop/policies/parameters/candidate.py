from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeparatorFullWidthCompetitionParameters:
    content_outer_max_median_aspect: float = 1.045
    general_min_median_aspect: float = 1.090


@dataclass(frozen=True)
class CandidateExecutionBudgetParameters:
    reliable_confidence_margin: float = 0.02
    physical_primary_candidate_count: int = 2


@dataclass(frozen=True)
class EvidenceIndependenceParameters:
    max_dependent_gap_count_without_validation: int = 0
    min_standard_detected_gaps: int = 1
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    max_photo_width_cv: float = 0.040


@dataclass(frozen=True)
class ContentGuidedSeparatorCandidateParameters:
    max_hint_offset_ratio: float = 0.28
    max_hint_offset_min: int = 18
    max_hint_offset_max: int = 420


@dataclass(frozen=True)
class CandidatePlanParameters:
    content_guided_separator: ContentGuidedSeparatorCandidateParameters = field(
        default_factory=ContentGuidedSeparatorCandidateParameters
    )
    separator_full_width_competition: SeparatorFullWidthCompetitionParameters = field(
        default_factory=SeparatorFullWidthCompetitionParameters
    )
    execution_budget: CandidateExecutionBudgetParameters = field(
        default_factory=CandidateExecutionBudgetParameters
    )
    evidence_independence: EvidenceIndependenceParameters = field(
        default_factory=EvidenceIndependenceParameters
    )


@dataclass(frozen=True)
class PartialHolderParameters:
    minimum_observed_frame_count: int = 2
    min_hard_gaps: int = 1
    min_hard_ratio: float = 0.15
    max_equal_gaps: int = 0
    max_photo_width_cv: float = 0.055
    min_joint_score: float = 0.65
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    leading_content_max_mean: float = 0.20
    leading_content_max_coverage: float = 0.34
    leading_content_band_ratio: float = 0.04
    leading_content_band_min_px: int = 8
    leading_content_band_max_ratio: float = 0.12
    leading_content_signal_threshold: float = 0.20
    min_frame_mean: float = 0.055
    min_frame_coverage: float = 0.10
