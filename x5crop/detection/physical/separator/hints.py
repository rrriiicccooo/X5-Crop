from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SeparatorGapHint:
    index: int
    center: float
    source_start: float
    source_end: float

    def detail(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SeparatorGapHintSet:
    source: str
    role: str
    hints: tuple[SeparatorGapHint, ...]
    max_offset_ratio: float
    max_offset_min: int
    max_offset_max: int
    detail: dict[str, Any] = field(default_factory=dict)

    def hint_for_index(self, index: int) -> Optional[SeparatorGapHint]:
        for hint in self.hints:
            if hint.index == index:
                return hint
        return None

    def summary(self) -> dict[str, Any]:
        return {
            "used": bool(self.hints),
            "source": self.source,
            "role": self.role,
            "hint_count": len(self.hints),
            "max_offset_ratio": float(self.max_offset_ratio),
            "max_offset_min": int(self.max_offset_min),
            "max_offset_max": int(self.max_offset_max),
            "hints": [hint.detail() for hint in self.hints],
            **dict(self.detail),
        }
