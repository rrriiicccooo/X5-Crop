from __future__ import annotations

from typing import Any

from ...domain import Gap
from ...gap_methods import is_hard_gap_method


def separator_width_requirement_detail(detail: dict[str, Any], min_required: int) -> dict[str, Any]:
    result = dict(detail)
    min_required = max(0, int(min_required))
    count = int(
        result.get(
            "broad_separator_width_gaps",
            result.get("separator_width_gap_count", 0),
        ) or 0
    )
    result["min_broad_separator_width_gaps"] = min_required
    if bool(result.get("used", False)):
        ok = count >= min_required
        result["reason"] = "ok" if ok else "too_few_broad_separator_width_gaps"
    return result


def separator_width_evidence_detail(
    gaps: list[Gap],
    short_axis: float,
    min_width_ratio: float,
    min_required: int = 0,
) -> dict[str, Any]:
    min_required = max(0, int(min_required))
    if short_axis <= 0.0 or min_width_ratio <= 0.0:
        return {
            "used": False,
            "reason": "disabled",
            "separator_width_class": "unknown",
            "broad_separator_width_gaps": 0,
            "min_broad_separator_width_gaps": min_required,
            "broad_separator_width_gap_indexes": [],
            "separator_width_gap_count": 0,
            "separator_width_gap_indexes": [],
            "separator_width_min_px": 0.0,
            "gap_widths": [float(gap.width) for gap in gaps],
            "broad_separator_width_scores": [],
        }

    min_width = max(1.0, float(short_axis) * float(min_width_ratio))
    broad_indexes: list[int] = []
    broad_scores: list[float] = []
    gap_widths: list[float] = []
    for gap in gaps:
        width = float(gap.width)
        gap_widths.append(width)
        if is_hard_gap_method(gap.method) and width >= min_width:
            broad_indexes.append(int(gap.index))
            broad_scores.append(float(gap.score))

    count = len(broad_indexes)
    detail = {
        "used": True,
        "reason": "ok",
        "separator_width_class": "broad" if count > 0 else "standard",
        "broad_separator_width_gaps": int(count),
        "min_broad_separator_width_gaps": int(min_required),
        "broad_separator_width_gap_indexes": broad_indexes,
        "separator_width_gap_count": int(count),
        "separator_width_gap_indexes": broad_indexes,
        "separator_width_min_px": float(min_width),
        "gap_widths": gap_widths,
        "broad_separator_width_scores": broad_scores,
    }
    return separator_width_requirement_detail(detail, min_required)


__all__ = [
    "separator_width_evidence_detail",
    "separator_width_requirement_detail",
]
