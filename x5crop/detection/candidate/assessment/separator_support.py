from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ....gap_methods import is_hard_gap_method
from ...evidence.separator_continuity import (
    SeparatorContinuityEvidence,
    supported_hard_separator_observations,
)
from ...evidence.state import EvidenceState

if TYPE_CHECKING:
    from ...geometry import CandidateGeometry


@dataclass(frozen=True)
class SeparatorSequenceEvidence:
    state: EvidenceState
    reason: str
    expected_count: int
    hard_count: int
    model_count: int
    hard_indexes: tuple[int, ...]
    missing_indexes: tuple[int, ...]
    hard_scores: tuple[float, ...]


def separator_sequence_evidence(
    geometry: CandidateGeometry,
    continuity: SeparatorContinuityEvidence,
) -> SeparatorSequenceEvidence:
    expected = max(0, int(geometry.count) - 1)
    hard = supported_hard_separator_observations(continuity)
    hard_indexes = tuple(sorted({int(observation.index) for observation in hard}))
    missing = tuple(
        index for index in range(1, expected + 1) if index not in hard_indexes
    )
    model_count = sum(
        1
        for observation in geometry.separators
        if not is_hard_gap_method(observation.method)
    )
    if expected == 0:
        state = EvidenceState.NOT_APPLICABLE
        reason = "single_frame_has_no_internal_separator"
    elif not missing:
        state = EvidenceState.SUPPORTED
        reason = "complete_hard_separator_sequence"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "hard_separator_sequence_incomplete"
    return SeparatorSequenceEvidence(
        state=state,
        reason=reason,
        expected_count=expected,
        hard_count=len(hard),
        model_count=model_count,
        hard_indexes=hard_indexes,
        missing_indexes=missing,
        hard_scores=tuple(float(observation.score) for observation in hard),
    )
