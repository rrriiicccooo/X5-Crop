from __future__ import annotations

from dataclasses import dataclass, field, replace

from ....domain import (
    BoundarySide,
    EvidenceState,
    InterPhotoBoundaryReference,
    InterPhotoSpacing,
    InterPhotoSpacingBasis,
    InterPhotoSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PhotoAperture,
    PhotoApertureEdgeSource,
)
from ..photo_aperture_coverage import PhotoApertureCoverageEvidence
from .photo_content import (
    PhotoBoundaryContentTrace,
    PhotoContentEvidence,
    PhotoContentObservation,
)


@dataclass(frozen=True)
class InternalBoundaryObservation:
    boundary: InterPhotoBoundaryReference
    spacing_evidence: InterPhotoSpacing
    shared_content_track_count: int
    minimum_shared_content_tracks: int
    long_axis_content_spans_boundary: bool
    continuous_content_crossing: bool = field(init=False)
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.spacing_evidence.boundary != self.boundary:
            raise ValueError("internal boundary spacing must preserve boundary identity")
        if self.shared_content_track_count < 0:
            raise ValueError("shared content track count must be non-negative")
        if self.minimum_shared_content_tracks <= 0:
            raise ValueError("shared content track requirement must be positive")
        crossing = bool(
            self.long_axis_content_spans_boundary
            and self.shared_content_track_count >= self.minimum_shared_content_tracks
        )
        explained = bool(
            self.spacing_evidence.state == EvidenceState.SUPPORTED
            and self.spacing_evidence.kind
            in {
                InterPhotoSpacingKind.SEPARATOR,
                InterPhotoSpacingKind.CONTACT,
                InterPhotoSpacingKind.OVERLAP,
            }
        )
        if explained:
            state = EvidenceState.SUPPORTED
            reason = "internal_boundary_physically_explained"
        elif crossing:
            state = EvidenceState.CONTRADICTED
            reason = "continuous_content_crosses_unexplained_boundary"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "inter_photo_boundary_preservation_unresolved"
        object.__setattr__(self, "continuous_content_crossing", crossing)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _boundary_trace(
    observation: PhotoContentObservation | None,
    side: BoundarySide,
) -> PhotoBoundaryContentTrace | None:
    if observation is None:
        return None
    return next(
        (trace for trace in observation.boundary_traces if trace.side == side),
        None,
    )


def _shared_track_count(
    left: PhotoBoundaryContentTrace | None,
    right: PhotoBoundaryContentTrace | None,
) -> tuple[int, int]:
    if left is None or right is None:
        return 0, 1
    shared = 0
    left_index = 0
    right_index = 0
    while (
        left_index < len(left.boundary_parallel_runs)
        and right_index < len(right.boundary_parallel_runs)
    ):
        left_start, left_end = left.boundary_parallel_runs[left_index]
        right_start, right_end = right.boundary_parallel_runs[right_index]
        shared += max(0, min(left_end, right_end) - max(left_start, right_start))
        if left_end <= right_end:
            left_index += 1
        else:
            right_index += 1
    return shared, max(
        left.minimum_crossing_tracks,
        right.minimum_crossing_tracks,
    )


def _content_spans_boundary(
    coverage: PhotoApertureCoverageEvidence,
    left: PhotoAperture,
    right: PhotoAperture,
) -> bool:
    lower = min(left.trailing.position.minimum, right.leading.position.minimum)
    upper = max(left.trailing.position.maximum, right.leading.position.maximum)
    if upper <= lower:
        return any(
            start <= lower < end
            for start, end in coverage.content_runs
        )
    return any(
        start <= lower and end >= upper
        for start, end in coverage.content_runs
    )


def _content_corroborated_spacing(
    spacing: InterPhotoSpacing,
    left: PhotoAperture,
    right: PhotoAperture,
    continuous_content_crossing: bool,
) -> InterPhotoSpacing:
    if spacing.supports_output_protection:
        return spacing
    measured_overlap_edges = bool(
        spacing.kind == InterPhotoSpacingKind.OVERLAP
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
    photo_aperture_coverage: PhotoApertureCoverageEvidence,
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

    observations: list[InternalBoundaryObservation] = []
    for boundary_index, spacing in enumerate(spacings, start=1):
        left = photo_apertures[boundary_index - 1]
        right = photo_apertures[boundary_index]
        shared_tracks, minimum_shared_tracks = _shared_track_count(
            _boundary_trace(
                content.get(boundary_index),
                BoundarySide.TRAILING,
            ),
            _boundary_trace(
                content.get(boundary_index + 1),
                BoundarySide.LEADING,
            ),
        )
        long_axis_span = _content_spans_boundary(
            photo_aperture_coverage,
            left,
            right,
        )
        crossing = bool(
            long_axis_span and shared_tracks >= minimum_shared_tracks
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
                shared_content_track_count=shared_tracks,
                minimum_shared_content_tracks=minimum_shared_tracks,
                long_axis_content_spans_boundary=long_axis_span,
            )
        )
    return InterPhotoBoundaryPreservationEvidence(tuple(observations))
