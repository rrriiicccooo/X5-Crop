from __future__ import annotations

ANALYSIS_SOURCE_SEPARATOR = "separator_candidate"
ANALYSIS_SOURCE_CONTENT = "content_candidate"
ANALYSIS_SOURCE_CONTENT_PRIMARY = "content_primary"
ANALYSIS_SOURCE_HARD_FALLBACK = "hard_fallback"
ANALYSIS_SOURCE_UNSUPPORTED = "unsupported_mode"
ANALYSIS_SOURCE_PARALLEL_LANE = "parallel_lane_strip"

GAP_DETECTED = "detected"
GAP_EDGE_PAIR = "edge-pair"
GAP_ENHANCED_DETECTED = "enhanced-detected"
GAP_WIDE_SEPARATOR = "wide-separator"
GAP_GRID = "grid"
GAP_EQUAL = "equal"
GAP_CONTENT = "content"

HARD_GAP_METHODS = {
    GAP_DETECTED,
    GAP_EDGE_PAIR,
    GAP_ENHANCED_DETECTED,
    GAP_WIDE_SEPARATOR,
}
MODEL_GAP_METHODS = {
    GAP_GRID,
    GAP_EQUAL,
    GAP_CONTENT,
}

REASON_AUTO_GATE_NOT_SATISFIED = "auto_gate_not_satisfied"
REASON_SEPARATOR_HARD_EVIDENCE_WEAK = "separator_hard_evidence_weak"
REASON_CONTENT_EVIDENCE_WEAK = "content_evidence_weak"
REASON_CONTENT_ASPECT_CONFLICT = "content_aspect_conflict"
REASON_OUTER_CONTENT_BBOX_MISMATCH = "outer_content_bbox_mismatch"
REASON_LUCKY_PASS_RISK = "lucky_pass_risk"
