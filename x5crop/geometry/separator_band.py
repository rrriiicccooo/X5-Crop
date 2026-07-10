from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorBand:
    start: float
    end: float
    center: float
    width: float
    score: float


@dataclass(frozen=True)
class SeparatorBandCollection:
    bands: list[SeparatorBand]
    edge_margin: float
