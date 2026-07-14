from __future__ import annotations

from dataclasses import dataclass

from ....domain import EvidenceState, PhysicalSearchOutcome
from ..model import AssessedCandidate
from ..plan.model import CountHypothesis
from ..selection.model import SelectionResult


@dataclass(frozen=True)
class CountHypothesisEvaluation:
    hypothesis: CountHypothesis
    candidates: tuple[AssessedCandidate, ...]
    selection: SelectionResult | None
    physical_search: PhysicalSearchOutcome

    def __post_init__(self) -> None:
        if any(
            candidate.geometry.count != self.hypothesis.count
            or candidate.geometry.strip_mode != self.hypothesis.strip_mode
            or candidate.count_hypothesis != self.hypothesis
            for candidate in self.candidates
        ):
            raise ValueError("count evaluation candidates must match its hypothesis")
        if (self.selection is None) != (not self.candidates):
            raise ValueError("count evaluation selection must match candidate availability")
        if self.selection is not None and {
            id(candidate) for candidate in self.selection.ranked_candidates
        } != {id(candidate) for candidate in self.candidates}:
            raise ValueError("count evaluation selection must cover its candidates")
        if (
            self.selection is not None
            and self.selection.geometry_resolution.physical_search
            != self.physical_search
        ):
            raise ValueError("count evaluation search state must match its selection")

    @property
    def geometry_resolved(self) -> bool:
        return bool(
            self.selection is not None
            and self.selection.geometry_resolution.supported
        )

    @property
    def hypothesis_state(self) -> EvidenceState:
        if self.geometry_resolved:
            return EvidenceState.SUPPORTED
        if (
            not self.candidates
            and self.physical_search.state == EvidenceState.CONTRADICTED
        ):
            return EvidenceState.CONTRADICTED
        return EvidenceState.UNAVAILABLE
