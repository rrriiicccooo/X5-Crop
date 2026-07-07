from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GatePolicy:
    ordered_gates: tuple[str, ...]
    hard_review_reasons_block_auto: bool = True


@dataclass(frozen=True)
class PartialHolderPolicy:
    safe_extra_frames: bool = False
    safe_extra_frames_strip_modes: tuple[str, ...] = ("partial",)
    requires_broad_separator_width_gaps: int = 0
    checks_leading_content: bool = False
    checks_frame_content: bool = False
    min_count_35mm: int = 2
    min_count_small: int = 2
    min_hard_gaps: int = 1
    min_hard_ratio: float = 0.15
    max_equal_gaps: int = 0
    max_width_cv: float = 0.055
    min_joint_score: float = 0.65
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    broad_separator_width_min_ratio: float = 0.033
    leading_content_max_mean: float = 0.20
    leading_content_max_coverage: float = 0.34
    leading_content_band_ratio: float = 0.04
    min_frame_mean: float = 0.055
    min_frame_coverage: float = 0.10
    max_frame_aspect_error: float = 0.22


@dataclass(frozen=True)
class PartialEdgeHintPolicy:
    window_ratio: float = 0.18
    window_min: int = 8
    window_max: int = 900


@dataclass(frozen=True)
class GeometrySupportScorePolicy:
    width_cv_norm: float = 0.040
    outer_min_area: float = 0.35
    outer_max_area: float = 0.94
    outer_uncertain_score: float = 0.55
    aspect_norm: float = 0.22
    no_aspect_score: float = 0.80
    width_weight: float = 0.34
    outer_weight: float = 0.24
    aspect_weight: float = 0.26
    count_weight: float = 0.16


@dataclass(frozen=True)
class BaseDetectionScorePolicy:
    width_cv_norm: float = 0.030
    gap_weight: float = 0.40
    width_weight: float = 0.30
    outer_min_area: float = 0.35
    outer_max_area: float = 0.995
    outer_too_large: float = 0.94
    image_quality_contrast_min: float = 35.0
    full_width_cv: float = 0.040
    geometry_floor_tight_cv: float = 0.006
    geometry_floor_high: float = 0.92
    geometry_floor_low: float = 0.88
    unstable_width_cv: float = 0.030
    full_outer_min_area: float = 0.40
    low_confidence_floor: float = 0.85
    partial_one_cap: float = 0.78
    partial_two_35mm_cap: float = 0.82
    partial_general_cap: float = 0.84
    family_separator_uncertain_reason: str = "separator_evidence_incomplete"


@dataclass(frozen=True)
class SeparatorSupportScorePolicy:
    model_grid_credit: float = 0.35
    model_equal_credit: float = 0.12
    hard_weight: float = 0.78
    model_weight: float = 0.22
    no_expected_confidence_threshold: float = 0.85
    no_expected_confidence_cap: float = 0.75


@dataclass(frozen=True)
class ScoringPolicy:
    confidence_threshold_default: float = 0.85
    hard_full_confidence_floor: float = 0.0
    geometry_weight: float = 0.34
    content_weight: float = 0.33
    separator_weight: float = 0.33
    separator_source_bias: float = 0.0
    no_auto_cap_full: float = 0.84
    no_auto_cap_partial: float = 0.82
    competition_top_n: int = 8
    competition_close_margin: float = 0.04
    base_detection: BaseDetectionScorePolicy = field(default_factory=BaseDetectionScorePolicy)
    geometry_support: GeometrySupportScorePolicy = field(default_factory=GeometrySupportScorePolicy)
    separator_support: SeparatorSupportScorePolicy = field(default_factory=SeparatorSupportScorePolicy)


@dataclass(frozen=True)
class ContentMismatchReviewSelectionPolicy:
    enabled: bool = False
    strip_modes: tuple[str, ...] = ("full",)
    require_default_count: bool = True
    required_best_source: str = "content"
    required_review_reason: str = "content_run_count_mismatch"
    candidate_source: str = "separator"
    min_hard_ratio: float = 0.50
    max_equal_gaps: int = 0
    required_content_support: str = "ok"
    override_reason: str = "content_candidate_mismatch_prefers_separator_review"


@dataclass(frozen=True)
class SelectionPolicy:
    top_n: int = 8
    close_margin: float = 0.04
    confidence_cap: float = 0.84
    content_mismatch_review: ContentMismatchReviewSelectionPolicy = field(default_factory=ContentMismatchReviewSelectionPolicy)


@dataclass(frozen=True)
class SafetyCandidatePolicy:
    use_outer_proposals: bool = True
    strategies: tuple[str, ...] = ("separator_outer",)


@dataclass(frozen=True)
class PartialStopPolicy:
    stop_after_safe_auto: bool = True
    skip_content_after_safe_auto: bool = True
    skip_content_after_safe_auto_strip_modes: tuple[str, ...] = ("partial",)
    skip_content_after_safe_auto_reason: str = "partial_safe_separator_auto_gate_passed"


@dataclass(frozen=True)
class SeparatorFullWidthCompetitionPolicy:
    enabled: bool = True
    content_outer_max_median_aspect_strategies: tuple[str, ...] = ("content_outer",)
    content_outer_max_median_aspect_strip_modes: tuple[str, ...] = ("partial",)
    content_outer_max_median_aspect: float = 1.045
    general_min_median_aspect: float = 1.090


@dataclass(frozen=True)
class CandidateExecutionBudgetPolicy:
    stop_after_reliable_primary: bool = True
    skip_outer_correction_after_reliable_selection: bool = True
    reliable_confidence_margin: float = 0.02
    requires_separator_source: bool = True
    requires_auto_gate: bool = True
    requires_hard_separator_ok: bool = True
    requires_content_support: str = "ok"
    requires_no_review_reasons: bool = True


@dataclass(frozen=True)
class EvidenceIndependencePolicy:
    enabled: bool = True
    dependent_outer_strategies: tuple[str, ...] = ("separator_outer",)
    dependent_gap_sources: tuple[str, ...] = ("observed_width_profile",)
    max_dependent_gap_count_without_validation: int = 0
    min_standard_detected_gaps: int = 1
    require_content_support: str = "ok"
    min_content_score: float = 0.72
    min_geometry_score: float = 0.72
    max_width_cv: float = 0.040
    review_reason: str = "evidence_dependency_cycle_risk"


@dataclass(frozen=True)
class OuterCorrectionCandidateExtensionPolicy:
    enabled: bool = True


@dataclass(frozen=True)
class ContentCandidatePlanPolicy:
    enabled: bool = True
    skip_after_separator_auto: bool = True
    separator_auto_skip_strip_modes: tuple[str, ...] = ("full",)
    separator_auto_skip_reason: str = "separator_auto_gate_passed"
    disabled_skip_reason: str = "disabled_by_policy"


@dataclass(frozen=True)
class ContentGuidedSeparatorCandidatePolicy:
    enabled: bool = True
    strip_modes: tuple[str, ...] = ("full", "partial")
    requires_exact_content_runs: bool = True
    max_hint_offset_ratio: float = 0.28
    max_hint_offset_min: int = 18
    max_hint_offset_max: int = 420
    proposal_role: str = "content_guided_separator_search"
    guidance_source: str = "content_region_hints"
    requires_hard_separator_reason: str = "content_guided_separator_needs_hard_separator"

    def available_for(self, strip_mode: str) -> bool:
        return bool(self.enabled and strip_mode in self.strip_modes)


@dataclass(frozen=True)
class CandidatePlanPolicy:
    content_candidate: ContentCandidatePlanPolicy = field(default_factory=ContentCandidatePlanPolicy)
    content_guided_separator: ContentGuidedSeparatorCandidatePolicy = field(
        default_factory=ContentGuidedSeparatorCandidatePolicy
    )
    safety_candidate: SafetyCandidatePolicy = field(default_factory=SafetyCandidatePolicy)
    partial_stop: PartialStopPolicy = field(default_factory=PartialStopPolicy)
    separator_full_width_competition: SeparatorFullWidthCompetitionPolicy = field(
        default_factory=SeparatorFullWidthCompetitionPolicy
    )
    execution_budget: CandidateExecutionBudgetPolicy = field(default_factory=CandidateExecutionBudgetPolicy)
    evidence_independence: EvidenceIndependencePolicy = field(default_factory=EvidenceIndependencePolicy)
    outer_correction_extension: OuterCorrectionCandidateExtensionPolicy = field(
        default_factory=OuterCorrectionCandidateExtensionPolicy
    )


__all__ = [
    "BaseDetectionScorePolicy",
    "CandidateExecutionBudgetPolicy",
    "CandidatePlanPolicy",
    "ContentCandidatePlanPolicy",
    "ContentGuidedSeparatorCandidatePolicy",
    "ContentMismatchReviewSelectionPolicy",
    "EvidenceIndependencePolicy",
    "GatePolicy",
    "GeometrySupportScorePolicy",
    "OuterCorrectionCandidateExtensionPolicy",
    "PartialEdgeHintPolicy",
    "PartialHolderPolicy",
    "PartialStopPolicy",
    "SafetyCandidatePolicy",
    "ScoringPolicy",
    "SelectionPolicy",
    "SeparatorFullWidthCompetitionPolicy",
    "SeparatorSupportScorePolicy",
]
