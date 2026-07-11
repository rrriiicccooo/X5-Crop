from __future__ import annotations

from dataclasses import dataclass

from ....domain import MeasurementProvenance


@dataclass(frozen=True)
class SeparatorGapHint:
    index: int
    work_center: float
    work_start: float
    work_end: float

@dataclass(frozen=True)
class SeparatorGapHintSet:
    hints: tuple[SeparatorGapHint, ...]
    max_offset_ratio: float
    max_offset_min: int
    max_offset_max: int
    provenance: MeasurementProvenance

    def hint_for_index(self, index: int) -> SeparatorGapHint | None:
        for hint in self.hints:
            if hint.index == index:
                return hint
        return None
