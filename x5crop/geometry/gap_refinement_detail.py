from __future__ import annotations

from typing import Any


def _limited(items: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    return list(items) if limit is None else list(items)[:limit]


def gap_refinement_batch_detail(
    *,
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    searched: list[dict[str, Any]] | None = None,
    accepted_limit: int | None = None,
    rejected_limit: int | None = 8,
    searched_limit: int | None = 8,
) -> dict[str, Any]:
    detail: dict[str, Any] = {}
    if searched is not None:
        detail["searched"] = _limited(searched, searched_limit)
        detail["searched_count"] = len(searched)
    detail["accepted"] = _limited(accepted, accepted_limit)
    detail["accepted_count"] = len(accepted)
    detail["rejected"] = _limited(rejected, rejected_limit)
    detail["rejected_count"] = len(rejected)
    return detail


__all__ = ["gap_refinement_batch_detail"]
