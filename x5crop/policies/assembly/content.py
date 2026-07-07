from __future__ import annotations

from ..parameters.aggregate import FormatParameters
from ..runtime.content import (
    ContentCandidatePolicy,
    ContentEvidencePolicy,
    ContentPolicy,
    ContentMaskPolicy,
    ContentProfilePolicy,
)


def content_policy(params: FormatParameters) -> ContentPolicy:
    evidence = params.content_evidence
    profile = params.content_profile
    mask = params.content_mask
    candidate = params.content_candidate
    support = params.content_support
    return ContentPolicy(
        evidence=ContentEvidencePolicy(
            percentile=float(evidence.percentile),
            threshold_multiplier=float(evidence.threshold_multiplier),
            threshold_min=float(evidence.threshold_min),
            threshold_max=float(evidence.threshold_max),
            aspect_ok_max=float(evidence.aspect_ok_max),
            present_mean_min=float(evidence.present_mean_min),
            present_coverage_min=float(evidence.present_coverage_min),
        ),
        profile=ContentProfilePolicy(
            smooth_ratio=float(profile.smooth_ratio),
            min_run_ratio=float(profile.min_run_ratio),
            threshold_min=float(profile.threshold_min),
            threshold_max=float(profile.threshold_max),
            p35_weight=float(profile.p35_weight),
            p65_multiplier=float(profile.p65_multiplier),
        ),
        mask=ContentMaskPolicy(
            p55_weight=float(mask.p55_weight),
            p75_multiplier=float(mask.p75_multiplier),
            threshold_min=float(mask.threshold_min),
            threshold_max=float(mask.threshold_max),
            percentiles=tuple(float(value) for value in mask.percentiles),
            bbox_min_fraction=float(mask.bbox_min_fraction),
            outer_min_width_ratio=float(mask.outer_min_width_ratio),
            outer_min_height_ratio=float(mask.outer_min_height_ratio),
            outer_min_width_px=int(mask.outer_min_width_px),
            outer_min_height_px=int(mask.outer_min_height_px),
            outer_expand_ratio=float(mask.outer_expand_ratio),
        ),
        candidate=ContentCandidatePolicy(
            candidate_contract="content_guidance_assessment_required",
            proposal_role="weak_content_model_proposal",
            model_gap_evidence_kind="content_model_gap",
            expected_width_min_px=float(candidate.expected_width_min_px),
            coverage_weight=float(candidate.coverage_weight),
            mean_weight=float(candidate.mean_weight),
            run_weight=float(candidate.run_weight),
            aspect_weight=float(candidate.aspect_weight),
            coverage_norm=float(candidate.coverage_norm),
            mean_norm=float(candidate.mean_norm),
            aspect_norm=float(candidate.aspect_norm),
            weak_coverage=float(candidate.weak_coverage),
            aspect_uncertain=float(candidate.aspect_uncertain),
            grid_fallback_cap=float(candidate.grid_fallback_cap),
            run_mismatch_cap=float(candidate.run_mismatch_cap),
            runs_incomplete_cap=float(candidate.runs_incomplete_cap),
            weak_coverage_cap=float(candidate.weak_coverage_cap),
            aspect_uncertain_cap=float(candidate.aspect_uncertain_cap),
        ),
        support_coverage_norm=float(support.coverage_norm),
        support_mean_norm=float(support.mean_norm),
        support_aspect_norm=float(support.aspect_norm),
        support_coverage_weight=float(support.coverage_weight),
        support_mean_weight=float(support.mean_weight),
        support_aspect_weight=float(support.aspect_weight),
        support_gate_ok=float(support.gate_ok),
        support_gate_weak=float(support.gate_weak),
        support_gate_low_content=float(support.gate_low_content),
        support_gate_aspect_conflict=float(support.gate_aspect_conflict),
        support_gate_unknown=float(support.gate_unknown),
    )

__all__ = [
    'content_policy',
]
