from __future__ import annotations

from typing import Any


def gap_run_evaluation_summary(
    evaluations: list[dict[str, Any]] | None,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    evaluations = evaluations or []
    accepted = [item for item in evaluations if bool(item.get("accepted", False))]
    rejected = [item for item in evaluations if not bool(item.get("accepted", False))]
    return {
        "evaluated_run_count": len(evaluations),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted": accepted[:limit],
        "rejected": rejected[:limit],
    }


def attach_gap_run_evaluation_summary(
    detail: dict[str, Any],
    evaluations: list[dict[str, Any]] | None,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    result = dict(detail)
    result.update(gap_run_evaluation_summary(evaluations, limit=limit))
    return result
