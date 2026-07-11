from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorWidthProfileParameters:
    band_candidate_count: int = 10
    sequence_candidate_count: int = 4
    max_candidates: int = 4
