from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PartialCountParameters:
    offsets: tuple[float, ...]
    include_default_auto: bool

@dataclass(frozen=True)
class PartialEdgeHintParameters:
    window_ratio: float
    window_min: int
    window_max: int

__all__ = [
    'PartialCountParameters',
    'PartialEdgeHintParameters',
]
