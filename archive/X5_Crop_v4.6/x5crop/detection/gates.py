from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..common import Detection, FORMATS, FormatTuning
from ..constants import HARD_GAP_METHODS
from ..policies import DetectionPolicy, get_detection_policy


@dataclass(frozen=True)
class GateResult:
    name: str
    ok: bool
    reason: str
    detail: dict[str, Any]


def separator_gate_135_decision(
    expected: int,
    hard: int,
    equal: int,
    tuning: FormatTuning,
) -> tuple[bool, str]:
    needed = min(expected, tuning.separator_135_needed_hard_max)
    ok = hard >= needed and equal <= max(tuning.separator_135_max_equal_min, expected // 2)
    return ok, "135_hard_separator_support" if ok else "135_separator_support_weak"


def separator_gate_half_decision(
    detection: Detection,
    threshold: float,
    equal: int,
    expected: int,
    tuning: FormatTuning,
) -> tuple[bool, str]:
    ok = bool(tuning.separator_half_allow_geometry_support) and detection.confidence >= threshold and equal <= expected
    return ok, "half_geometry_support" if ok else "half_separator_support_weak"


def separator_gate_hard_required_decision(
    detection: Detection,
    expected: int,
    hard: int,
    wide: int,
    edge_pair_scores: list[float],
    tuning: FormatTuning,
) -> tuple[bool, str]:
    needed = max(1, expected if tuning.separator_hard_required_all_gaps else min(expected, 1))
    ok = hard >= needed
    reason = "120_hard_separator_support" if ok else "120_separator_support_weak"
    if ok and detection.strip_mode == "full" and detection.count == FORMATS[detection.film_format].default_count:
        if wide < tuning.separator_gate_120_min_wide_gaps_for_auto:
            ok = False
            reason = "120_wide_separator_support_weak"
        edge_min = (
            tuning.separator_gate_120_edge_pair_min_score_with_wide
            if wide > 0
            else tuning.separator_gate_120_edge_pair_min_score_without_wide
        )
        if ok and edge_pair_scores and min(edge_pair_scores) < edge_min:
            ok = False
            reason = "120_edge_pair_support_weak"
    return ok, reason


def separator_hard_evidence_ok(
    detection: Detection,
    threshold: float,
    policy: Optional[DetectionPolicy] = None,
) -> tuple[bool, dict[str, Any]]:
    policy = policy or get_detection_policy(detection.film_format, detection.strip_mode)
    tuning = policy.tuning
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
        tuning.leading_grid_failure_enabled
        and detection.strip_mode == "full"
        and expected >= tuning.leading_grid_failure_min_count
        and len(leading_grid_scores) >= tuning.leading_grid_failure_leading_count
        and all(score < tuning.leading_grid_failure_low_score for score in leading_grid_scores[:tuning.leading_grid_failure_leading_count])
        and sum(1 for score in leading_grid_scores[:tuning.leading_grid_failure_leading_count] if score < tuning.leading_grid_failure_very_low_score) >= tuning.leading_grid_failure_very_low_count
        and enhanced_accepted == 0
        and len(hard_indexes) <= tuning.leading_grid_failure_max_hard
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
        reason = "135_leading_grid_separator_failure"
    elif policy.separator.gate_mode == "135":
        ok, reason = separator_gate_135_decision(expected, hard, equal, tuning)
    elif policy.separator.gate_mode == "half":
        ok, reason = separator_gate_half_decision(detection, threshold, equal, expected, tuning)
    else:
        ok, reason = separator_gate_hard_required_decision(
            detection,
            expected,
            hard,
            wide,
            edge_pair_scores,
            tuning,
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
        "format_policy": tuning.name,
    }


__all__ = [
    "GateResult",
    "separator_gate_135_decision",
    "separator_gate_half_decision",
    "separator_gate_hard_required_decision",
    "separator_hard_evidence_ok",
]
