from __future__ import annotations

from dataclasses import dataclass, field

from ..physical.model import PhotoSequenceSolution
from ..physical.photo_size import FrameDimensionEvidence
from .content.photo_content import PhotoContentEvidence
from .photo_sequence_coverage import PhotoSequenceCoverageEvidence
from x5crop.domain import EvidenceState


@dataclass(frozen=True)
class PartialEdgeSafetyEvidence:
    is_partial: bool
    hard_separator_count: int
    expected_separator_count: int
    photo_sequence_coverage_state: EvidenceState
    frame_dimension_state: EvidenceState
    edge_apertures_supported: bool
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
            and self.hard_separator_count == self.expected_separator_count
            and self.frame_dimension_state == EvidenceState.SUPPORTED
            and self.photo_sequence_coverage_state == EvidenceState.SUPPORTED
            and self.edge_apertures_supported
        )
        if not self.is_partial:
            state = EvidenceState.NOT_APPLICABLE
            reason = "not_partial"
        elif self.photo_sequence_coverage_state == EvidenceState.CONTRADICTED:
            state = EvidenceState.CONTRADICTED
            reason = "content_outside_aperture_union"
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
    geometry: PhotoSequenceSolution,
    photo_sequence_coverage: PhotoSequenceCoverageEvidence,
    frame_dimensions: FrameDimensionEvidence,
    photo_content: PhotoContentEvidence,
) -> PartialEdgeSafetyEvidence:
    hard_count = sum(
        1
        for assignment in geometry.separator_assignments
        if assignment.independent
    )
    expected = max(0, geometry.count - 1)
    diagnostics: list[str] = []
    if photo_content.state == EvidenceState.UNAVAILABLE:
        diagnostics.append("photo_content_unavailable")
    return PartialEdgeSafetyEvidence(
        is_partial=geometry.strip_mode == "partial",
        hard_separator_count=hard_count,
        expected_separator_count=expected,
        photo_sequence_coverage_state=photo_sequence_coverage.state,
        frame_dimension_state=frame_dimensions.state,
        edge_apertures_supported=bool(
            geometry.photo_apertures[0].leading.independently_observed
            and geometry.photo_apertures[-1].trailing.independently_observed
        ),
        diagnostics=tuple(diagnostics),
    )
