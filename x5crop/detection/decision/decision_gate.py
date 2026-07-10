from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from ...constants import CANDIDATE_SOURCE_REVIEW_ONLY
from ...domain import DetectionCandidate, FinalDetection, OutputProtectionPlan
from ...policies.decision.contract import DetectionDecisionContract
from ...run_config import RunConfig
from ..confidence_caps import apply_confidence_cap
from ..gate_checks import GateCheck, gate_check_details
from .decision_signals import decision_signals_for
from .evidence_summary import evidence_summary_for
from .final_reasons import (
    FINAL_REASON_CANDIDATE_COMPETITION_CLOSE,
    FINAL_REASON_CONTENT_INSUFFICIENT,
    FINAL_REASON_CONTENT_ONLY_EVIDENCE,
    FINAL_REASON_DESKEW_UNCERTAIN,
    FINAL_REASON_EVIDENCE_INSUFFICIENT,
    FINAL_REASON_EXPOSURE_OVERLAP_UNRESOLVED,
    FINAL_REASON_GEOMETRY_UNSTABLE,
    FINAL_REASON_OUTER_CANDIDATE_DISAGREEMENT,
    FINAL_REASON_OUTER_CONTENT_MISMATCH,
    FINAL_REASON_PARTIAL_EDGE_UNCERTAIN,
    FINAL_REASON_SEPARATOR_INCOMPLETE,
)


@dataclass(frozen=True)
class DecisionGateAssessment:
    passed: bool
    checks: list[GateCheck]
    final_review_reasons: list[str]
    reason_inputs: list[dict[str, Any]]
    confidence_caps: list[dict[str, Any]] = field(default_factory=list)

    def with_confidence_caps(self, confidence_caps: list[dict[str, Any]]) -> "DecisionGateAssessment":
        return replace(self, confidence_caps=list(confidence_caps))

    def report_detail(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "checks": gate_check_details(self.checks),
            "reason_inputs": list(self.reason_inputs),
            "confidence_caps": list(self.confidence_caps),
        }


@dataclass(frozen=True)
class DecisionAssessmentInput:
    detection: DetectionCandidate
    confidence_threshold: float
    decision_signals: dict[str, Any]
    policy: DetectionDecisionContract
    candidate_gate: dict[str, Any]
    deskew_detail: dict[str, Any]
    confidence_caps: list[dict[str, Any]] = field(default_factory=list)


def _review_check(
    *,
    code: str,
    bucket: str,
    triggered: bool,
    signal: str,
    final_review_reason: str,
    severity: str = "blocker",
    detail: dict[str, Any] | None = None,
) -> GateCheck:
    return GateCheck(
        code=code,
        stage="decision",
        bucket=bucket,
        passed=not triggered,
        severity=severity,
        signal=signal,
        detail={
            **(detail or {}),
            "final_review_reason": final_review_reason,
        },
    )


def _failed_reason_inputs(checks: list[GateCheck]) -> list[dict[str, Any]]:
    return [
        {
            "bucket": check.bucket,
            "signal": check.signal,
            "final_review_reason": str(check.detail.get("final_review_reason", "")),
        }
        for check in checks
        if not check.passed
        and check.severity == "blocker"
        and check.detail.get("final_review_reason")
    ]


def _failed_reasons(checks: list[GateCheck]) -> list[str]:
    return [
        str(check.detail.get("final_review_reason"))
        for check in checks
        if not check.passed
        and check.severity == "blocker"
        and check.detail.get("final_review_reason")
    ]


def _unique_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(str(reason) for reason in reasons if reason))


def decision_gate_assessment(decision_input: DecisionAssessmentInput) -> DecisionGateAssessment:
    detection = decision_input.detection
    confidence_threshold = decision_input.confidence_threshold
    decision_signals = decision_input.decision_signals
    policy = decision_input.policy
    candidate_gate_allows_auto = bool(decision_input.candidate_gate.get("passed", False))
    deskew_detail = decision_input.deskew_detail
    checks: list[GateCheck] = []
    checks.append(
        _review_check(
            code="content_only_evidence",
            bucket="source",
            triggered=bool(decision_signals["content_only_evidence"]),
            signal="content_only_evidence",
            final_review_reason=FINAL_REASON_CONTENT_ONLY_EVIDENCE,
        )
    )
    checks.append(
        _review_check(
            code="safety_or_review_only",
            bucket="source",
            triggered=bool(decision_signals["safety_or_review_only"]),
            signal="safety_or_review_only",
            final_review_reason=FINAL_REASON_EVIDENCE_INSUFFICIENT,
        )
    )
    checks.append(
        _review_check(
            code="outer_content_alignment",
            bucket="outer",
            triggered=bool(decision_signals["outer_content_alignment_failed"]),
            signal="outer_content_alignment_failed",
            final_review_reason=FINAL_REASON_OUTER_CONTENT_MISMATCH,
        )
    )
    checks.append(
        _review_check(
            code="separator_support",
            bucket="separator",
            triggered=bool(decision_signals["separator_support_incomplete"]),
            signal="separator_support_incomplete",
            final_review_reason=FINAL_REASON_SEPARATOR_INCOMPLETE,
        )
    )
    checks.append(
        _review_check(
            code="geometry_support",
            bucket="geometry",
            triggered=bool(decision_signals["photo_geometry_unstable"]),
            signal="photo_geometry_unstable",
            final_review_reason=FINAL_REASON_GEOMETRY_UNSTABLE,
        )
    )
    checks.append(
        _review_check(
            code="content_support",
            bucket="content",
            triggered=bool(decision_signals["content_integrity_failed"]),
            signal="content_integrity_failed",
            final_review_reason=FINAL_REASON_CONTENT_INSUFFICIENT,
        )
    )
    checks.append(
        _review_check(
            code="candidate_competition",
            bucket="selection",
            triggered=bool(decision_signals["candidate_competition_close"]),
            signal="candidate_competition_close",
            final_review_reason=FINAL_REASON_CANDIDATE_COMPETITION_CLOSE,
        )
    )
    checks.append(
        _review_check(
            code="exposure_overlap_protection",
            bucket="output",
            triggered=bool(decision_signals["exposure_overlap_unresolved"]),
            signal="exposure_overlap_unresolved",
            final_review_reason=FINAL_REASON_EXPOSURE_OVERLAP_UNRESOLVED,
        )
    )
    checks.append(
        _review_check(
            code="partial_edge_safety",
            bucket="partial_edge",
            triggered=bool(decision_signals["partial_edge_uncertain"]),
            signal="partial_edge_uncertain",
            final_review_reason=FINAL_REASON_PARTIAL_EDGE_UNCERTAIN,
        )
    )
    checks.append(
        _review_check(
            code="candidate_gate",
            bucket="candidate_assessment",
            triggered=not candidate_gate_allows_auto,
            signal="candidate_gate_failed",
            final_review_reason=FINAL_REASON_EVIDENCE_INSUFFICIENT,
        )
    )

    failed_before_confidence_floor = bool(_failed_reasons(checks))
    confidence_below_threshold = float(detection.confidence) < float(confidence_threshold)
    checks.append(
        _review_check(
            code="confidence_floor",
            bucket="confidence",
            triggered=confidence_below_threshold,
            signal="confidence_below_threshold",
            final_review_reason=FINAL_REASON_EVIDENCE_INSUFFICIENT,
            severity="diagnostic" if failed_before_confidence_floor else "blocker",
            detail={
                "confidence": float(detection.confidence),
                "confidence_threshold": float(confidence_threshold),
                "reason_visibility": (
                    "diagnostic_because_specific_reason_exists"
                    if failed_before_confidence_floor
                    else "final_reason"
                ),
            },
        )
    )
    checks.append(
        _review_check(
            code="outer_candidate_disagreement",
            bucket="low_confidence_context",
            triggered=(
                confidence_below_threshold
                and float(detection.detail.get("outer_area_spread_ratio", 0.0))
                >= policy.decision.outer_candidate_disagreement_min_spread_ratio
            ),
            signal="outer_area_spread",
            final_review_reason=FINAL_REASON_OUTER_CANDIDATE_DISAGREEMENT,
        )
    )
    checks.append(
        _review_check(
            code="deskew_uncertain",
            bucket="low_confidence_context",
            triggered=(
                confidence_below_threshold
                and (
                    deskew_detail.get("skipped") == "angle_out_of_range"
                    or bool(deskew_detail.get("reason"))
                )
            ),
            signal="deskew_uncertain",
            final_review_reason=FINAL_REASON_DESKEW_UNCERTAIN,
        )
    )

    reasons = _unique_reasons(_failed_reasons(checks))
    return DecisionGateAssessment(
        passed=not reasons,
        checks=checks,
        final_review_reasons=reasons,
        reason_inputs=_failed_reason_inputs(checks),
        confidence_caps=list(decision_input.confidence_caps),
    )


def _apply_decision_confidence_caps(
    detection: DetectionCandidate,
    config: RunConfig,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    policy: DetectionDecisionContract,
) -> list[dict[str, Any]]:
    decision_caps: list[dict[str, Any]] = []

    review_only_mode = detection.detail.get("candidate_source") == CANDIDATE_SOURCE_REVIEW_ONLY
    support = str(content_detail.get("support", ""))
    if not review_only_mode:
        if support == "aspect_conflict" and detection.confidence >= config.confidence_threshold:
            detection.confidence, cap_detail = apply_confidence_cap(
                float(detection.confidence),
                policy.decision.content_aspect_conflict_cap,
                owner="decision",
                reason="content_aspect_conflict",
            )
            decision_caps.append(cap_detail)
        elif support == "low_content" and detection.confidence >= config.confidence_threshold:
            detection.confidence, cap_detail = apply_confidence_cap(
                float(detection.confidence),
                policy.decision.content_low_confidence_cap,
                owner="decision",
                reason="content_low_confidence",
            )
            decision_caps.append(cap_detail)

    outer_correction_detail = detection.detail.get("outer_correction", {})
    suppress_outer_mismatch = bool(
        isinstance(outer_correction_detail, dict)
        and outer_correction_detail.get("suppress_outer_mismatch", False)
    )
    if (
        not review_only_mode
        and not suppress_outer_mismatch
        and bool(outer_alignment.get("used", False))
        and not bool(outer_alignment.get("ok", True))
    ):
        detection.confidence, cap_detail = apply_confidence_cap(
            float(detection.confidence),
            policy.decision.outer_mismatch_cap,
            owner="decision",
            reason="outer_content_mismatch",
        )
        decision_caps.append(cap_detail)
    return decision_caps


def apply_decision_gate(
    gray: np.ndarray,
    detection: DetectionCandidate,
    config: RunConfig,
    content_detail: dict[str, Any],
    outer_alignment: dict[str, Any],
    *,
    policy: DetectionDecisionContract,
    deskew_detail: dict[str, Any],
    output_protection_plan: OutputProtectionPlan,
) -> FinalDetection:
    working = deepcopy(detection)
    evidence = evidence_summary_for(gray, working, content_detail, outer_alignment, policy)
    decision_signals = decision_signals_for(
        working,
        evidence,
        policy,
        output_protection_plan,
    )
    assessment = working.detail.get("candidate_assessment", {})
    assessment = dict(assessment) if isinstance(assessment, dict) else {}
    candidate_gate = assessment.get("candidate_gate")
    candidate_gate = dict(candidate_gate) if isinstance(candidate_gate, dict) else {}
    decision_caps = _apply_decision_confidence_caps(
        working,
        config,
        content_detail,
        outer_alignment,
        policy,
    )
    decision_gate = decision_gate_assessment(
        DecisionAssessmentInput(
            detection=working,
            confidence_threshold=config.confidence_threshold,
            decision_signals=decision_signals,
            policy=policy,
            candidate_gate=candidate_gate,
            deskew_detail=deskew_detail,
            confidence_caps=decision_caps,
        )
    )
    final_reasons = list(decision_gate.final_review_reasons)
    if working.confidence < config.confidence_threshold or final_reasons:
        working.confidence, cap_detail = apply_confidence_cap(
            float(working.confidence),
            policy.candidate_selection.confidence_cap,
            owner="decision",
            reason="final_review",
        )
        decision_caps.append(cap_detail)
    decision_gate = decision_gate.with_confidence_caps(decision_caps)
    status = (
        "approved_auto"
        if decision_gate.passed and working.confidence >= config.confidence_threshold
        else "needs_review"
    )
    working.detail["decision_summary"] = {
        "decision_gate": decision_gate.report_detail(),
    }
    working.detail["evidence_summary"] = evidence
    working.detail["decision_signals"] = decision_signals
    return FinalDetection.from_candidate(
        working,
        status=status,
        final_review_reasons=final_reasons,
    )
