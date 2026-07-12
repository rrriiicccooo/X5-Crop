from __future__ import annotations

from dataclasses import dataclass

from ..partial_edge import PartialEdgeSafetyEvidence
from ..frame_coverage import FrameCoverageEvidence
from ..sequence_content_alignment import SequenceContentAlignmentEvidence
from x5crop.domain import EvidenceState
from .frame_support import FrameContentEvidence


@dataclass(frozen=True)
class ContentPreservationEvidence:
    state: EvidenceState
    reason: str
    uncovered_content: tuple[tuple[int, int], ...]
    boundary_contact_frame_indexes: tuple[int, ...]
    partial_edge_state: EvidenceState

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("content preservation evidence requires a reason")
        if any(end <= start for start, end in self.uncovered_content):
            raise ValueError("uncovered content intervals must have positive extent")
        if (
            any(index < 0 for index in self.boundary_contact_frame_indexes)
            or len(set(self.boundary_contact_frame_indexes))
            != len(self.boundary_contact_frame_indexes)
        ):
            raise ValueError("content boundary contacts must be valid and unique")
        contradicted = bool(
            self.uncovered_content
            or self.partial_edge_state == EvidenceState.CONTRADICTED
        )
        if contradicted != (self.state == EvidenceState.CONTRADICTED):
            raise ValueError(
                "content preservation contradiction must match physical evidence"
            )

def content_preservation_evidence(
    frame_content: FrameContentEvidence,
    sequence_content_alignment: SequenceContentAlignmentEvidence,
    partial_edge: PartialEdgeSafetyEvidence,
    frame_coverage: FrameCoverageEvidence,
) -> ContentPreservationEvidence:
    uncovered = tuple(frame_coverage.uncovered_content)
    contacts = frame_content.boundary_contact_frame_indexes
    if uncovered:
        state = EvidenceState.CONTRADICTED
        reason = "content_outside_frame_union"
    elif sequence_content_alignment.content_outside_sides:
        state = EvidenceState.UNAVAILABLE
        reason = "content_measurement_conflicts_with_sequence"
    elif partial_edge.state == EvidenceState.CONTRADICTED:
        state = EvidenceState.CONTRADICTED
        reason = partial_edge.reason
    elif (
        frame_coverage.state == EvidenceState.SUPPORTED
        or sequence_content_alignment.state == EvidenceState.SUPPORTED
    ):
        state = EvidenceState.SUPPORTED
        reason = "content_preserved"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "content_preservation_unresolved"
    return ContentPreservationEvidence(
        state=state,
        reason=reason,
        uncovered_content=uncovered,
        boundary_contact_frame_indexes=contacts,
        partial_edge_state=partial_edge.state,
    )
