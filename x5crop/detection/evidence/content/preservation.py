from __future__ import annotations

from dataclasses import dataclass

from ..partial_edge import PartialEdgeSafetyEvidence
from ..frame_coverage import FrameCoverageEvidence
from ..outer_alignment import OuterAlignmentEvidence
from ..state import EvidenceState
from .frame_support import FrameContentEvidence


@dataclass(frozen=True)
class ContentPreservationEvidence:
    state: EvidenceState
    reason: str
    uncovered_content: tuple[tuple[int, int], ...]
    boundary_contact_frame_indexes: tuple[int, ...]
    confirmed_outer_undercrop_sides: tuple[str, ...]
    partial_edge_state: EvidenceState

def content_preservation_evidence(
    frame_content: FrameContentEvidence,
    outer_alignment: OuterAlignmentEvidence,
    partial_edge: PartialEdgeSafetyEvidence,
    frame_coverage: FrameCoverageEvidence,
) -> ContentPreservationEvidence:
    uncovered = tuple(frame_coverage.uncovered_content)
    contacts = frame_content.boundary_contact_frame_indexes
    confirmed_sides = tuple(outer_alignment.confirmed_undercrop_sides)
    if uncovered:
        state = EvidenceState.CONTRADICTED
        reason = "content_outside_frame_union"
    elif frame_coverage.unexplained_content_region_count:
        state = EvidenceState.CONTRADICTED
        reason = "content_region_count_exceeds_frame_count"
    elif contacts:
        state = EvidenceState.CONTRADICTED
        reason = "content_contacts_frame_boundary"
    elif confirmed_sides:
        state = EvidenceState.CONTRADICTED
        reason = "content_outside_film_span_confirmed"
    elif partial_edge.state == EvidenceState.CONTRADICTED:
        state = EvidenceState.CONTRADICTED
        reason = partial_edge.reason
    elif (
        frame_coverage.state == EvidenceState.SUPPORTED
        or outer_alignment.state == EvidenceState.SUPPORTED
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
        confirmed_outer_undercrop_sides=confirmed_sides,
        partial_edge_state=partial_edge.state,
    )
