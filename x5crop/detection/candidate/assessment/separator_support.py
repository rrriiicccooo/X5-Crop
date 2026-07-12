from __future__ import annotations

from dataclasses import dataclass

from x5crop.domain import EvidenceState, FrameBoundaryReference
from ...physical.model import SequenceSolution


@dataclass(frozen=True)
class SeparatorSequenceEvidence:
    state: EvidenceState
    reason: str
    expected_count: int
    hard_count: int
    dimension_constrained_count: int
    hard_boundaries: tuple[FrameBoundaryReference, ...]
    missing_boundaries: tuple[FrameBoundaryReference, ...]
    hard_tonal_evidence: tuple[float, ...]

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
        boundary.source == "dimension_constrained"
        for boundary in geometry.frame_boundaries
    )
    if expected == 0:
        state = EvidenceState.NOT_APPLICABLE
        reason = "single_frame_has_no_internal_separator"
    elif not missing:
        state = EvidenceState.SUPPORTED
        reason = "complete_independent_separator_sequence"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "independent_separator_sequence_incomplete"
    return SeparatorSequenceEvidence(
        state=state,
        reason=reason,
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
