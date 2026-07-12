from __future__ import annotations

from dataclasses import dataclass

from ..physical.model import SequenceSolution
from ..physical.photo_size import FrameDimensionEvidence
from .content.frame_support import FrameContentEvidence
from .frame_coverage import FrameCoverageEvidence
from .holder_occupancy import HolderOccupancyEvidence
from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class PartialEdgeSafetyEvidence:
    state: EvidenceState
    reason: str
    boundary_support: bool
    hard_separator_count: int
    expected_separator_count: int
    content_coverage_state: EvidenceState
    holder_occupancy_state: EvidenceState
    complete_underfilled_strip: bool
    diagnostics: tuple[str, ...]

def partial_edge_safety_evidence(
    geometry: SequenceSolution,
    frame_coverage: FrameCoverageEvidence,
    frame_dimensions: FrameDimensionEvidence,
    frame_content: FrameContentEvidence,
    occupancy: HolderOccupancyEvidence,
) -> PartialEdgeSafetyEvidence:
    if geometry.strip_mode != "partial":
        return PartialEdgeSafetyEvidence(
            EvidenceState.NOT_APPLICABLE,
            "not_partial",
            False,
            0,
            max(0, geometry.count - 1),
            frame_coverage.state,
            occupancy.state,
            False,
            (),
        )
    hard_count = sum(
        1
        for assignment in geometry.separator_assignments
        if assignment.used_for_boundary and assignment.independent
    )
    expected = max(0, geometry.count - 1)
    boundary_support = bool(
        geometry.count > 1
        and hard_count >= expected
        and frame_dimensions.state == EvidenceState.SUPPORTED
        and frame_coverage.state == EvidenceState.SUPPORTED
    )
    diagnostics: list[str] = []
    if frame_content.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("frame_content_unavailable")
    if occupancy.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("holder_occupancy_unresolved")
    if frame_coverage.state == EvidenceState.CONTRADICTED:
        state = EvidenceState.CONTRADICTED
        reason = frame_coverage.reason
    elif boundary_support:
        state = EvidenceState.SUPPORTED
        reason = "partial_boundaries_physically_supported"
    else:
        state = EvidenceState.UNAVAILABLE
        reason = "partial_boundaries_unresolved"
    return PartialEdgeSafetyEvidence(
        state=state,
        reason=reason,
        boundary_support=boundary_support,
        hard_separator_count=hard_count,
        expected_separator_count=expected,
        content_coverage_state=frame_coverage.state,
        holder_occupancy_state=occupancy.state,
        complete_underfilled_strip=occupancy.complete_underfilled_strip,
        diagnostics=tuple(diagnostics),
    )
