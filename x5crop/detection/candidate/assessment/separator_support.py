from __future__ import annotations

from dataclasses import dataclass, field

from x5crop.domain import EvidenceState, FrameBoundaryReference, FrameBoundarySource
from ...physical.model import SequenceSolution


@dataclass(frozen=True)
class SeparatorSequenceEvidence:
    expected_count: int
    hard_count: int
    dimension_constrained_count: int
    hard_boundaries: tuple[FrameBoundaryReference, ...]
    missing_boundaries: tuple[FrameBoundaryReference, ...]
    hard_tonal_evidence: tuple[float, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if min(
            self.expected_count,
            self.hard_count,
            self.dimension_constrained_count,
        ) < 0:
            raise ValueError("separator sequence counts cannot be negative")
        if self.hard_count != len(self.hard_boundaries):
            raise ValueError("hard separator count must match boundary references")
        if len(self.hard_tonal_evidence) != self.hard_count:
            raise ValueError("hard separator tonal evidence must be complete")
        references = (*self.hard_boundaries, *self.missing_boundaries)
        if len(references) != self.expected_count or len(set(references)) != len(
            references
        ):
            raise ValueError(
                "separator boundary references must be complete and unique"
            )
        state = (
            EvidenceState.NOT_APPLICABLE
            if self.expected_count == 0
            else EvidenceState.SUPPORTED
            if not self.missing_boundaries
            else EvidenceState.UNAVAILABLE
        )
        reason = (
            "single_frame_has_no_internal_separator"
            if self.expected_count == 0
            else "complete_independent_separator_sequence"
            if state == EvidenceState.SUPPORTED
            else "independent_separator_sequence_incomplete"
        )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def separator_sequence_evidence(
    geometry: SequenceSolution,
) -> SeparatorSequenceEvidence:
    expected = max(0, geometry.count - 1)
    accepted = tuple(
        boundary
        for boundary in geometry.frame_boundaries
        if boundary.hard_separator
        and boundary.assignment is not None
        and boundary.assignment.observation.cross_axis.state
        == EvidenceState.SUPPORTED
    )
    indexes = tuple(sorted(boundary.boundary_index for boundary in accepted))
    missing = tuple(
        index for index in range(1, expected + 1) if index not in indexes
    )
    dimension_count = sum(
        boundary.source == FrameBoundarySource.DIMENSION_CONSTRAINED
        for boundary in geometry.frame_boundaries
    )
    return SeparatorSequenceEvidence(
        expected_count=expected,
        hard_count=len(accepted),
        dimension_constrained_count=dimension_count,
        hard_boundaries=tuple(
            FrameBoundaryReference(None, index) for index in indexes
        ),
        missing_boundaries=tuple(
            FrameBoundaryReference(None, index) for index in missing
        ),
        hard_tonal_evidence=tuple(
            float(boundary.assignment.observation.tonal_evidence)
            for boundary in accepted
            if boundary.assignment is not None
        ),
    )
