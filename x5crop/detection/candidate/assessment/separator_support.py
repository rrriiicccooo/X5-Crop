from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ....domain import Detection
from ...evidence.separator_summary import gap_method_evidence_summary
from ....policies.runtime.policy import DetectionPolicy
from ....policies.runtime.separator import (
    LeadingGridFailurePolicy,
    SeparatorSupportPolicy,
)


@dataclass(frozen=True)
class SeparatorSupportEvidence:
    expected_gaps: int
    actual_detected_gaps: int
    broad_separator_width_gaps: int
    grid_gaps: int
    equal_gaps: int
    hard_gaps: int
    hard_gap_indexes: list[int]
    edge_pair_scores: list[float]
    detected_scores: list[float]
    broad_separator_width_scores: list[Any]
    leading_grid_scores: list[float]


@dataclass(frozen=True)
class SeparatorSupportAssessment:
    ok: bool
    reason: str
    leading_grid_failure: bool = False


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
    support: SeparatorSupportPolicy,
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


def separator_support_geometry_support_assessment(
    detection: Detection,
    threshold: float,
    evidence: SeparatorSupportEvidence,
    support: SeparatorSupportPolicy,
) -> SeparatorSupportCheck:
    ok = (
        bool(support.allow_geometry_support)
        and detection.confidence >= threshold
        and evidence.equal_gaps <= evidence.expected_gaps
    )
    return SeparatorSupportCheck(
        ok=ok,
        reason="separator_geometry_support" if ok else "separator_geometry_support_weak",
    )


def separator_support_needs_full_strip_supplemental_checks(detection: Detection, default_count: int) -> bool:
    return detection.strip_mode == "full" and detection.count == int(default_count)


def separator_support_broad_width_support_assessment(
    broad_width: int,
    support: SeparatorSupportPolicy,
) -> SeparatorSupportCheck:
    ok = broad_width >= support.min_broad_separator_width_gaps_for_auto
    return SeparatorSupportCheck(
        ok=ok,
        reason="separator_broad_width_support" if ok else "separator_broad_width_support_weak",
    )


def separator_support_edge_pair_support_assessment(
    broad_width: int,
    edge_pair_scores: list[float],
    support: SeparatorSupportPolicy,
) -> SeparatorSupportCheck:
    edge_min = (
        support.edge_pair_min_score_with_broad_width
        if broad_width > 0
        else support.edge_pair_min_score_without_broad_width
    )
    ok = not edge_pair_scores or min(edge_pair_scores) >= edge_min
    return SeparatorSupportCheck(
        ok=ok,
        reason="separator_edge_pair_support" if ok else "separator_edge_pair_support_weak",
    )


def separator_support_all_internal_gaps_hard_assessment(
    detection: Detection,
    evidence: SeparatorSupportEvidence,
    support: SeparatorSupportPolicy,
    default_count: int,
) -> SeparatorSupportCheck:
    needed = max(
        1,
        evidence.expected_gaps
        if support.hard_required_all_gaps
        else min(evidence.expected_gaps, 1),
    )
    ok = evidence.hard_gaps >= needed
    reason = (
        "separator_all_internal_gaps_hard_support"
        if ok
        else "separator_all_internal_gaps_hard_support_weak"
    )
    if ok and separator_support_needs_full_strip_supplemental_checks(detection, default_count):
        broad_assessment = separator_support_broad_width_support_assessment(
            evidence.broad_separator_width_gaps,
            support,
        )
        if not broad_assessment.ok:
            return broad_assessment
        edge_assessment = separator_support_edge_pair_support_assessment(
            evidence.broad_separator_width_gaps,
            evidence.edge_pair_scores,
            support,
        )
        if not edge_assessment.ok:
            return edge_assessment
    return SeparatorSupportCheck(ok=ok, reason=reason)


def hard_gap_indexes_are_tail_adjacent(hard_indexes: list[int]) -> bool:
    if not hard_indexes:
        return False
    expected_sequence = list(
        range(max(hard_indexes) - len(hard_indexes) + 1, max(hard_indexes) + 1)
    )
    return hard_indexes == expected_sequence and min(hard_indexes) >= 4


def separator_support_leading_grid_failure_assessment(
    detection: Detection,
    evidence: SeparatorSupportEvidence,
    policy: LeadingGridFailurePolicy,
) -> bool:
    return (
        policy.enabled
        and detection.strip_mode == "full"
        and evidence.expected_gaps >= policy.min_expected_gaps
        and len(evidence.leading_grid_scores) >= policy.leading_count
        and all(
            score < policy.low_score
            for score in evidence.leading_grid_scores[:policy.leading_count]
        )
        and sum(
            1
            for score in evidence.leading_grid_scores[:policy.leading_count]
            if score < policy.very_low_score
        ) >= policy.very_low_count
        and len(evidence.hard_gap_indexes) <= policy.max_hard_gaps
        and hard_gap_indexes_are_tail_adjacent(evidence.hard_gap_indexes)
    )


def separator_support_evidence_from_detection(detection: Detection) -> SeparatorSupportEvidence:
    raw_gap_evidence = gap_method_evidence_summary(detection.gaps, reliable_min_score=0.0)
    broad_width = int(detection.detail.get("broad_separator_width_gaps", 0))
    width_evidence = detection.detail.get("separator_width_evidence", {})
    broad_width_scores = (
        list(width_evidence.get("broad_separator_width_scores", []))
        if isinstance(width_evidence, dict)
        else []
    )
    return SeparatorSupportEvidence(
        expected_gaps=max(0, int(detection.count) - 1),
        actual_detected_gaps=raw_gap_evidence.direct_hard_gaps,
        broad_separator_width_gaps=broad_width,
        grid_gaps=raw_gap_evidence.grid_model_gaps,
        equal_gaps=raw_gap_evidence.equal_model_gaps,
        hard_gaps=raw_gap_evidence.hard_separator_gaps,
        hard_gap_indexes=list(raw_gap_evidence.hard_gap_indexes),
        edge_pair_scores=list(raw_gap_evidence.edge_pair_scores),
        detected_scores=list(raw_gap_evidence.detected_scores),
        broad_separator_width_scores=broad_width_scores,
        leading_grid_scores=list(raw_gap_evidence.leading_grid_scores),
    )


def separator_support_detail(
    evidence: SeparatorSupportEvidence,
    assessment: SeparatorSupportAssessment,
    detection: Detection,
    support: SeparatorSupportPolicy,
    policy: DetectionPolicy,
) -> dict[str, Any]:
    return {
        "ok": assessment.ok,
        "reason": assessment.reason,
        "expected_gaps": evidence.expected_gaps,
        "hard_gaps": evidence.hard_gaps,
        "separator_support_count": evidence.hard_gaps + evidence.grid_gaps,
        "actual_detected_gaps": evidence.actual_detected_gaps,
        "broad_separator_width_gaps": evidence.broad_separator_width_gaps,
        "grid_gaps": evidence.grid_gaps,
        "equal_gaps": evidence.equal_gaps,
        "hard_gap_indexes": evidence.hard_gap_indexes,
        "edge_pair_scores": evidence.edge_pair_scores,
        "detected_scores": evidence.detected_scores,
        "broad_separator_width_scores": evidence.broad_separator_width_scores,
        "leading_grid_scores": evidence.leading_grid_scores,
        "leading_grid_separator_failure": bool(assessment.leading_grid_failure),
        "separator_confidence": float(detection.confidence),
        "policy_id": policy.policy_id,
    }


def separator_support_assessment(
    detection: Detection,
    threshold: float,
    evidence: SeparatorSupportEvidence,
    support: SeparatorSupportPolicy,
    default_count: int,
) -> SeparatorSupportAssessment:
    leading_grid_failure = separator_support_leading_grid_failure_assessment(
        detection,
        evidence,
        support.leading_grid_failure,
    )

    if evidence.expected_gaps == 0:
        support_assessment = SeparatorSupportCheck(
            ok=detection.confidence >= threshold,
            reason=(
                "single_frame_no_separator_needed"
                if detection.confidence >= threshold
                else "single_frame_low_confidence"
            ),
        )
    elif detection.confidence < threshold:
        support_assessment = SeparatorSupportCheck(
            ok=False,
            reason="separator_below_threshold",
        )
    elif leading_grid_failure:
        support_assessment = SeparatorSupportCheck(
            ok=False,
            reason="leading_grid_separator_failure",
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
            separator_support_geometry_support_assessment(
                detection,
                threshold,
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
        leading_grid_failure=leading_grid_failure,
    )


def assess_separator_support(
    detection: Detection,
    threshold: float,
    policy: DetectionPolicy,
) -> SeparatorSupportResult:
    support = policy.separator.support
    evidence = separator_support_evidence_from_detection(detection)
    assessment = separator_support_assessment(detection, threshold, evidence, support, policy.default_count)

    return SeparatorSupportResult(
        ok=assessment.ok,
        detail=separator_support_detail(
            evidence,
            assessment,
            detection,
            support,
            policy,
        ),
    )


__all__ = [
    "SeparatorSupportAssessment",
    "SeparatorSupportEvidence",
    "SeparatorSupportResult",
    "SeparatorSupportCheck",
    "hard_gap_indexes_are_tail_adjacent",
    "separator_support_all_internal_gaps_hard_assessment",
    "separator_support_broad_width_support_assessment",
    "separator_support_edge_pair_support_assessment",
    "separator_support_geometry_support_assessment",
    "separator_support_leading_grid_failure_assessment",
    "separator_support_min_hard_with_equal_cap_assessment",
    "separator_support_needs_full_strip_supplemental_checks",
    "separator_support_assessment",
    "separator_support_detail",
    "separator_support_evidence_from_detection",
    "assess_separator_support",
]
