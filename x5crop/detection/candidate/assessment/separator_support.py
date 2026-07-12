from __future__ import annotations

from dataclasses import dataclass

from ...evidence.separator_continuity import (
    SeparatorContinuityEvidence,
    continuity_state_for_observation,
)
from x5crop.domain import EvidenceState
from ...physical.model import SequenceSolution


@dataclass(frozen=True)
class SeparatorSequenceEvidence:
    state: EvidenceState
    reason: str
    expected_count: int
    hard_count: int
    dimension_constrained_count: int
    hard_boundary_indexes: tuple[int, ...]
    missing_boundary_indexes: tuple[int, ...]
    hard_tonal_evidence: tuple[float, ...]


def separator_sequence_evidence(
    geometry: SequenceSolution,
    continuity: SeparatorContinuityEvidence,
) -> SeparatorSequenceEvidence:
    expected = max(0, geometry.count - 1)
    accepted = tuple(
        boundary
        for boundary in geometry.frame_boundaries
        if boundary.hard_separator
        and boundary.assignment is not None
        and continuity_state_for_observation(
            continuity,
            boundary.assignment.observation,
        )
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
        hard_boundary_indexes=indexes,
        missing_boundary_indexes=missing,
        hard_tonal_evidence=tuple(
            float(boundary.assignment.observation.tonal_evidence)
            for boundary in accepted
            if boundary.assignment is not None
        ),
    )
