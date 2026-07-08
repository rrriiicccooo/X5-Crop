from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from ....constants import CANDIDATE_SOURCE_SEPARATOR
from ...gate_checks import GateCheck, gate_check_details, unique_signals
from ..signals import (
    GATE_BLOCKER_SIGNALS,
    GATE_DIAGNOSTIC_SIGNALS,
    FRAME_TOPOLOGY_BLOCKER_SIGNALS,
    MODE_DIAGNOSTIC_SIGNALS,
    PHOTO_SIZE_BLOCKER_SIGNALS,
    SIGNAL_BUCKETS,
    SIGNAL_CONTENT_ASPECT_CONFLICT,
    SIGNAL_CONTENT_EVIDENCE_WEAK,
    SIGNAL_CONTENT_HARM_RISK,
    SIGNAL_CONTENT_OUTSIDE_OUTER,
    SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_RISK,
    SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK,
    unknown_candidate_signals,
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


def candidate_signal_gate_checks(
    signals: list[str],
    *,
    ignored_signals: set[str] | None = None,
) -> list[GateCheck]:
    ignored = ignored_signals or set()
    unknown = unknown_candidate_signals(signals, ignored=ignored)
    if unknown:
        raise ValueError(f"unowned candidate signals: {', '.join(unknown)}")
    checks: list[GateCheck] = []
    for signal in unique_signals([str(signal) for signal in signals]):
        if signal in ignored or signal in MODE_DIAGNOSTIC_SIGNALS:
            continue
        if signal in GATE_BLOCKER_SIGNALS:
            severity = "blocker"
        elif signal in GATE_DIAGNOSTIC_SIGNALS:
            severity = "diagnostic"
        else:
            continue
        bucket = SIGNAL_BUCKETS.get(signal, "candidate")
        checks.append(
            GateCheck(
                code=f"{bucket}_signal",
                stage="candidate",
                bucket=bucket,
                passed=False,
                severity=severity,
                signal=signal,
            )
        )
    return checks


def candidate_signal_blocker_signals(
    signals: list[str],
    *,
    ignored_signals: set[str] | None = None,
) -> list[str]:
    return _failed_check_signals(
        candidate_signal_gate_checks(signals, ignored_signals=ignored_signals),
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
    signals: list[str],
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
            signal=SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK,
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
        SIGNAL_CONTENT_ASPECT_CONFLICT
        if content_support == "aspect_conflict"
        else SIGNAL_CONTENT_EVIDENCE_WEAK
    )
    content_integrity_ok = content_containment_ok and not content_harm_risk
    if content_integrity_ok:
        content_integrity_signal = "content_integrity_ok"
    elif not content_containment_ok:
        content_integrity_signal = content_signal
    else:
        content_integrity_signal = SIGNAL_CONTENT_HARM_RISK
    checks.append(
        GateCheck(
            code="content_integrity",
            stage="candidate",
            bucket="content",
            passed=content_integrity_ok,
            severity="blocker",
            signal=content_integrity_signal,
            detail={
                "content_support": content_support,
                "content_containment_ok": bool(content_containment_ok),
                "content_harm_risk": bool(content_harm_risk),
            },
        )
    )

    independence_signal = str(
        evidence_independence_detail.get("reason")
        or SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_RISK
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

    photo_width_signals = PHOTO_SIZE_BLOCKER_SIGNALS.intersection(signals)
    checks.append(
        GateCheck(
            code="photo_size_consistency",
            stage="candidate",
            bucket="photo_size",
            passed=not photo_width_signals,
            severity="blocker",
            signal=next(iter(sorted(photo_width_signals)), "photo_width_stable"),
            detail={"signals": sorted(photo_width_signals)},
        )
    )
    frame_topology_signals = FRAME_TOPOLOGY_BLOCKER_SIGNALS.intersection(signals)
    checks.append(
        GateCheck(
            code="frame_topology",
            stage="candidate",
            bucket="frame_topology",
            passed=not frame_topology_signals,
            severity="blocker",
            signal=next(iter(sorted(frame_topology_signals)), "frame_topology_ok"),
            detail={"signals": sorted(frame_topology_signals)},
        )
    )

    handled_signals = {
        SIGNAL_CONTENT_HARM_RISK,
        "partial_safe_extra_frames_blocked",
        SIGNAL_CONTENT_ASPECT_CONFLICT,
        SIGNAL_CONTENT_EVIDENCE_WEAK,
        SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK,
        *partial_safe_disqualifiers,
        *photo_width_signals,
        *frame_topology_signals,
        independence_signal,
    }
    checks.extend(
        candidate_signal_gate_checks(
            signals,
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
    "candidate_signal_blocker_signals",
    "candidate_signal_gate_checks",
]
