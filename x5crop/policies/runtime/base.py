from __future__ import annotations

from dataclasses import dataclass
FULL = "full"
PARTIAL = "partial"


@dataclass(frozen=True)
class DetectorPolicy:
    kind: str = "standard_strip"


@dataclass(frozen=True)
class CountHypothesisPolicy:
    """Placement offsets used while evaluating partial count hypotheses."""

    partial_offsets: tuple[float, ...] = (0.0,)
