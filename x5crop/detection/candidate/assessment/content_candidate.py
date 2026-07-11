from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....domain import DetectionCandidate
from ....policies.parameters.content import ContentCandidateParameters
from ....policies.runtime.content import ContentPolicy


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
    diagnostics: list[str] = []
    if placement != "content_runs":
        diagnostics.append("content_grid_placement")
    if runs_count != count:
        diagnostics.append("content_run_count_mismatch")
    if run_conf < 1.0:
        diagnostics.append("content_runs_incomplete")
    if median_coverage < candidate_policy.weak_coverage:
        diagnostics.append("content_coverage_weak")
    if max_aspect_error > candidate_policy.aspect_uncertain:
        diagnostics.append("content_aspect_uncertain")
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
    }
    return ContentCandidateAssessment(
        confidence=float(confidence),
        diagnostics=diagnostics,
        detail=detail,
    )


def content_candidate_assessment_from_proposal(
    detection: DetectionCandidate,
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
