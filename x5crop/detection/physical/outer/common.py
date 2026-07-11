from __future__ import annotations

from collections.abc import Iterable

from .types import OuterProposal


def unique_outer_proposals(candidates: Iterable[OuterProposal]) -> list[OuterProposal]:
    seen: set[tuple[int, int, int, int, str, str]] = set()
    out: list[OuterProposal] = []
    for candidate in candidates:
        box = candidate.box
        key = (
            box.left,
            box.top,
            box.right,
            box.bottom,
            candidate.provenance.root_measurement,
            candidate.provenance.source,
        )
        if key in seen or not box.valid():
            continue
        seen.add(key)
        out.append(candidate)
    return out
