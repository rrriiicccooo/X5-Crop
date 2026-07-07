from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...domain import Gap
from ...gap_methods import (
    is_content_model_gap_method,
    is_detected_gap_method,
    is_direct_hard_gap_method,
    is_edge_pair_gap_method,
    is_equal_model_gap_method,
    is_grid_model_gap_method,
    is_hard_gap_method,
    is_separator_support_gap_method,
)


@dataclass(frozen=True)
class GapMethodEvidenceSummary:
    direct_hard_gaps: int
    hard_separator_gaps: int
    grid_model_gaps: int
    equal_model_gaps: int
    content_model_gaps: int
    separator_support_count: int
    reliable_support_count: int
    hard_gap_indexes: tuple[int, ...]
    edge_pair_scores: tuple[float, ...]
    detected_scores: tuple[float, ...]
    leading_grid_scores: tuple[float, ...]

    @property
    def separator_support_gaps(self) -> int:
        return self.separator_support_count

    @property
    def reliable_support_gaps(self) -> int:
        return self.reliable_support_count

    @property
    def geometry_model_gaps(self) -> int:
        return self.grid_model_gaps + self.equal_model_gaps

    @property
    def model_gaps(self) -> int:
        return self.geometry_model_gaps + self.content_model_gaps


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
    def separator_support_count(self) -> int:
        return self.hard_separator_gaps + self.grid_model_gaps

    @property
    def separator_support_gaps(self) -> int:
        return self.separator_support_count

    @property
    def model_gaps(self) -> int:
        return self.grid_model_gaps + self.equal_model_gaps + self.content_model_gaps

    @property
    def hard_gap_ratio(self) -> float:
        return self.hard_separator_gaps / float(max(1, self.expected_gaps))

    @property
    def model_gap_share(self) -> float:
        return self.model_gaps / float(max(1, self.expected_gaps))

    def evidence_detail(self) -> dict[str, Any]:
        return {
            "expected_gaps": self.expected_gaps,
            "hard_gaps": self.hard_separator_gaps,
            "grid_gaps": self.grid_model_gaps,
            "equal_gaps": self.equal_model_gaps,
            "content_gaps": self.content_model_gaps,
            "model_gaps": self.model_gaps,
            "separator_support_count": self.separator_support_count,
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

def gap_method_evidence_summary(
    gaps: list[Gap],
    reliable_min_score: float,
) -> GapMethodEvidenceSummary:
    direct_hard_gaps = 0
    grid_model_gaps = 0
    equal_model_gaps = 0
    content_model_gaps = 0
    reliable_support_count = 0
    hard_gap_indexes: list[int] = []
    edge_pair_scores: list[float] = []
    detected_scores: list[float] = []
    leading_grid_scores: list[float] = []
    leading_grid_open = True

    for gap in gaps:
        method = gap.method
        if is_direct_hard_gap_method(method):
            direct_hard_gaps += 1
        if is_grid_model_gap_method(method):
            grid_model_gaps += 1
            if leading_grid_open:
                leading_grid_scores.append(float(gap.score))
        else:
            leading_grid_open = False
        if is_equal_model_gap_method(method):
            equal_model_gaps += 1
        if is_content_model_gap_method(method):
            content_model_gaps += 1
        if is_hard_gap_method(method):
            hard_gap_indexes.append(int(gap.index))
        if is_edge_pair_gap_method(method):
            edge_pair_scores.append(float(gap.score))
        if is_detected_gap_method(method):
            detected_scores.append(float(gap.score))
        if is_separator_support_gap_method(method) and gap.score >= reliable_min_score:
            reliable_support_count += 1

    hard_separator_gaps = direct_hard_gaps
    separator_support_count = hard_separator_gaps + grid_model_gaps
    return GapMethodEvidenceSummary(
        direct_hard_gaps=direct_hard_gaps,
        hard_separator_gaps=hard_separator_gaps,
        grid_model_gaps=grid_model_gaps,
        equal_model_gaps=equal_model_gaps,
        content_model_gaps=content_model_gaps,
        separator_support_count=separator_support_count,
        reliable_support_count=reliable_support_count,
        hard_gap_indexes=tuple(hard_gap_indexes),
        edge_pair_scores=tuple(edge_pair_scores),
        detected_scores=tuple(detected_scores),
        leading_grid_scores=tuple(leading_grid_scores),
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


__all__ = [
    "GapMethodEvidenceSummary",
    "SeparatorGateDetailSummary",
    "gap_method_evidence_summary",
    "separator_gate_detail_summary",
]
