from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....domain import DetectionCandidate
from ...confidence_caps import apply_confidence_cap
from ....policies.parameters.content import ContentCandidateParameters
from ....policies.runtime.content import ContentPolicy
from ....run_config import RunConfig


@dataclass(frozen=True)
class ContentCandidateAssessment:
    confidence: float
    diagnostics: list[str]
    detail: dict[str, Any]


def content_candidate_assessment_from_metrics(
    *,
    placement: str,
    runs_count: int,
    selected_run_count: int,
    count: int,
    strip_mode: str,
    median_mean: float,
    median_coverage: float,
    max_aspect_error: float,
    confidence_threshold: float,
    candidate_policy: ContentCandidateParameters,
) -> ContentCandidateAssessment:
    run_conf = min(1.0, selected_run_count / float(max(1, count)))
    coverage_conf = min(1.0, median_coverage / candidate_policy.coverage_norm)
    mean_conf = min(1.0, median_mean / candidate_policy.mean_norm)
    aspect_conf = max(0.0, min(1.0, 1.0 - max_aspect_error / candidate_policy.aspect_norm))
    confidence = (
        candidate_policy.coverage_weight * coverage_conf
        + candidate_policy.mean_weight * mean_conf
        + candidate_policy.run_weight * run_conf
        + candidate_policy.aspect_weight * aspect_conf
    )
    confidence_caps: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    if placement != "content_runs":
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.grid_placement_cap,
            owner="candidate.assessment",
            reason="content_grid_placement",
        )
        confidence_caps.append(cap_detail)
        diagnostics.append("content_grid_placement")
    if runs_count != count:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.run_mismatch_cap,
            owner="candidate.assessment",
            reason="content_run_count_mismatch",
        )
        confidence_caps.append(cap_detail)
        diagnostics.append("content_run_count_mismatch")
    if run_conf < 1.0:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.runs_incomplete_cap,
            owner="candidate.assessment",
            reason="content_runs_incomplete",
        )
        confidence_caps.append(cap_detail)
        diagnostics.append("content_runs_incomplete")
    if median_coverage < candidate_policy.weak_coverage:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.weak_coverage_cap,
            owner="candidate.assessment",
            reason="content_coverage_weak",
        )
        confidence_caps.append(cap_detail)
        diagnostics.append("content_coverage_weak")
    if max_aspect_error > candidate_policy.aspect_uncertain:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.aspect_uncertain_cap,
            owner="candidate.assessment",
            reason="content_aspect_uncertain",
        )
        confidence_caps.append(cap_detail)
        diagnostics.append("content_aspect_uncertain")
    if confidence < confidence_threshold and not diagnostics:
        diagnostics.append("content_confidence_low")
    detail = {
        "run_conf": run_conf,
        "coverage_conf": coverage_conf,
        "mean_conf": mean_conf,
        "aspect_conf": aspect_conf,
        "partial_candidate_role": (
            "content_guidance_not_count_evidence"
            if strip_mode == "partial"
            else "content_guidance"
        ),
        "confidence_caps": confidence_caps,
    }
    return ContentCandidateAssessment(
        confidence=float(confidence),
        diagnostics=diagnostics,
        detail=detail,
    )


def content_candidate_assessment_from_proposal(
    detection: DetectionCandidate,
    config: RunConfig,
    policy: ContentPolicy,
) -> ContentCandidateAssessment:
    proposal = detection.detail.get("content_proposal", {})
    if not isinstance(proposal, dict):
        return ContentCandidateAssessment(
            confidence=0.0,
            diagnostics=["content_confidence_low"],
            detail={"used": False, "reason": "missing_content_proposal"},
        )
    assessment = content_candidate_assessment_from_metrics(
        placement=str(proposal.get("placement", "")),
        runs_count=int(proposal.get("usable_run_count", 0)),
        selected_run_count=int(proposal.get("selected_run_count", 0)),
        count=int(detection.count),
        strip_mode=detection.strip_mode,
        median_mean=float(proposal.get("median_mean", 0.0)),
        median_coverage=float(proposal.get("median_coverage", 0.0)),
        max_aspect_error=float(proposal.get("max_aspect_error", 1.0)),
        confidence_threshold=float(config.confidence_threshold),
        candidate_policy=policy.candidate,
    )
    return ContentCandidateAssessment(
        confidence=assessment.confidence,
        diagnostics=assessment.diagnostics,
        detail={
            **assessment.detail,
            "used": True,
            "owner": "candidate.assessment",
        },
    )
