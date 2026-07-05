from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ....constants import GAP_DETECTED, GAP_EDGE_PAIR, GAP_GRID, HARD_GAP_METHODS
from ....domain import Detection
from ....formats import FORMATS
from ....policies.registry import get_detection_policy
from ....policies.runtime.policy import DetectionPolicy
from ....policies.runtime.separator import LeadingGridFailurePolicy, SeparatorGatePolicy


@dataclass(frozen=True)
class SeparatorGateEvidence:
    expected_gaps: int
    actual_detected_gaps: int
    broad_separator_width_gaps: int
    enhanced_detected_gaps: int
    grid_gaps: int
    equal_gaps: int
    hard_gaps: int
    hard_gap_indexes: list[int]
    edge_pair_scores: list[float]
    detected_scores: list[float]
    broad_separator_width_scores: list[Any]
    leading_grid_scores: list[float]
    enhanced_separator_accepted_count: int


def separator_gate_min_hard_with_equal_cap_assessment(
    evidence: SeparatorGateEvidence,
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    needed = min(evidence.expected_gaps, gate.needed_hard_max)
    ok = (
        evidence.hard_gaps >= needed
        and (
            evidence.equal_gaps
            <= max(gate.max_equal_gaps_floor, evidence.expected_gaps // 2)
        )
    )
    return ok, "separator_min_hard_support" if ok else "separator_min_hard_support_weak"


def separator_gate_geometry_support_assessment(
    detection: Detection,
    threshold: float,
    evidence: SeparatorGateEvidence,
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    ok = (
        bool(gate.allow_geometry_support)
        and detection.confidence >= threshold
        and evidence.equal_gaps <= evidence.expected_gaps
    )
    return ok, "separator_geometry_support" if ok else "separator_geometry_support_weak"


def separator_gate_needs_full_strip_supplemental_checks(detection: Detection) -> bool:
    return detection.strip_mode == "full" and detection.count == FORMATS[detection.film_format].default_count


def separator_gate_broad_width_support_assessment(
    broad_width: int,
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    ok = broad_width >= gate.min_broad_separator_width_gaps_for_auto
    return ok, "separator_broad_width_support" if ok else "separator_broad_width_support_weak"


def separator_gate_edge_pair_support_assessment(
    broad_width: int,
    edge_pair_scores: list[float],
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    edge_min = (
        gate.edge_pair_min_score_with_broad_width
        if broad_width > 0
        else gate.edge_pair_min_score_without_broad_width
    )
    ok = not edge_pair_scores or min(edge_pair_scores) >= edge_min
    return ok, "separator_edge_pair_support" if ok else "separator_edge_pair_support_weak"


def separator_gate_all_internal_gaps_hard_assessment(
    detection: Detection,
    evidence: SeparatorGateEvidence,
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    needed = max(
        1,
        evidence.expected_gaps
        if gate.hard_required_all_gaps
        else min(evidence.expected_gaps, 1),
    )
    ok = evidence.hard_gaps >= needed
    reason = (
        "separator_all_internal_gaps_hard_support"
        if ok
        else "separator_all_internal_gaps_hard_support_weak"
    )
    if ok and separator_gate_needs_full_strip_supplemental_checks(detection):
        broad_ok, broad_reason = separator_gate_broad_width_support_assessment(
            evidence.broad_separator_width_gaps,
            gate,
        )
        if not broad_ok:
            return False, broad_reason
        edge_ok, edge_reason = separator_gate_edge_pair_support_assessment(
            evidence.broad_separator_width_gaps,
            evidence.edge_pair_scores,
            gate,
        )
        if not edge_ok:
            return False, edge_reason
    return ok, reason


def leading_grid_scores_from_gaps(detection: Detection) -> list[float]:
    scores: list[float] = []
    for gap in detection.gaps:
        if gap.method != GAP_GRID:
            break
        scores.append(float(gap.score))
    return scores


def hard_gap_indexes_from_gaps(detection: Detection) -> list[int]:
    return [
        int(gap.index)
        for gap in detection.gaps
        if gap.method in HARD_GAP_METHODS
    ]


def hard_gap_indexes_are_adjacent_late(hard_indexes: list[int]) -> bool:
    if not hard_indexes:
        return False
    expected_sequence = list(
        range(max(hard_indexes) - len(hard_indexes) + 1, max(hard_indexes) + 1)
    )
    return hard_indexes == expected_sequence and min(hard_indexes) >= 4


def enhanced_gap_promotion_accepted_count(detection: Detection) -> int:
    enhanced_gap_promotion = detection.detail.get("enhanced_gap_promotion", {})
    if not isinstance(enhanced_gap_promotion, dict):
        return 0
    return int(enhanced_gap_promotion.get("accepted_count", 0) or 0)


def separator_gate_leading_grid_failure_assessment(
    detection: Detection,
    evidence: SeparatorGateEvidence,
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
        and evidence.enhanced_separator_accepted_count == 0
        and len(evidence.hard_gap_indexes) <= policy.max_hard_gaps
        and hard_gap_indexes_are_adjacent_late(evidence.hard_gap_indexes)
    )


def separator_gate_evidence_from_detection(detection: Detection) -> SeparatorGateEvidence:
    actual = int(detection.detail.get("actual_detected_gaps", 0))
    broad_width = int(detection.detail.get("broad_separator_width_gaps", 0))
    enhanced = int(detection.detail.get("enhanced_detected_gaps", 0))
    width_evidence = detection.detail.get("separator_width_evidence", {})
    broad_width_scores = (
        list(width_evidence.get("broad_separator_width_scores", []))
        if isinstance(width_evidence, dict)
        else []
    )
    return SeparatorGateEvidence(
        expected_gaps=max(0, int(detection.count) - 1),
        actual_detected_gaps=actual,
        broad_separator_width_gaps=broad_width,
        enhanced_detected_gaps=enhanced,
        grid_gaps=int(detection.detail.get("grid_gaps", 0)),
        equal_gaps=int(detection.detail.get("equal_gaps", 0)),
        hard_gaps=actual + enhanced,
        hard_gap_indexes=hard_gap_indexes_from_gaps(detection),
        edge_pair_scores=[
            float(gap.score)
            for gap in detection.gaps
            if gap.method == GAP_EDGE_PAIR
        ],
        detected_scores=[
            float(gap.score)
            for gap in detection.gaps
            if gap.method == GAP_DETECTED
        ],
        broad_separator_width_scores=broad_width_scores,
        leading_grid_scores=leading_grid_scores_from_gaps(detection),
        enhanced_separator_accepted_count=enhanced_gap_promotion_accepted_count(
            detection
        ),
    )


def separator_gate_detail(
    evidence: SeparatorGateEvidence,
    ok: bool,
    reason: str,
    detection: Detection,
    gate: SeparatorGatePolicy,
    policy: DetectionPolicy,
    leading_grid_failure: bool,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "reason": reason,
        "expected_gaps": evidence.expected_gaps,
        "hard_gaps": evidence.hard_gaps,
        "actual_detected_gaps": evidence.actual_detected_gaps,
        "broad_separator_width_gaps": evidence.broad_separator_width_gaps,
        "enhanced_detected_gaps": evidence.enhanced_detected_gaps,
        "grid_gaps": evidence.grid_gaps,
        "equal_gaps": evidence.equal_gaps,
        "hard_gap_indexes": evidence.hard_gap_indexes,
        "edge_pair_scores": evidence.edge_pair_scores,
        "detected_scores": evidence.detected_scores,
        "broad_separator_width_scores": evidence.broad_separator_width_scores,
        "leading_grid_scores": evidence.leading_grid_scores,
        "enhanced_separator_accepted_count": evidence.enhanced_separator_accepted_count,
        "leading_grid_separator_failure": bool(leading_grid_failure),
        "separator_confidence": float(detection.confidence),
        "separator_gate_profile": gate.profile,
        "policy_id": policy.policy_id,
    }


def candidate_has_hard_separator_evidence(
    detection: Detection,
    threshold: float,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[bool, dict[str, Any]]:
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    gate = policy.separator.gate
    evidence = separator_gate_evidence_from_detection(detection)
    leading_grid_failure = separator_gate_leading_grid_failure_assessment(
        detection,
        evidence,
        gate.leading_grid_failure,
    )

    if evidence.expected_gaps == 0:
        ok = detection.confidence >= threshold
        reason = "single_frame_no_separator_needed" if ok else "single_frame_low_confidence"
    elif detection.confidence < threshold:
        ok = False
        reason = "separator_below_threshold"
    elif leading_grid_failure:
        ok = False
        reason = "leading_grid_separator_failure"
    elif gate.profile == "min_hard_with_equal_cap":
        ok, reason = separator_gate_min_hard_with_equal_cap_assessment(evidence, gate)
    elif gate.profile == "geometry_support":
        ok, reason = separator_gate_geometry_support_assessment(
            detection,
            threshold,
            evidence,
            gate,
        )
    else:
        ok, reason = separator_gate_all_internal_gaps_hard_assessment(
            detection,
            evidence,
            gate,
        )

    return ok, separator_gate_detail(
        evidence,
        ok,
        reason,
        detection,
        gate,
        policy,
        leading_grid_failure,
    )


__all__ = [
    "SeparatorGateEvidence",
    "enhanced_gap_promotion_accepted_count",
    "hard_gap_indexes_are_adjacent_late",
    "hard_gap_indexes_from_gaps",
    "leading_grid_scores_from_gaps",
    "separator_gate_all_internal_gaps_hard_assessment",
    "separator_gate_broad_width_support_assessment",
    "separator_gate_edge_pair_support_assessment",
    "separator_gate_geometry_support_assessment",
    "separator_gate_leading_grid_failure_assessment",
    "separator_gate_min_hard_with_equal_cap_assessment",
    "separator_gate_needs_full_strip_supplemental_checks",
    "separator_gate_detail",
    "separator_gate_evidence_from_detection",
    "candidate_has_hard_separator_evidence",
]
