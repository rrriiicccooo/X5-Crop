from __future__ import annotations

from ...configuration.model import FrameCountMode
from ..candidate.assessment.model import CandidateGateAssessment
from ..gate_checks import GateCheck, GateGap, GateStage
from .model import DecisionGateAssessment
from .vocabulary import (
    FINAL_REASON_CAPACITY_OUTPUT_SLOT_COUNT_UNFULFILLED,
    FINAL_REASON_DIRECT_USE_BUDGET_EXCEEDED,
    FINAL_REASON_DIRECT_USE_BUDGET_UNAVAILABLE,
    FINAL_REASON_FORMAT_PLACEMENT_UNAVAILABLE,
    FINAL_REASON_OUTPUT_TRANSFORM_UNAVAILABLE,
    FINAL_REASON_PLACEMENT_SET_CONTAINMENT_UNAVAILABLE,
    FINAL_REASON_REQUESTED_COUNT_UNFULFILLED,
    FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE,
    FINAL_REASON_SHARED_STRIP_DIRECTION_NONUNIQUE,
    FINAL_REASON_SHARED_STRIP_DIRECTION_UNAVAILABLE,
    FINAL_REASON_SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED,
    FINAL_REASON_SOURCE_FRAME_GEOMETRY_UNAVAILABLE,
    FINAL_REASON_SOURCE_LANE_AUTHORITY_INVALID,
)


_REASON_BY_GAP = {
    GateGap.SCAN_CANVAS_AUTHORITY_UNAVAILABLE: (
        FINAL_REASON_SCAN_CANVAS_AUTHORITY_UNAVAILABLE
    ),
    GateGap.FORMAT_PLACEMENT_UNAVAILABLE: (
        FINAL_REASON_FORMAT_PLACEMENT_UNAVAILABLE
    ),
    GateGap.SHARED_STRIP_DIRECTION_UNAVAILABLE: (
        FINAL_REASON_SHARED_STRIP_DIRECTION_UNAVAILABLE
    ),
    GateGap.SHARED_STRIP_DIRECTION_NONUNIQUE: (
        FINAL_REASON_SHARED_STRIP_DIRECTION_NONUNIQUE
    ),
    GateGap.SOURCE_FRAME_GEOMETRY_UNAVAILABLE: (
        FINAL_REASON_SOURCE_FRAME_GEOMETRY_UNAVAILABLE
    ),
    GateGap.SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED: (
        FINAL_REASON_SLOT_ORDINAL_ASSIGNMENT_UNRESOLVED
    ),
    GateGap.SOURCE_LANE_AUTHORITY_INVALID: (
        FINAL_REASON_SOURCE_LANE_AUTHORITY_INVALID
    ),
    GateGap.PLACEMENT_SET_CONTAINMENT_UNAVAILABLE: (
        FINAL_REASON_PLACEMENT_SET_CONTAINMENT_UNAVAILABLE
    ),
    GateGap.DIRECT_USE_BUDGET_EXCEEDED: (
        FINAL_REASON_DIRECT_USE_BUDGET_EXCEEDED
    ),
    GateGap.DIRECT_USE_BUDGET_UNAVAILABLE: (
        FINAL_REASON_DIRECT_USE_BUDGET_UNAVAILABLE
    ),
    GateGap.OUTPUT_TRANSFORM_UNAVAILABLE: (
        FINAL_REASON_OUTPUT_TRANSFORM_UNAVAILABLE
    ),
}


def _final_reason(
    check: GateCheck,
    count_mode: FrameCountMode,
) -> str:
    if check.gap == GateGap.OUTPUT_SLOT_COUNT_UNAVAILABLE:
        return (
            FINAL_REASON_CAPACITY_OUTPUT_SLOT_COUNT_UNFULFILLED
            if count_mode == FrameCountMode.AUTO
            else FINAL_REASON_REQUESTED_COUNT_UNFULFILLED
        )
    if check.gap is None:
        raise ValueError("supported check has no final review reason")
    return _REASON_BY_GAP[check.gap]


def apply_decision_gate(
    candidate_gate: CandidateGateAssessment,
    count_mode: FrameCountMode,
) -> DecisionGateAssessment:
    return DecisionGateAssessment(
        checks=tuple(
            GateCheck(
                code=check.code,
                stage=GateStage.DECISION,
                state=check.state,
                gap=check.gap,
                final_review_reason=(
                    _final_reason(check, count_mode) if check.blocks else None
                ),
            )
            for check in candidate_gate.checks
        )
    )
