from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeparatorBand:
    start: float
    end: float
    center: float
    width: float
    score: float
    oversized: bool = False


__all__ = ["SeparatorBand"]
