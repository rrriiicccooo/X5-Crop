from __future__ import annotations

from dataclasses import dataclass

from ..model import AssessedCandidate
from ..plan.count_hypotheses import CountHypothesis
from ..selection.model import SelectionResult


@dataclass(frozen=True)
class CountHypothesisEvaluation:
    hypothesis: CountHypothesis
    candidates: tuple[AssessedCandidate, ...]
    selection: SelectionResult | None

    @property
    def geometry_resolved(self) -> bool:
        return bool(
            self.selection is not None
            and self.selection.geometry_resolution.supported
        )


@dataclass(frozen=True)
class OffsetEvaluation:
    candidates: tuple[AssessedCandidate, ...]
    selection: SelectionResult | None

    @property
    def geometry_resolved(self) -> bool:
        return bool(
            self.selection is not None
            and self.selection.geometry_resolution.supported
        )
