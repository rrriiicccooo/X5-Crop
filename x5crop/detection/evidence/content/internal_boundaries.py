from __future__ import annotations

from dataclasses import dataclass, field, replace

from ....domain import (
    BoundarySide,
    EvidenceState,
    InterPhotoBoundaryReference,
    InterPhotoSpacing,
    InterPhotoSpacingBasis,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoAperture,
    PhotoApertureEdgeSource,
)
from .photo_content import PhotoContentEvidence


@dataclass(frozen=True)
class InternalBoundaryObservation:
    boundary: InterPhotoBoundaryReference
    spacing_evidence: InterPhotoSpacing
    continuous_content_crossing: bool
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.spacing_evidence.boundary != self.boundary:
            raise ValueError("internal boundary spacing must preserve boundary identity")
        explained = bool(
            self.spacing_evidence.state == EvidenceState.SUPPORTED
            and self.spacing_evidence.kind in {"separator", "contact", "overlap"}
        )
        if explained:
            state = EvidenceState.SUPPORTED
            reason = "internal_boundary_physically_explained"
        elif self.continuous_content_crossing:
            state = EvidenceState.CONTRADICTED
            reason = "continuous_content_crosses_unexplained_boundary"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "inter_photo_boundary_preservation_unresolved"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _content_corroborated_spacing(
    spacing: InterPhotoSpacing,
    left: PhotoAperture,
    right: PhotoAperture,
    continuous_content_crossing: bool,
) -> InterPhotoSpacing:
    if spacing.supports_output_protection:
        return spacing
    measured_overlap_edges = bool(
        spacing.kind == "overlap"
        and spacing.basis == InterPhotoSpacingBasis.GEOMETRY_HYPOTHESIS
        and continuous_content_crossing
        and left.trailing.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
        and right.leading.source == PhotoApertureEdgeSource.MEASURED_BOUNDARY_PATH
        and left.trailing.provenance.observation_id
        != right.leading.provenance.observation_id
    )
    if not measured_overlap_edges:
        return spacing
    dependencies = tuple(
        dict.fromkeys(
            (
                spacing.provenance.root_measurement,
                left.trailing.provenance.root_measurement,
                right.leading.provenance.root_measurement,
            )
        )
    )
    return replace(
        spacing,
        basis=InterPhotoSpacingBasis.CORROBORATED_OVERLAP,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
            observation_id=ObservationId(
                f"content_overlap:{spacing.boundary.boundary_index}:"
                f"{left.trailing.provenance.observation_id}:"
                f"{right.leading.provenance.observation_id}"
            ),
            dependencies=dependencies,
            description="content-corroborated inter-photo overlap",
            boundary_anchors=(
                left.trailing.provenance.observation_id,
                right.leading.provenance.observation_id,
            ),
        ),
    )


@dataclass(frozen=True)
class InterPhotoBoundaryPreservationEvidence:
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
            reason = "inter_photo_boundary_preservation_unresolved"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def inter_photo_boundary_preservation_evidence(
    count: int,
    photo_apertures: tuple[PhotoAperture, ...],
    spacings: tuple[InterPhotoSpacing, ...],
    photo_content: PhotoContentEvidence,
) -> InterPhotoBoundaryPreservationEvidence:
    if count <= 0:
        raise ValueError("internal boundary evidence requires a positive count")
    expected = tuple(range(1, count))
    if tuple(item.index for item in photo_apertures) != tuple(range(1, count + 1)):
        raise ValueError("internal boundary evidence requires complete apertures")
    if tuple(spacing.boundary.boundary_index for spacing in spacings) != expected:
        raise ValueError("internal boundary evidence requires complete spacing")
    content = {
        observation.photo_index: observation
        for observation in photo_content.observations
    }

    def content_contacts(frame_index: int, side: BoundarySide) -> bool:
        observation = content.get(frame_index)
        return bool(
            observation is not None
            and side in observation.boundary_contact_sides
        )

    observations: list[InternalBoundaryObservation] = []
    for boundary_index, spacing in enumerate(spacings, start=1):
        left = photo_apertures[boundary_index - 1]
        right = photo_apertures[boundary_index]
        crossing = bool(
            content_contacts(boundary_index, BoundarySide.TRAILING)
            and content_contacts(boundary_index + 1, BoundarySide.LEADING)
        )
        observations.append(
            InternalBoundaryObservation(
                boundary=InterPhotoBoundaryReference(None, boundary_index),
                spacing_evidence=_content_corroborated_spacing(
                    spacing,
                    left,
                    right,
                    crossing,
                ),
                continuous_content_crossing=crossing,
            )
        )
    return InterPhotoBoundaryPreservationEvidence(tuple(observations))
