from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....domain import DetectionCandidate
from ...evidence.separator_summary import gap_method_evidence_summary
from ....policies.runtime.policy import DetectionPolicy
from ....policies.parameters.separator import SeparatorSupportParameters


@dataclass(frozen=True)
class SeparatorSupportEvidence:
    expected_gaps: int
    actual_detected_gaps: int
    equal_gaps: int
    hard_gaps: int
    hard_gap_indexes: list[int]
    edge_pair_scores: list[float]
    detected_scores: list[float]


@dataclass(frozen=True)
class SeparatorSupportAssessment:
    ok: bool
    reason: str


@dataclass(frozen=True)
class SeparatorSupportCheck:
    ok: bool
    reason: str


@dataclass(frozen=True)
class SeparatorSupportResult:
    ok: bool
    detail: dict[str, Any]


def separator_support_min_hard_with_equal_cap_assessment(
    evidence: SeparatorSupportEvidence,
    support: SeparatorSupportParameters,
) -> SeparatorSupportCheck:
    needed = min(evidence.expected_gaps, support.needed_hard_max)
    ok = (
        evidence.hard_gaps >= needed
        and (
            evidence.equal_gaps
            <= max(support.max_equal_gaps_floor, evidence.expected_gaps // 2)
        )
    )
    return SeparatorSupportCheck(
        ok=ok,
        reason="separator_min_hard_support" if ok else "separator_min_hard_support_weak",
    )


def separator_support_needs_full_strip_supplemental_checks(detection: DetectionCandidate, default_count: int) -> bool:
    return detection.strip_mode == "full" and detection.count == int(default_count)


def separator_support_edge_pair_support_assessment(
    edge_pair_scores: list[float],
    support: SeparatorSupportParameters,
) -> SeparatorSupportCheck:
    ok = not edge_pair_scores or min(edge_pair_scores) >= support.edge_pair_min_score
    return SeparatorSupportCheck(
        ok=ok,
        reason="separator_edge_pair_support" if ok else "separator_edge_pair_support_weak",
    )


def separator_support_all_internal_gaps_hard_assessment(
    detection: DetectionCandidate,
    evidence: SeparatorSupportEvidence,
    support: SeparatorSupportParameters,
    default_count: int,
) -> SeparatorSupportCheck:
    needed = max(1, evidence.expected_gaps)
    ok = evidence.hard_gaps >= needed
    reason = (
        "separator_all_internal_gaps_hard_support"
        if ok
        else "separator_all_internal_gaps_hard_support_weak"
    )
    if ok and separator_support_needs_full_strip_supplemental_checks(detection, default_count):
        edge_assessment = separator_support_edge_pair_support_assessment(
            evidence.edge_pair_scores,
            support,
        )
        if not edge_assessment.ok:
            return edge_assessment
    return SeparatorSupportCheck(ok=ok, reason=reason)


def separator_support_evidence_from_detection(detection: DetectionCandidate) -> SeparatorSupportEvidence:
    raw_gap_evidence = gap_method_evidence_summary(detection.gaps, reliable_min_score=0.0)
    return SeparatorSupportEvidence(
        expected_gaps=max(0, int(detection.count) - 1),
        actual_detected_gaps=raw_gap_evidence.direct_hard_gaps,
        equal_gaps=raw_gap_evidence.equal_model_gaps,
        hard_gaps=raw_gap_evidence.hard_separator_gaps,
        hard_gap_indexes=list(raw_gap_evidence.hard_gap_indexes),
        edge_pair_scores=list(raw_gap_evidence.edge_pair_scores),
        detected_scores=list(raw_gap_evidence.detected_scores),
    )


def separator_support_detail(
    evidence: SeparatorSupportEvidence,
    assessment: SeparatorSupportAssessment,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    return {
        "ok": assessment.ok,
        "reason": assessment.reason,
        "expected_gaps": evidence.expected_gaps,
        "hard_gaps": evidence.hard_gaps,
        "separator_support_count": evidence.hard_gaps,
        "actual_detected_gaps": evidence.actual_detected_gaps,
        "equal_gaps": evidence.equal_gaps,
        "hard_gap_indexes": evidence.hard_gap_indexes,
        "edge_pair_scores": evidence.edge_pair_scores,
        "detected_scores": evidence.detected_scores,
        "policy_id": policy.policy_id,
    }


def separator_support_assessment(
    detection: DetectionCandidate,
    evidence: SeparatorSupportEvidence,
    support: SeparatorSupportParameters,
    default_count: int,
) -> SeparatorSupportAssessment:
    if evidence.expected_gaps == 0:
        support_assessment = SeparatorSupportCheck(
            ok=True,
            reason="single_frame_no_separator_needed",
        )
    else:
        checks = [
            separator_support_all_internal_gaps_hard_assessment(
                detection,
                evidence,
                support,
                default_count,
            ),
            separator_support_min_hard_with_equal_cap_assessment(
                evidence,
                support,
            ),
        ]
        support_assessment = next(
            (check for check in checks if check.ok),
            checks[0],
        )

    return SeparatorSupportAssessment(
        ok=support_assessment.ok,
        reason=support_assessment.reason,
    )


def assess_separator_support(
    detection: DetectionCandidate,
    policy: DetectionPolicy,
) -> SeparatorSupportResult:
    support = policy.separator.support
    evidence = separator_support_evidence_from_detection(detection)
    assessment = separator_support_assessment(
        detection,
        evidence,
        support,
        policy.physical_spec.default_count,
    )

    return SeparatorSupportResult(
        ok=assessment.ok,
        detail=separator_support_detail(
            evidence,
            assessment,
            policy,
        ),
    )
