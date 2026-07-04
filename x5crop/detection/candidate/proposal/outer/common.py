from __future__ import annotations

from collections.abc import Iterable

from .....domain import OuterCandidate


def unique_outer_candidates(candidates: Iterable[OuterCandidate]) -> list[OuterCandidate]:
    seen: set[tuple[int, int, int, int]] = set()
    out: list[OuterCandidate] = []
    for candidate in candidates:
        box = candidate.box
        key = (box.left, box.top, box.right, box.bottom)
        if key in seen or not box.valid():
            continue
        seen.add(key)
        out.append(candidate)
    return out
