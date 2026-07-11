from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...domain import Gap
from ...gap_methods import (
    is_content_model_gap_method,
    is_detected_gap_method,
    is_hard_gap_method,
    is_edge_pair_gap_method,
    is_equal_model_gap_method,
)


@dataclass(frozen=True)
class GapMethodEvidenceSummary:
    direct_hard_gaps: int
    hard_separator_gaps: int
    equal_model_gaps: int
    content_model_gaps: int
    separator_support_count: int
    reliable_support_count: int
    hard_gap_indexes: tuple[int, ...]
    edge_pair_scores: tuple[float, ...]
    detected_scores: tuple[float, ...]

@dataclass(frozen=True)
class SeparatorSupportDetailSummary:
    expected_gaps: int
    hard_separator_gaps: int
    equal_model_gaps: int
    content_model_gaps: int = 0

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
    equal_model_gaps = 0
    content_model_gaps = 0
    reliable_support_count = 0
    hard_gap_indexes: list[int] = []
    edge_pair_scores: list[float] = []
    detected_scores: list[float] = []

    for gap in gaps:
        method = gap.method
        if is_hard_gap_method(method):
            direct_hard_gaps += 1
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
        if is_hard_gap_method(method) and gap.score >= reliable_min_score:
            reliable_support_count += 1

    hard_separator_gaps = direct_hard_gaps
    separator_support_count = hard_separator_gaps
    return GapMethodEvidenceSummary(
        direct_hard_gaps=direct_hard_gaps,
        hard_separator_gaps=hard_separator_gaps,
        equal_model_gaps=equal_model_gaps,
        content_model_gaps=content_model_gaps,
        separator_support_count=separator_support_count,
        reliable_support_count=reliable_support_count,
        hard_gap_indexes=tuple(hard_gap_indexes),
        edge_pair_scores=tuple(edge_pair_scores),
        detected_scores=tuple(detected_scores),
    )


def separator_support_detail_summary(
    hard_detail: dict[str, Any],
    *,
    expected_default: int = 0,
    hard_default: int = 0,
    equal_default: int = 0,
    content_default: int = 0,
) -> SeparatorSupportDetailSummary:
    detail = _dict(hard_detail)
    return SeparatorSupportDetailSummary(
        expected_gaps=max(0, _int(detail.get("expected_gaps"), expected_default)),
        hard_separator_gaps=_int(detail.get("hard_gaps"), hard_default),
        equal_model_gaps=_int(detail.get("equal_gaps"), equal_default),
        content_model_gaps=_int(detail.get("content_gaps"), content_default),
    )
