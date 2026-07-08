from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PartialCountParameters:
    offsets: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    include_default_auto: bool = False

@dataclass(frozen=True)
class PartialEdgeHintParameters:
    window_ratio: float = 0.18
    window_min: int = 8
    window_max: int = 900

__all__ = [
    'PartialCountParameters',
    'PartialEdgeHintParameters',
]
