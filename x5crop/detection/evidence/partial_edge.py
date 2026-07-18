from __future__ import annotations

from dataclasses import dataclass, field

from ..physical.model import FrameSequenceSolution
from ..physical.frame_dimensions import FrameDimensionEvidence
from .content.frame_content import FrameContentEvidence
from .frame_coverage import FrameCoverageEvidence
from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class PartialEdgeSafetyEvidence:
    is_partial: bool
    hard_separator_count: int
    expected_separator_count: int
    frame_coverage_state: EvidenceState
    frame_dimension_state: EvidenceState
    edge_geometry_resolved: bool
    diagnostics: tuple[str, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)
    boundary_support: bool = field(init=False)

    def __post_init__(self) -> None:
        if min(self.hard_separator_count, self.expected_separator_count) < 0:
            raise ValueError("partial edge separator counts must be non-negative")
        if self.hard_separator_count > self.expected_separator_count:
            raise ValueError("hard separator count cannot exceed boundary count")
        if any(not item for item in self.diagnostics) or len(
            set(self.diagnostics)
        ) != len(self.diagnostics):
            raise ValueError("partial edge diagnostics must be non-empty and unique")

        boundary_support = bool(
            self.is_partial
            and self.expected_separator_count > 0
            and self.frame_dimension_state == EvidenceState.SUPPORTED
            and self.frame_coverage_state == EvidenceState.SUPPORTED
            and self.edge_geometry_resolved
        )
        if not self.is_partial:
            state = EvidenceState.NOT_APPLICABLE
            reason = "not_partial"
        elif self.frame_coverage_state == EvidenceState.CONTRADICTED:
            state = EvidenceState.CONTRADICTED
            reason = "content_outside_frame_union"
        elif boundary_support:
            state = EvidenceState.SUPPORTED
            reason = "partial_boundaries_physically_supported"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "partial_boundaries_unresolved"
        object.__setattr__(self, "boundary_support", boundary_support)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def partial_edge_safety_evidence(
    geometry: FrameSequenceSolution,
    frame_coverage: FrameCoverageEvidence,
    frame_dimensions: FrameDimensionEvidence,
    frame_content: FrameContentEvidence,
) -> PartialEdgeSafetyEvidence:
    hard_count = len(geometry.separator_assignments)
    expected = max(0, geometry.count - 1)
    diagnostics: list[str] = []
    if frame_content.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("frame_content_unavailable")
    return PartialEdgeSafetyEvidence(
        is_partial=geometry.strip_mode == "partial",
        hard_separator_count=hard_count,
        expected_separator_count=expected,
        frame_coverage_state=frame_coverage.state,
        frame_dimension_state=frame_dimensions.state,
        edge_geometry_resolved=bool(
            geometry.frame_slots[0].leading.geometry_resolved
            and geometry.frame_slots[-1].trailing.geometry_resolved
        ),
        diagnostics=tuple(diagnostics),
    )
