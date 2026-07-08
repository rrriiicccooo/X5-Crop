from __future__ import annotations

from ...domain import Detection
from ..detail import CANDIDATE_SIGNALS, candidate_signals_from_detail


SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK = "separator_hard_support_weak"
SIGNAL_SEPARATOR_MODEL_GAP_OVERUSED = "separator_model_gap_overused"
SIGNAL_SEPARATOR_HARD_GAP_FLOOR_FAILED = "separator_hard_gap_floor_failed"
SIGNAL_SEPARATOR_EXPECTED_SUPPORT_INCOMPLETE = "separator_expected_support_incomplete"
SIGNAL_SEPARATOR_CROSS_AXIS_CONTINUITY_WEAK = "separator_cross_axis_continuity_weak"
SIGNAL_EDGE_ANCHOR_HARD_SEPARATOR_MISSING = "edge_anchor_hard_separator_missing"
SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING = "content_guided_hard_separator_missing"

SIGNAL_PHOTO_WIDTH_UNSTABLE = "photo_width_unstable"
SIGNAL_FRAME_COUNT_MISMATCH = "frame_count_mismatch"
SIGNAL_FRAME_EXTENT_INVALID = "frame_extent_invalid"
SIGNAL_FRAME_ORDER_INVALID = "frame_order_invalid"
SIGNAL_FRAME_OVERLAP_DETECTED = "frame_overlap_detected"

SIGNAL_CONTENT_EVIDENCE_WEAK = "content_evidence_weak"
SIGNAL_CONTENT_ASPECT_CONFLICT = "content_aspect_conflict"
SIGNAL_CONTENT_HARM_RISK = "content_harm_risk"
SIGNAL_CONTENT_OUTSIDE_OUTER = "content_outside_outer"
SIGNAL_CONTENT_ONLY_NOT_ENOUGH_FOR_AUTO = "content_only_not_enough_for_auto"

SIGNAL_CONTENT_GRID_FALLBACK = "content_grid_fallback"
SIGNAL_CONTENT_RUN_COUNT_MISMATCH = "content_run_count_mismatch"
SIGNAL_CONTENT_RUNS_INCOMPLETE = "content_runs_incomplete"
SIGNAL_CONTENT_COVERAGE_WEAK = "content_coverage_weak"
SIGNAL_CONTENT_ASPECT_UNCERTAIN = "content_aspect_uncertain"
SIGNAL_CONTENT_CONFIDENCE_LOW = "content_confidence_low"

SIGNAL_PARTIAL_COUNT_AMBIGUOUS = "partial_count_ambiguous"
SIGNAL_PARTIAL_LEADING_CONTENT_RISK = "partial_leading_content_risk"
SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE = "partial_frame_content_unstable"
SIGNAL_HOLDER_EDGE_DISAMBIGUATION_WEAK = "holder_edge_disambiguation_weak"

SIGNAL_OUTER_OVERCONTAINS_HOLDER_AREA = "outer_overcontains_holder_area"
SIGNAL_OUTER_SCOPE_UNCERTAIN = "outer_scope_uncertain"

SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_RISK = "evidence_dependency_cycle_risk"
SIGNAL_SAFETY_CANDIDATE_GATE_BLOCKED = "safety_candidate_gate_blocked"

SIGNAL_HARD_SAFETY_NO_CANDIDATES = "hard_safety_no_candidates"
SIGNAL_NEEDS_MANUAL_REVIEW = "needs_manual_review"
SIGNAL_DUAL_LANE_DETECTION_FAILED = "dual_lane_detection_failed"
SIGNAL_DUAL_LANE_OUTER_DETECTION_FAILED = "dual_lane_outer_detection_failed"
SIGNAL_DUAL_LANE_BELOW_THRESHOLD = "dual_lane_below_threshold"
SIGNAL_DUAL_LANE_PARTIAL_NOT_SUPPORTED = "dual_lane_partial_not_supported"

SEPARATOR_BLOCKER_SIGNALS = frozenset(
    {
        SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK,
        SIGNAL_SEPARATOR_MODEL_GAP_OVERUSED,
        SIGNAL_SEPARATOR_HARD_GAP_FLOOR_FAILED,
        SIGNAL_SEPARATOR_EXPECTED_SUPPORT_INCOMPLETE,
        SIGNAL_SEPARATOR_CROSS_AXIS_CONTINUITY_WEAK,
        SIGNAL_EDGE_ANCHOR_HARD_SEPARATOR_MISSING,
        SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING,
    }
)
PHOTO_SIZE_BLOCKER_SIGNALS = frozenset(
    {
        SIGNAL_PHOTO_WIDTH_UNSTABLE,
    }
)
FRAME_TOPOLOGY_BLOCKER_SIGNALS = frozenset(
    {
        SIGNAL_FRAME_COUNT_MISMATCH,
        SIGNAL_FRAME_EXTENT_INVALID,
        SIGNAL_FRAME_ORDER_INVALID,
        SIGNAL_FRAME_OVERLAP_DETECTED,
    }
)
CONTENT_INTEGRITY_BLOCKER_SIGNALS = frozenset(
    {
        SIGNAL_CONTENT_EVIDENCE_WEAK,
        SIGNAL_CONTENT_ASPECT_CONFLICT,
        SIGNAL_CONTENT_HARM_RISK,
        SIGNAL_CONTENT_OUTSIDE_OUTER,
        SIGNAL_CONTENT_ONLY_NOT_ENOUGH_FOR_AUTO,
    }
)
CONTENT_CANDIDATE_DIAGNOSTIC_SIGNALS = frozenset(
    {
        SIGNAL_CONTENT_GRID_FALLBACK,
        SIGNAL_CONTENT_RUN_COUNT_MISMATCH,
        SIGNAL_CONTENT_RUNS_INCOMPLETE,
        SIGNAL_CONTENT_COVERAGE_WEAK,
        SIGNAL_CONTENT_ASPECT_UNCERTAIN,
        SIGNAL_CONTENT_CONFIDENCE_LOW,
    }
)
PARTIAL_HOLDER_EDGE_BLOCKER_SIGNALS = frozenset(
    {
        SIGNAL_PARTIAL_COUNT_AMBIGUOUS,
        SIGNAL_PARTIAL_LEADING_CONTENT_RISK,
        SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE,
        SIGNAL_HOLDER_EDGE_DISAMBIGUATION_WEAK,
    }
)
OUTER_SCOPE_DIAGNOSTIC_SIGNALS = frozenset(
    {
        SIGNAL_OUTER_OVERCONTAINS_HOLDER_AREA,
        SIGNAL_OUTER_SCOPE_UNCERTAIN,
    }
)
EVIDENCE_INDEPENDENCE_BLOCKER_SIGNALS = frozenset(
    {
        SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_RISK,
    }
)
SAFETY_BLOCKER_SIGNALS = frozenset(
    {
        SIGNAL_SAFETY_CANDIDATE_GATE_BLOCKED,
    }
)
MODE_DIAGNOSTIC_SIGNALS = frozenset(
    {
        SIGNAL_HARD_SAFETY_NO_CANDIDATES,
        SIGNAL_NEEDS_MANUAL_REVIEW,
        SIGNAL_DUAL_LANE_DETECTION_FAILED,
        SIGNAL_DUAL_LANE_OUTER_DETECTION_FAILED,
        SIGNAL_DUAL_LANE_BELOW_THRESHOLD,
        SIGNAL_DUAL_LANE_PARTIAL_NOT_SUPPORTED,
    }
)

GATE_BLOCKER_SIGNALS = frozenset(
    {
        *SEPARATOR_BLOCKER_SIGNALS,
        *PHOTO_SIZE_BLOCKER_SIGNALS,
        *FRAME_TOPOLOGY_BLOCKER_SIGNALS,
        *CONTENT_INTEGRITY_BLOCKER_SIGNALS,
        *PARTIAL_HOLDER_EDGE_BLOCKER_SIGNALS,
        *EVIDENCE_INDEPENDENCE_BLOCKER_SIGNALS,
        *SAFETY_BLOCKER_SIGNALS,
    }
)
GATE_DIAGNOSTIC_SIGNALS = frozenset(
    {
        *CONTENT_CANDIDATE_DIAGNOSTIC_SIGNALS,
        *OUTER_SCOPE_DIAGNOSTIC_SIGNALS,
    }
)
CANDIDATE_SIGNAL_TAXONOMY = frozenset(
    {
        *GATE_BLOCKER_SIGNALS,
        *GATE_DIAGNOSTIC_SIGNALS,
        *MODE_DIAGNOSTIC_SIGNALS,
    }
)

SIGNAL_BUCKETS = {
    **{signal: "separator" for signal in SEPARATOR_BLOCKER_SIGNALS},
    **{signal: "photo_size" for signal in PHOTO_SIZE_BLOCKER_SIGNALS},
    **{signal: "frame_topology" for signal in FRAME_TOPOLOGY_BLOCKER_SIGNALS},
    **{signal: "content" for signal in CONTENT_INTEGRITY_BLOCKER_SIGNALS},
    **{signal: "content_candidate" for signal in CONTENT_CANDIDATE_DIAGNOSTIC_SIGNALS},
    **{signal: "partial_edge" for signal in PARTIAL_HOLDER_EDGE_BLOCKER_SIGNALS},
    **{signal: "outer" for signal in OUTER_SCOPE_DIAGNOSTIC_SIGNALS},
    **{signal: "evidence" for signal in EVIDENCE_INDEPENDENCE_BLOCKER_SIGNALS},
    **{signal: "source" for signal in SAFETY_BLOCKER_SIGNALS},
    **{signal: "mode" for signal in MODE_DIAGNOSTIC_SIGNALS},
}


def normalized_candidate_signals(signals: list[str]) -> list[str]:
    return sorted(set(str(signal) for signal in signals if signal))


def candidate_signals(detection: Detection) -> list[str]:
    return candidate_signals_from_detail(detection)


def set_candidate_signals(detection: Detection, signals: list[str]) -> None:
    detection.detail[CANDIDATE_SIGNALS] = normalized_candidate_signals(signals)


def add_candidate_signals(detection: Detection, signals: list[str]) -> None:
    set_candidate_signals(detection, [*candidate_signals(detection), *signals])


def add_candidate_signal(detection: Detection, signal: str) -> None:
    add_candidate_signals(detection, [signal])


def merged_candidate_signals(detection: Detection, signals: list[str]) -> list[str]:
    return normalized_candidate_signals([*candidate_signals(detection), *signals])


def unknown_candidate_signals(signals: list[str], *, ignored: set[str] | None = None) -> list[str]:
    ignored = ignored or set()
    return [
        signal
        for signal in normalized_candidate_signals(signals)
        if signal not in ignored and signal not in CANDIDATE_SIGNAL_TAXONOMY
    ]


__all__ = [
    "CANDIDATE_SIGNAL_TAXONOMY",
    "CONTENT_CANDIDATE_DIAGNOSTIC_SIGNALS",
    "CONTENT_INTEGRITY_BLOCKER_SIGNALS",
    "EVIDENCE_INDEPENDENCE_BLOCKER_SIGNALS",
    "GATE_BLOCKER_SIGNALS",
    "GATE_DIAGNOSTIC_SIGNALS",
    "MODE_DIAGNOSTIC_SIGNALS",
    "OUTER_SCOPE_DIAGNOSTIC_SIGNALS",
    "PARTIAL_HOLDER_EDGE_BLOCKER_SIGNALS",
    "FRAME_TOPOLOGY_BLOCKER_SIGNALS",
    "PHOTO_SIZE_BLOCKER_SIGNALS",
    "SAFETY_BLOCKER_SIGNALS",
    "SEPARATOR_BLOCKER_SIGNALS",
    "SIGNAL_BUCKETS",
    "SIGNAL_CONTENT_ASPECT_CONFLICT",
    "SIGNAL_CONTENT_ASPECT_UNCERTAIN",
    "SIGNAL_CONTENT_CONFIDENCE_LOW",
    "SIGNAL_CONTENT_COVERAGE_WEAK",
    "SIGNAL_CONTENT_EVIDENCE_WEAK",
    "SIGNAL_CONTENT_GRID_FALLBACK",
    "SIGNAL_CONTENT_GUIDED_HARD_SEPARATOR_MISSING",
    "SIGNAL_CONTENT_HARM_RISK",
    "SIGNAL_CONTENT_ONLY_NOT_ENOUGH_FOR_AUTO",
    "SIGNAL_CONTENT_OUTSIDE_OUTER",
    "SIGNAL_CONTENT_RUNS_INCOMPLETE",
    "SIGNAL_CONTENT_RUN_COUNT_MISMATCH",
    "SIGNAL_DUAL_LANE_BELOW_THRESHOLD",
    "SIGNAL_DUAL_LANE_DETECTION_FAILED",
    "SIGNAL_DUAL_LANE_OUTER_DETECTION_FAILED",
    "SIGNAL_DUAL_LANE_PARTIAL_NOT_SUPPORTED",
    "SIGNAL_EDGE_ANCHOR_HARD_SEPARATOR_MISSING",
    "SIGNAL_EVIDENCE_DEPENDENCY_CYCLE_RISK",
    "SIGNAL_FRAME_COUNT_MISMATCH",
    "SIGNAL_FRAME_EXTENT_INVALID",
    "SIGNAL_FRAME_ORDER_INVALID",
    "SIGNAL_FRAME_OVERLAP_DETECTED",
    "SIGNAL_HARD_SAFETY_NO_CANDIDATES",
    "SIGNAL_HOLDER_EDGE_DISAMBIGUATION_WEAK",
    "SIGNAL_NEEDS_MANUAL_REVIEW",
    "SIGNAL_OUTER_OVERCONTAINS_HOLDER_AREA",
    "SIGNAL_OUTER_SCOPE_UNCERTAIN",
    "SIGNAL_PARTIAL_COUNT_AMBIGUOUS",
    "SIGNAL_PARTIAL_FRAME_CONTENT_UNSTABLE",
    "SIGNAL_PARTIAL_LEADING_CONTENT_RISK",
    "SIGNAL_PHOTO_WIDTH_UNSTABLE",
    "SIGNAL_SAFETY_CANDIDATE_GATE_BLOCKED",
    "SIGNAL_SEPARATOR_EXPECTED_SUPPORT_INCOMPLETE",
    "SIGNAL_SEPARATOR_CROSS_AXIS_CONTINUITY_WEAK",
    "SIGNAL_SEPARATOR_HARD_GAP_FLOOR_FAILED",
    "SIGNAL_SEPARATOR_HARD_SUPPORT_WEAK",
    "SIGNAL_SEPARATOR_MODEL_GAP_OVERUSED",
    "add_candidate_signal",
    "add_candidate_signals",
    "candidate_signals",
    "merged_candidate_signals",
    "normalized_candidate_signals",
    "set_candidate_signals",
    "unknown_candidate_signals",
]
