from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContentEvidencePolicy:
    percentile: float = 70.0
    threshold_multiplier: float = 0.70
    threshold_min: float = 0.08
    threshold_max: float = 0.45
    aspect_ok_max: float = 0.22
    present_mean_min: float = 0.075
    present_coverage_min: float = 0.18


@dataclass(frozen=True)
class ContentProfilePolicy:
    smooth_ratio: float = 0.010
    min_run_ratio: float = 0.20
    threshold_min: float = 0.035
    threshold_max: float = 0.40
    p35_weight: float = 0.38
    p65_multiplier: float = 0.82


@dataclass(frozen=True)
class ContentMaskPolicy:
    p55_weight: float = 0.34
    p75_multiplier: float = 0.78
    threshold_min: float = 0.045
    threshold_max: float = 0.45
    percentiles: tuple[float, float, float] = (55.0, 75.0, 92.0)
    bbox_min_fraction: float = 0.008
    outer_min_width_ratio: float = 0.08
    outer_min_height_ratio: float = 0.08
    outer_min_width_px: int = 60
    outer_min_height_px: int = 30
    outer_expand_ratio: float = 0.002


@dataclass(frozen=True)
class ContentCandidatePolicy:
    candidate_contract: str = "content_guidance_assessment_required"
    proposal_role: str = "weak_content_model_proposal"
    model_gap_evidence_kind: str = "content_model_gap"
    expected_width_min_px: float = 8.0
    coverage_weight: float = 0.38
    mean_weight: float = 0.30
    run_weight: float = 0.22
    aspect_weight: float = 0.10
    coverage_norm: float = 0.22
    mean_norm: float = 0.16
    aspect_norm: float = 0.18
    weak_coverage: float = 0.14
    aspect_uncertain: float = 0.18
    grid_fallback_cap: float = 0.82
    run_mismatch_cap: float = 0.84
    runs_incomplete_cap: float = 0.84
    weak_coverage_cap: float = 0.82
    aspect_uncertain_cap: float = 0.82


@dataclass(frozen=True)
class ContentPolicy:
    validates_candidates: bool = True
    evidence: ContentEvidencePolicy = field(default_factory=ContentEvidencePolicy)
    profile: ContentProfilePolicy = field(default_factory=ContentProfilePolicy)
    mask: ContentMaskPolicy = field(default_factory=ContentMaskPolicy)
    candidate: ContentCandidatePolicy = field(default_factory=ContentCandidatePolicy)
    support_coverage_norm: float = 0.22
    support_mean_norm: float = 0.16
    support_aspect_norm: float = 0.22
    support_coverage_weight: float = 0.42
    support_mean_weight: float = 0.40
    support_aspect_weight: float = 0.18
    support_score_ok: float = 1.0
    support_score_weak: float = 0.72
    support_score_low_content: float = 0.58
    support_score_aspect_conflict: float = 0.35
    support_score_unknown: float = 0.50


__all__ = [
    "ContentCandidatePolicy",
    "ContentEvidencePolicy",
    "ContentMaskPolicy",
    "ContentPolicy",
    "ContentProfilePolicy",
]
