from __future__ import annotations

from dataclasses import dataclass, field

from ....domain import EvidenceState, FrameBoundary, FrameBoundaryReference
from ...physical.spacing import InterFrameSpacing, ObservedSpacingEvidence
from .frame_support import FrameContentEvidence


@dataclass(frozen=True)
class InternalBoundaryObservation:
    boundary: FrameBoundaryReference
    separator_supported: bool
    contact_supported: bool
    overlap_supported: bool
    continuous_content_crossing: bool
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        explained = bool(
            self.separator_supported
            or self.contact_supported
            or self.overlap_supported
        )
        if explained:
            state = EvidenceState.SUPPORTED
            reason = "internal_boundary_physically_explained"
        elif self.continuous_content_crossing:
            state = EvidenceState.CONTRADICTED
            reason = "continuous_content_crosses_unexplained_boundary"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "internal_boundary_preservation_unresolved"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class InternalBoundaryPreservationEvidence:
    observations: tuple[InternalBoundaryObservation, ...]
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.observations:
            state = EvidenceState.NOT_APPLICABLE
            reason = "single_frame_has_no_internal_boundary"
        elif any(
            observation.state == EvidenceState.CONTRADICTED
            for observation in self.observations
        ):
            state = EvidenceState.CONTRADICTED
            reason = "internal_boundary_cuts_continuous_content"
        elif all(
            observation.state == EvidenceState.SUPPORTED
            for observation in self.observations
        ):
            state = EvidenceState.SUPPORTED
            reason = "internal_boundaries_preserve_content"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "internal_boundary_preservation_unresolved"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def internal_boundary_preservation_evidence(
    count: int,
    frame_boundaries: tuple[FrameBoundary, ...],
    spacings: tuple[InterFrameSpacing, ...],
    frame_content: FrameContentEvidence,
) -> InternalBoundaryPreservationEvidence:
    if count <= 0:
        raise ValueError("internal boundary evidence requires a positive count")
    expected = tuple(range(1, count))
    if tuple(boundary.boundary_index for boundary in frame_boundaries) != expected:
        raise ValueError("internal boundary evidence requires complete boundaries")
    if tuple(spacing.boundary.boundary_index for spacing in spacings) != expected:
        raise ValueError("internal boundary evidence requires complete spacing")
    content = {
        observation.index: observation
        for observation in frame_content.observations
    }

    def content_contacts(frame_index: int, side: str) -> bool:
        observation = content.get(frame_index)
        return bool(
            observation is not None
            and side in observation.boundary_contact_sides
        )

    observations = tuple(
        InternalBoundaryObservation(
            boundary=FrameBoundaryReference(None, boundary_index),
            separator_supported=frame_boundary.hard_separator,
            contact_supported=bool(
                isinstance(spacing, ObservedSpacingEvidence)
                and spacing.kind == "contact"
                and spacing.independently_observed
            ),
            overlap_supported=bool(
                spacing.kind == "overlap" and spacing.supports_output_protection
            ),
            continuous_content_crossing=bool(
                content_contacts(boundary_index, "right")
                and content_contacts(boundary_index + 1, "left")
            ),
        )
        for boundary_index, (frame_boundary, spacing) in enumerate(
            zip(frame_boundaries, spacings, strict=True),
            start=1,
        )
    )
    return InternalBoundaryPreservationEvidence(observations)
