from __future__ import annotations

from collections.abc import Iterable

from .types import SequenceHypothesis


def unique_sequence_span_proposals(
    candidates: Iterable[SequenceHypothesis],
) -> list[SequenceHypothesis]:
    seen: set[tuple[int, int, int, int, str, str]] = set()
    out: list[SequenceHypothesis] = []
    for candidate in candidates:
        box = candidate.crop_envelope.box
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
