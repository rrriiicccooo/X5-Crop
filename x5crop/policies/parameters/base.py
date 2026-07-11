from __future__ import annotations

from dataclasses import dataclass
@dataclass(frozen=True)
class PartialCountParameters:
    offsets: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
