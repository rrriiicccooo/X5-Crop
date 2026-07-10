from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from ...domain import DetectionCandidate
from ...policies.decision.contract import DetectionDecisionContract
from ..gate_checks import GateCheck, gate_check_details


@dataclass(frozen=True)
class DecisionGateAssessment:
    passed: bool
    checks: list[GateCheck]
    final_review_reasons: list[str]
    reason_inputs: list[dict[str, Any]]
    confidence_caps: list[dict[str, Any]] = field(default_factory=list)

    def with_confidence_caps(self, confidence_caps: list[dict[str, Any]]) -> "DecisionGateAssessment":
        return replace(self, confidence_caps=list(confidence_caps))

    def with_final_review_reasons(self, reasons: list[str]) -> "DecisionGateAssessment":
        return replace(self, final_review_reasons=list(reasons))

    def report_detail(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "checks": gate_check_details(self.checks),
            "final_review_reasons": list(self.final_review_reasons),
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
            final_review_reason=policy.decision.content_only_evidence_reason,
        )
    )
    checks.append(
        _review_check(
            code="safety_or_review_only",
            bucket="source",
            triggered=bool(decision_signals["safety_or_review_only"]),
            signal="safety_or_review_only",
            final_review_reason=policy.decision.decision_insufficient_reason,
        )
    )
    checks.append(
        _review_check(
            code="outer_content_alignment",
            bucket="outer",
            triggered=bool(decision_signals["outer_content_alignment_failed"]),
            signal="outer_content_alignment_failed",
            final_review_reason=policy.decision.outer_content_mismatch_reason,
        )
    )
    checks.append(
        _review_check(
            code="separator_support",
            bucket="separator",
            triggered=bool(decision_signals["separator_support_incomplete"]),
            signal="separator_support_incomplete",
            final_review_reason=policy.decision.separator_incomplete_reason,
        )
    )
    checks.append(
        _review_check(
            code="geometry_support",
            bucket="geometry",
            triggered=bool(decision_signals["photo_geometry_unstable"]),
            signal="photo_geometry_unstable",
            final_review_reason=policy.decision.geometry_unstable_reason,
        )
    )
    checks.append(
        _review_check(
            code="content_support",
            bucket="content",
            triggered=bool(decision_signals["content_integrity_failed"]),
            signal="content_integrity_failed",
            final_review_reason=policy.decision.content_evidence_insufficient_reason,
        )
    )
    checks.append(
        _review_check(
            code="candidate_competition",
            bucket="selection",
            triggered=bool(decision_signals["candidate_competition_close"]),
            signal="candidate_competition_close",
            final_review_reason=policy.decision.candidate_competition_close_reason,
        )
    )
    checks.append(
        _review_check(
            code="exposure_overlap_protection",
            bucket="output",
            triggered=bool(decision_signals["exposure_overlap_unresolved"]),
            signal="exposure_overlap_unresolved",
            final_review_reason=policy.decision.exposure_overlap_unresolved_reason,
        )
    )
    checks.append(
        _review_check(
            code="partial_edge_safety",
            bucket="partial_edge",
            triggered=bool(decision_signals["partial_edge_uncertain"]),
            signal="partial_edge_uncertain",
            final_review_reason=policy.decision.partial_edge_uncertain_reason,
        )
    )
    checks.append(
        _review_check(
            code="candidate_gate",
            bucket="candidate_assessment",
            triggered=not candidate_gate_allows_auto,
            signal="candidate_gate_failed",
            final_review_reason=policy.decision.decision_insufficient_reason,
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
            final_review_reason=policy.decision.decision_insufficient_reason,
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
            final_review_reason=policy.decision.outer_candidate_disagreement_review_reason,
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
            final_review_reason=policy.decision.deskew_uncertain_review_reason,
        )
    )

    reasons = _failed_reasons(checks)
    return DecisionGateAssessment(
        passed=not reasons,
        checks=checks,
        final_review_reasons=reasons,
        reason_inputs=_failed_reason_inputs(checks),
        confidence_caps=list(decision_input.confidence_caps),
    )
