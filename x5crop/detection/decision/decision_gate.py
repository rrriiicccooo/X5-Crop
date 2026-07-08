from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from ...domain import Detection
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


def _review_check(
    *,
    code: str,
    bucket: str,
    triggered: bool,
    signal: str,
    final_review_reason: str,
    detail: dict[str, Any] | None = None,
) -> GateCheck:
    return GateCheck(
        code=code,
        stage="decision",
        bucket=bucket,
        passed=not triggered,
        severity="blocker",
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


def decision_gate_assessment(
    *,
    detection: Detection,
    confidence_threshold: float,
    evidence: dict[str, Any],
    decision_signals: dict[str, Any],
    policy: DetectionDecisionContract,
    candidate_gate_passed: bool,
    deskew_detail: dict[str, Any],
    include_low_confidence_context: bool,
    confidence_caps: list[dict[str, Any]] | None = None,
) -> DecisionGateAssessment:
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
            code="output_overlap",
            bucket="output",
            triggered=bool(decision_signals["output_overlap_detected"]),
            signal="output_overlap_detected",
            final_review_reason=policy.decision.output_overlap_reason,
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
            triggered=not candidate_gate_passed,
            signal="candidate_gate_failed",
            final_review_reason=policy.decision.decision_insufficient_reason,
        )
    )

    if not _failed_reasons(checks):
        checks.append(
            _review_check(
                code="confidence_floor",
                bucket="confidence",
                triggered=float(detection.confidence) < float(confidence_threshold),
                signal="confidence_below_threshold",
                final_review_reason=policy.decision.decision_insufficient_reason,
                detail={
                    "confidence": float(detection.confidence),
                    "confidence_threshold": float(confidence_threshold),
                },
            )
        )

    if include_low_confidence_context and detection.confidence < confidence_threshold:
        checks.append(
            _review_check(
                code="outer_candidate_disagreement",
                bucket="low_confidence_context",
                triggered=float(detection.detail.get("outer_area_spread_ratio", 0.0)) >= 0.20,
                signal="outer_area_spread",
                final_review_reason=policy.decision.outer_candidate_disagreement_review_reason,
            )
        )
        checks.append(
            _review_check(
                code="deskew_uncertain",
                bucket="low_confidence_context",
                triggered=(
                    deskew_detail.get("skipped") == "angle_out_of_range"
                    or bool(deskew_detail.get("reason"))
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
        confidence_caps=list(confidence_caps or []),
    )


__all__ = [
    "DecisionGateAssessment",
    "decision_gate_assessment",
]
