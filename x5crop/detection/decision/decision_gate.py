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
    risk: dict[str, Any],
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
            bucket="risk",
            triggered=bool(risk["content_only_evidence"]),
            signal="content_only_evidence",
            final_review_reason=policy.decision.content_only_evidence_reason,
        )
    )
    checks.append(
        _review_check(
            code="safety_or_review_only",
            bucket="risk",
            triggered=bool(risk["safety_or_review_only"]),
            signal="safety_or_review_only",
            final_review_reason=policy.decision.decision_insufficient_reason,
        )
    )
    checks.append(
        _review_check(
            code="outer_content_alignment",
            bucket="outer",
            triggered=(
                not bool(evidence["outer"]["ok"])
                and policy.risk.review_on_outer_content_mismatch
            ),
            signal="outer_not_ok",
            final_review_reason=policy.decision.outer_content_mismatch_reason,
            detail={
                "review_on_outer_content_mismatch": bool(
                    policy.risk.review_on_outer_content_mismatch
                )
            },
        )
    )
    checks.append(
        _review_check(
            code="separator_support",
            bucket="separator",
            triggered=not bool(evidence["separator"]["ok"]),
            signal="separator_not_ok",
            final_review_reason=policy.decision.separator_incomplete_reason,
        )
    )
    checks.append(
        _review_check(
            code="geometry_support",
            bucket="geometry",
            triggered=not bool(evidence["geometry"]["ok"]),
            signal="geometry_not_ok",
            final_review_reason=policy.decision.geometry_unstable_reason,
        )
    )
    checks.append(
        _review_check(
            code="content_support",
            bucket="content",
            triggered=not bool(evidence["content"]["ok"]),
            signal="content_not_ok",
            final_review_reason=policy.decision.content_evidence_insufficient_reason,
        )
    )
    checks.append(
        _review_check(
            code="candidate_competition",
            bucket="risk",
            triggered=(
                bool(risk["candidate_competition_close"])
                and policy.risk.review_on_close_competition
            ),
            signal="candidate_competition_close",
            final_review_reason=policy.decision.candidate_competition_close_reason,
            detail={
                "review_on_close_competition": bool(policy.risk.review_on_close_competition)
            },
        )
    )
    checks.append(
        _review_check(
            code="overlap_risk",
            bucket="risk",
            triggered=bool(risk["overlap_risk"]) and policy.risk.review_on_overlap_risk,
            signal="overlap_bleed_risk",
            final_review_reason=policy.decision.overlap_risk_reason,
            detail={"review_on_overlap_risk": bool(policy.risk.review_on_overlap_risk)},
        )
    )
    checks.append(
        _review_check(
            code="lucky_pass_risk",
            bucket="risk",
            triggered=bool(risk["lucky_pass_risk"]) and policy.risk.review_on_lucky_pass_risk,
            signal="lucky_pass_risk",
            final_review_reason=policy.decision.lucky_pass_risk_reason,
            detail={"review_on_lucky_pass_risk": bool(policy.risk.review_on_lucky_pass_risk)},
        )
    )
    checks.append(
        _review_check(
            code="partial_edge_safety",
            bucket="partial_edge",
            triggered=bool(risk["partial_edge_uncertain"]),
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
                signal="below_threshold",
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
