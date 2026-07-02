from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ...constants import HARD_GAP_METHODS
from ...domain import Detection
from ...formats import FORMATS
from ...policies.registry import get_detection_policy
from ...policies.runtime_policy import DetectionPolicy
from ...policies.runtime_separator import SeparatorGatePolicy


@dataclass(frozen=True)
class CandidateGateOutcome:
    name: str
    ok: bool
    reason: str
    detail: dict[str, Any]


def separator_gate_min_hard_with_equal_cap_assessment(
    expected: int,
    hard: int,
    equal: int,
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    needed = min(expected, gate.needed_hard_max)
    ok = hard >= needed and equal <= max(gate.max_equal_gaps_floor, expected // 2)
    return ok, "separator_min_hard_support" if ok else "separator_min_hard_support_weak"


def separator_gate_geometry_support_assessment(
    detection: Detection,
    threshold: float,
    equal: int,
    expected: int,
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    ok = bool(gate.allow_geometry_support) and detection.confidence >= threshold and equal <= expected
    return ok, "separator_geometry_support" if ok else "separator_geometry_support_weak"


def separator_gate_all_internal_gaps_hard_assessment(
    detection: Detection,
    expected: int,
    hard: int,
    wide: int,
    edge_pair_scores: list[float],
    gate: SeparatorGatePolicy,
) -> tuple[bool, str]:
    needed = max(1, expected if gate.hard_required_all_gaps else min(expected, 1))
    ok = hard >= needed
    reason = "separator_all_internal_gaps_hard_support" if ok else "separator_all_internal_gaps_hard_support_weak"
    if ok and detection.strip_mode == "full" and detection.count == FORMATS[detection.film_format].default_count:
        if wide < gate.min_wide_gaps_for_auto:
            ok = False
            reason = "separator_wide_support_weak"
        edge_min = (
            gate.edge_pair_min_score_with_wide
            if wide > 0
            else gate.edge_pair_min_score_without_wide
        )
        if ok and edge_pair_scores and min(edge_pair_scores) < edge_min:
            ok = False
            reason = "separator_edge_pair_support_weak"
    return ok, reason


def candidate_has_hard_separator_evidence(
    detection: Detection,
    threshold: float,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[bool, dict[str, Any]]:
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    gate = policy.separator.gate
    leading_grid_policy = gate.leading_grid_failure
    expected = max(0, int(detection.count) - 1)
    actual = int(detection.detail.get("actual_detected_gaps", 0))
    wide = int(detection.detail.get("wide_detected_gaps", 0))
    enhanced = int(detection.detail.get("enhanced_detected_gaps", 0))
    grid = int(detection.detail.get("grid_gaps", 0))
    equal = int(detection.detail.get("equal_gaps", 0))
    hard = actual + wide + enhanced
    hard_indexes = [
        int(gap.index)
        for gap in detection.gaps
        if gap.method in HARD_GAP_METHODS
    ]
    edge_pair_scores = [
        float(gap.score)
        for gap in detection.gaps
        if gap.method == "edge-pair"
    ]
    detected_scores = [
        float(gap.score)
        for gap in detection.gaps
        if gap.method == "detected"
    ]
    wide_scores = [
        float(gap.score)
        for gap in detection.gaps
        if gap.method == "wide-separator"
    ]
    leading_grid_scores: list[float] = []
    for gap in detection.gaps:
        if gap.method != "grid":
            break
        leading_grid_scores.append(float(gap.score))
    separator_analysis = detection.detail.get("separator_analysis", {})
    enhanced_accepted = (
        int(separator_analysis.get("accepted_count", 0) or 0)
        if isinstance(separator_analysis, dict)
        else 0
    )
    hard_adjacent_late = False
    if hard_indexes:
        expected_sequence = list(
            range(max(hard_indexes) - len(hard_indexes) + 1, max(hard_indexes) + 1)
        )
        hard_adjacent_late = hard_indexes == expected_sequence and min(hard_indexes) >= 4
    leading_grid_failure = (
        leading_grid_policy.enabled
        and detection.strip_mode == "full"
        and expected >= leading_grid_policy.min_expected_gaps
        and len(leading_grid_scores) >= leading_grid_policy.leading_count
        and all(score < leading_grid_policy.low_score for score in leading_grid_scores[:leading_grid_policy.leading_count])
        and sum(1 for score in leading_grid_scores[:leading_grid_policy.leading_count] if score < leading_grid_policy.very_low_score) >= leading_grid_policy.very_low_count
        and enhanced_accepted == 0
        and len(hard_indexes) <= leading_grid_policy.max_hard_gaps
        and hard_adjacent_late
    )

    if expected == 0:
        ok = detection.confidence >= threshold
        reason = "single_frame_no_separator_needed" if ok else "single_frame_low_confidence"
    elif detection.confidence < threshold:
        ok = False
        reason = "separator_below_threshold"
    elif leading_grid_failure:
        ok = False
        reason = "leading_grid_separator_failure"
    elif gate.profile == "min_hard_with_equal_cap":
        ok, reason = separator_gate_min_hard_with_equal_cap_assessment(expected, hard, equal, gate)
    elif gate.profile == "geometry_support":
        ok, reason = separator_gate_geometry_support_assessment(detection, threshold, equal, expected, gate)
    else:
        ok, reason = separator_gate_all_internal_gaps_hard_assessment(
            detection,
            expected,
            hard,
            wide,
            edge_pair_scores,
            gate,
        )

    return ok, {
        "ok": ok,
        "reason": reason,
        "expected_gaps": expected,
        "hard_gaps": hard,
        "actual_detected_gaps": actual,
        "wide_detected_gaps": wide,
        "enhanced_detected_gaps": enhanced,
        "grid_gaps": grid,
        "equal_gaps": equal,
        "hard_gap_indexes": hard_indexes,
        "edge_pair_scores": edge_pair_scores,
        "detected_scores": detected_scores,
        "wide_separator_scores": wide_scores,
        "leading_grid_scores": leading_grid_scores,
        "enhanced_separator_accepted_count": enhanced_accepted,
        "leading_grid_separator_failure": bool(leading_grid_failure),
        "separator_confidence": float(detection.confidence),
        "separator_gate_profile": gate.profile,
        "policy_id": policy.policy_id,
    }


__all__ = [
    "CandidateGateOutcome",
    "separator_gate_all_internal_gaps_hard_assessment",
    "separator_gate_geometry_support_assessment",
    "separator_gate_min_hard_with_equal_cap_assessment",
    "candidate_has_hard_separator_evidence",
]
