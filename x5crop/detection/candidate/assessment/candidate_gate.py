from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from ....constants import (
    CANDIDATE_SOURCE_SEPARATOR,
    REASON_CONTENT_ASPECT_CONFLICT,
    REASON_CONTENT_EVIDENCE_WEAK,
    REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
)
from ...gate_checks import GateCheck, gate_check_details, unique_signals


_CANDIDATE_DIAGNOSTIC_SIGNALS = frozenset(
    {
        "content_grid_fallback",
        "content_run_count_mismatch",
        "content_runs_incomplete",
        "content_coverage_weak",
        "content_aspect_uncertain",
        "content_confidence_low",
        "low_confidence",
    }
)

_GEOMETRY_PHOTO_WIDTH_SIGNALS = frozenset(
    {
        "photo_width_unstable",
        "unstable_frame_width",
    }
)

_OUTER_CANDIDATE_VALIDITY_SIGNALS = frozenset(
    {
        "outer_box_too_large",
        "outer_box_uncertain",
    }
)


@dataclass(frozen=True)
class CandidateGateAssessment:
    passed: bool
    checks: list[GateCheck]
    blockers: list[str]
    diagnostics: list[str]
    confidence_caps: list[dict[str, Any]] = field(default_factory=list)

    def with_confidence_caps(self, confidence_caps: list[dict[str, Any]]) -> "CandidateGateAssessment":
        return replace(self, confidence_caps=list(confidence_caps))

    def report_detail(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "checks": gate_check_details(self.checks),
            "blockers": list(self.blockers),
            "diagnostics": list(self.diagnostics),
            "confidence_caps": list(self.confidence_caps),
        }


def _failed_check_signals(checks: list[GateCheck], severity: str) -> list[str]:
    return unique_signals(
        [
            check.signal
            for check in checks
            if not check.passed and check.severity == severity
        ]
    )


def candidate_reason_gate_checks(
    reasons: list[str],
    *,
    ignored_signals: set[str] | None = None,
) -> list[GateCheck]:
    ignored = ignored_signals or set()
    checks: list[GateCheck] = []
    for signal in unique_signals([str(reason) for reason in reasons]):
        if signal in ignored:
            continue
        severity = "diagnostic" if signal in _CANDIDATE_DIAGNOSTIC_SIGNALS else "blocker"
        checks.append(
            GateCheck(
                code="candidate_reason_signal",
                stage="candidate",
                bucket="candidate_diagnostic" if severity == "diagnostic" else "candidate_reason",
                passed=False,
                severity=severity,
                signal=signal,
            )
        )
    return checks


def candidate_reason_blocker_signals(
    reasons: list[str],
    *,
    ignored_signals: set[str] | None = None,
) -> list[str]:
    return _failed_check_signals(
        candidate_reason_gate_checks(reasons, ignored_signals=ignored_signals),
        "blocker",
    )


def candidate_gate_assessment(
    *,
    source: str,
    separator_gate_ok: bool,
    separator_gate_detail: dict[str, Any],
    partial_safe_candidate_gate_support_ok: bool,
    partial_safe_blocks_auto: bool,
    partial_safe_disqualifiers: set[str],
    content_containment_ok: bool,
    content_harm_risk: bool,
    content_support: str,
    evidence_independence_ok: bool,
    evidence_independence_detail: dict[str, Any],
    reasons: list[str],
) -> CandidateGateAssessment:
    checks: list[GateCheck] = []
    source_auto_allowed = source in {"separator", CANDIDATE_SOURCE_SEPARATOR}
    checks.append(
        GateCheck(
            code="candidate_source_auto_allowed",
            stage="candidate",
            bucket="source",
            passed=source_auto_allowed,
            severity="blocker",
            signal="candidate_source_not_auto_allowed",
            detail={"source": source},
        )
    )

    separator_support = (
        source != CANDIDATE_SOURCE_SEPARATOR
        or separator_gate_ok
        or partial_safe_candidate_gate_support_ok
    )
    checks.append(
        GateCheck(
            code="separator_support",
            stage="candidate",
            bucket="separator",
            passed=separator_support,
            severity="blocker",
            signal=REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
            detail={
                "separator_gate_ok": bool(separator_gate_ok),
                "partial_safe_candidate_gate_support_ok": bool(
                    partial_safe_candidate_gate_support_ok
                ),
                "separator_hard_evidence": dict(separator_gate_detail),
            },
        )
    )

    content_signal = (
        REASON_CONTENT_ASPECT_CONFLICT
        if content_support == "aspect_conflict"
        else REASON_CONTENT_EVIDENCE_WEAK
    )
    checks.append(
        GateCheck(
            code="content_containment",
            stage="candidate",
            bucket="content",
            passed=content_containment_ok,
            severity="blocker",
            signal=content_signal,
            detail={"content_support": content_support},
        )
    )
    checks.append(
        GateCheck(
            code="content_harm_absent",
            stage="candidate",
            bucket="content",
            passed=not content_harm_risk,
            severity="blocker",
            signal="content_harm_risk",
            detail={"content_harm_risk": bool(content_harm_risk)},
        )
    )

    independence_signal = str(
        evidence_independence_detail.get("reason") or "evidence_independence_weak"
    )
    checks.append(
        GateCheck(
            code="evidence_independence",
            stage="candidate",
            bucket="evidence",
            passed=evidence_independence_ok,
            severity="blocker",
            signal=independence_signal,
            detail=dict(evidence_independence_detail),
        )
    )

    checks.append(
        GateCheck(
            code="partial_edge_safety",
            stage="candidate",
            bucket="partial_edge",
            passed=not partial_safe_blocks_auto,
            severity="blocker",
            signal="partial_safe_extra_frames_blocked",
            detail={"disqualifiers": sorted(partial_safe_disqualifiers)},
        )
    )

    photo_width_signals = _GEOMETRY_PHOTO_WIDTH_SIGNALS.intersection(reasons)
    checks.append(
        GateCheck(
            code="geometry_photo_width_stability",
            stage="candidate",
            bucket="geometry",
            passed=not photo_width_signals,
            severity="blocker",
            signal=next(iter(sorted(photo_width_signals)), "photo_width_stable"),
            detail={"signals": sorted(photo_width_signals)},
        )
    )

    outer_signals = _OUTER_CANDIDATE_VALIDITY_SIGNALS.intersection(reasons)
    checks.append(
        GateCheck(
            code="outer_candidate_validity",
            stage="candidate",
            bucket="outer",
            passed=not outer_signals,
            severity="blocker",
            signal=next(iter(sorted(outer_signals)), "outer_candidate_valid"),
            detail={"signals": sorted(outer_signals)},
        )
    )

    handled_signals = {
        "content_harm_risk",
        "partial_safe_extra_frames_blocked",
        REASON_CONTENT_ASPECT_CONFLICT,
        REASON_CONTENT_EVIDENCE_WEAK,
        REASON_SEPARATOR_HARD_EVIDENCE_WEAK,
        *partial_safe_disqualifiers,
        *photo_width_signals,
        *outer_signals,
        independence_signal,
    }
    checks.extend(
        candidate_reason_gate_checks(
            reasons,
            ignored_signals=handled_signals,
        )
    )

    blockers = _failed_check_signals(checks, "blocker")
    diagnostics = _failed_check_signals(checks, "diagnostic")
    passed = not blockers
    return CandidateGateAssessment(
        passed=passed,
        checks=checks,
        blockers=blockers,
        diagnostics=diagnostics,
    )


__all__ = [
    "CandidateGateAssessment",
    "candidate_gate_assessment",
    "candidate_reason_blocker_signals",
    "candidate_reason_gate_checks",
]
