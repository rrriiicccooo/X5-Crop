from __future__ import annotations

from typing import Any

from ....domain import Detection
from ...confidence_caps import apply_confidence_cap
from ....policies.runtime.content import ContentCandidatePolicy, ContentPolicy
from ....runtime.config import RuntimeConfig


def content_candidate_confidence_and_reasons(
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
    candidate_policy: ContentCandidatePolicy,
) -> tuple[float, list[str], dict[str, Any]]:
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
    reasons: list[str] = []
    if placement != "content_runs":
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.grid_fallback_cap,
            owner="candidate.assessment",
            reason="content_grid_fallback",
        )
        confidence_caps.append(cap_detail)
        reasons.append("content_grid_fallback")
    if runs_count != count:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.run_mismatch_cap,
            owner="candidate.assessment",
            reason="content_run_count_mismatch",
        )
        confidence_caps.append(cap_detail)
        reasons.append("content_run_count_mismatch")
    if run_conf < 1.0:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.runs_incomplete_cap,
            owner="candidate.assessment",
            reason="content_runs_incomplete",
        )
        confidence_caps.append(cap_detail)
        reasons.append("content_runs_incomplete")
    if median_coverage < candidate_policy.weak_coverage:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.weak_coverage_cap,
            owner="candidate.assessment",
            reason="content_coverage_weak",
        )
        confidence_caps.append(cap_detail)
        reasons.append("content_coverage_weak")
    if max_aspect_error > candidate_policy.aspect_uncertain:
        confidence, cap_detail = apply_confidence_cap(
            confidence,
            candidate_policy.aspect_uncertain_cap,
            owner="candidate.assessment",
            reason="content_aspect_uncertain",
        )
        confidence_caps.append(cap_detail)
        reasons.append("content_aspect_uncertain")
    if confidence < confidence_threshold and not reasons:
        reasons.append("content_confidence_low")
    detail = {
        "run_conf": run_conf,
        "coverage_conf": coverage_conf,
        "mean_conf": mean_conf,
        "aspect_conf": aspect_conf,
        "partial_candidate_role": (
            "content_guidance_not_count_risk"
            if strip_mode == "partial"
            else "content_guidance"
        ),
        "confidence_caps": confidence_caps,
    }
    return float(confidence), reasons, detail


def content_candidate_assessment_from_proposal(
    detection: Detection,
    config: RuntimeConfig,
    policy: ContentPolicy,
) -> tuple[float, list[str], dict[str, Any]]:
    proposal = detection.detail.get("content_primary", {})
    if not isinstance(proposal, dict):
        return 0.0, ["content_confidence_low"], {"used": False, "reason": "missing_content_proposal"}
    confidence, reasons, detail = content_candidate_confidence_and_reasons(
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
    return confidence, reasons, {
        **detail,
        "used": True,
        "owner": "candidate.assessment",
    }


__all__ = [
    "content_candidate_assessment_from_proposal",
    "content_candidate_confidence_and_reasons",
]
