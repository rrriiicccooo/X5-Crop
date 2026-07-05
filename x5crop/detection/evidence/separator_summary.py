from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...constants import (
    GAP_CONTENT,
    GAP_DETECTED,
    GAP_EDGE_PAIR,
    GAP_ENHANCED_DETECTED,
    GAP_EQUAL,
    GAP_GRID,
    HARD_GAP_METHODS,
)
from ...domain import Detection, Gap


@dataclass(frozen=True)
class GapMethodEvidenceSummary:
    direct_hard_gaps: int
    enhanced_hard_gaps: int
    hard_separator_gaps: int
    grid_model_gaps: int
    equal_model_gaps: int
    separator_support_gaps: int
    reliable_support_gaps: int


@dataclass(frozen=True)
class SeparatorGateDetailSummary:
    expected_gaps: int
    hard_separator_gaps: int
    grid_model_gaps: int
    equal_model_gaps: int
    content_model_gaps: int = 0
    gate_reason: Any = None
    geometry_support_mode: Any = None
    hard_detail: dict[str, Any] = field(default_factory=dict)

    @property
    def separator_support_gaps(self) -> int:
        return self.hard_separator_gaps + self.grid_model_gaps

    @property
    def model_gaps(self) -> int:
        return self.grid_model_gaps + self.equal_model_gaps + self.content_model_gaps

    @property
    def hard_gap_ratio(self) -> float:
        return self.hard_separator_gaps / float(max(1, self.expected_gaps))

    @property
    def model_gap_share(self) -> float:
        return self.model_gaps / float(max(1, self.expected_gaps))

    def decision_summary(self) -> dict[str, Any]:
        return {
            "expected_gaps": self.expected_gaps,
            "hard_gaps": self.hard_separator_gaps,
            "grid_gaps": self.grid_model_gaps,
            "equal_gaps": self.equal_model_gaps,
            "content_gaps": self.content_model_gaps,
            "model_gaps": self.model_gaps,
            "hard_gap_ratio": self.hard_gap_ratio,
            "model_gap_share": self.model_gap_share,
            "gate_reason": self.gate_reason,
            "geometry_support_mode": self.geometry_support_mode,
            "hard_detail": self.hard_detail,
        }


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _gap_method_count(detection: Detection, methods: set[str]) -> int:
    return sum(1 for gap in detection.gaps if gap.method in methods)


def gap_method_evidence_summary(
    gaps: list[Gap],
    reliable_min_score: float,
) -> GapMethodEvidenceSummary:
    direct_hard_gaps = sum(1 for gap in gaps if gap.method in {GAP_DETECTED, GAP_EDGE_PAIR})
    enhanced_hard_gaps = sum(1 for gap in gaps if gap.method == GAP_ENHANCED_DETECTED)
    hard_separator_gaps = direct_hard_gaps + enhanced_hard_gaps
    grid_model_gaps = sum(1 for gap in gaps if gap.method == GAP_GRID)
    equal_model_gaps = sum(1 for gap in gaps if gap.method == GAP_EQUAL)
    separator_support_gaps = hard_separator_gaps + grid_model_gaps
    reliable_support_gaps = sum(
        1
        for gap in gaps
        if gap.method in HARD_GAP_METHODS.union({GAP_GRID})
        and gap.score >= reliable_min_score
    )
    return GapMethodEvidenceSummary(
        direct_hard_gaps=direct_hard_gaps,
        enhanced_hard_gaps=enhanced_hard_gaps,
        hard_separator_gaps=hard_separator_gaps,
        grid_model_gaps=grid_model_gaps,
        equal_model_gaps=equal_model_gaps,
        separator_support_gaps=separator_support_gaps,
        reliable_support_gaps=reliable_support_gaps,
    )


def separator_gate_detail_summary(
    hard_detail: dict[str, Any],
    *,
    expected_default: int = 0,
    hard_default: int = 0,
    grid_default: int = 0,
    equal_default: int = 0,
    content_default: int = 0,
) -> SeparatorGateDetailSummary:
    detail = _dict(hard_detail)
    return SeparatorGateDetailSummary(
        expected_gaps=max(0, _int(detail.get("expected_gaps"), expected_default)),
        hard_separator_gaps=_int(detail.get("hard_gaps"), hard_default),
        grid_model_gaps=_int(detail.get("grid_gaps"), grid_default),
        equal_model_gaps=_int(detail.get("equal_gaps"), equal_default),
        content_model_gaps=_int(detail.get("content_gaps"), content_default),
        gate_reason=detail.get("reason"),
        geometry_support_mode=detail.get("separator_geometry_support_mode"),
        hard_detail=detail,
    )


def separator_summary_from_detection(detection: Detection) -> SeparatorGateDetailSummary:
    assessment = _dict(detection.detail.get("candidate_assessment"))
    hard_detail = _dict(assessment.get("separator_hard_evidence"))
    return separator_gate_detail_summary(
        hard_detail,
        expected_default=max(0, int(detection.count) - 1),
        hard_default=_gap_method_count(detection, set(HARD_GAP_METHODS)),
        grid_default=_gap_method_count(detection, {GAP_GRID}),
        equal_default=_gap_method_count(detection, {GAP_EQUAL}),
        content_default=_gap_method_count(detection, {GAP_CONTENT}),
    )


__all__ = [
    "GapMethodEvidenceSummary",
    "SeparatorGateDetailSummary",
    "gap_method_evidence_summary",
    "separator_gate_detail_summary",
    "separator_summary_from_detection",
]
