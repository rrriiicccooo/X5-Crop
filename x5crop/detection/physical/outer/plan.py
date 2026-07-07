from __future__ import annotations

from collections.abc import Iterable

from ....domain import OuterCandidate
from .common import unique_outer_candidates


def outer_candidate_strategy(candidate: OuterCandidate | str) -> str:
    if isinstance(candidate, OuterCandidate):
        return candidate.strategy
    candidate_name = str(candidate)
    if candidate_name in {"bw", "white_x", "full_canvas"}:
        return "base_outer"
    return "unknown_outer"


def merge_outer_proposal_candidates(candidates: Iterable[OuterCandidate]) -> list[OuterCandidate]:
    return unique_outer_candidates(candidates)


__all__ = [
    "merge_outer_proposal_candidates",
    "outer_candidate_strategy",
]
