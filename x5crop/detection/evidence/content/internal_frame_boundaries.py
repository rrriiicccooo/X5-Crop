from __future__ import annotations

from dataclasses import dataclass, field, replace
import math

import numpy as np

from ....configuration.content import ContentEvidenceParameters
from ....domain import (
    BoundarySide,
    EvidenceState,
    InterFrameBoundaryReference,
    InterFrameSpacing,
    InterFrameSpacingBasis,
    InterFrameSpacingKind,
    MeasurementIdentity,
    MeasurementProvenance,
    ObservationId,
    PixelInterval,
)
from ...physical.model import (
    FrameSlot,
    boundary_role_is_independent_physical_measurement,
)
from ....image.evidence import activation_mask
from ....image.statistics import ImageMeasurementStatistics
from ..frame_coverage import FrameCoverageEvidence
from .frame_content import (
    FrameBoundaryContentTrace,
    FrameContentEvidence,
    FrameContentObservation,
)


@dataclass(frozen=True)
class InternalBoundaryContentContinuityObservation:
    boundary: InterFrameBoundaryReference
    shared_content_track_count: int
    minimum_shared_content_tracks: int
    long_axis_content_spans_boundary: bool
    content_bridge_track_count: int
    minimum_content_bridge_tracks: int
    gray_discontinuity_track_count: int
    minimum_gray_discontinuity_tracks: int
    provenance: MeasurementProvenance
    continuous_content_crossing: bool = field(init=False)
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.shared_content_track_count < 0:
            raise ValueError("shared content track count must be non-negative")
        if self.minimum_shared_content_tracks <= 0:
            raise ValueError("shared content track requirement must be positive")
        if self.content_bridge_track_count < 0:
            raise ValueError("content bridge count must be non-negative")
        if self.minimum_content_bridge_tracks <= 0:
            raise ValueError("content bridge requirement must be positive")
        if self.gray_discontinuity_track_count < 0:
            raise ValueError("gray discontinuity count must be non-negative")
        if self.minimum_gray_discontinuity_tracks <= 0:
            raise ValueError("gray discontinuity requirement must be positive")
        activity_spans_boundary = bool(
            self.long_axis_content_spans_boundary
            and self.shared_content_track_count >= self.minimum_shared_content_tracks
        )
        coherent_content_bridge = bool(
            self.content_bridge_track_count
            >= self.minimum_content_bridge_tracks
        )
        coherent_gray_discontinuity = bool(
            self.gray_discontinuity_track_count
            >= self.minimum_gray_discontinuity_tracks
        )
        if not activity_spans_boundary:
            crossing = False
            state = EvidenceState.UNAVAILABLE
            reason = "internal_boundary_content_continuity_unavailable"
        elif coherent_gray_discontinuity:
            crossing = False
            state = EvidenceState.UNAVAILABLE
            reason = "gray_discontinuity_breaks_content_continuity"
        elif not coherent_content_bridge:
            crossing = False
            state = EvidenceState.UNAVAILABLE
            reason = "content_bridge_not_observed"
        else:
            crossing = True
            state = EvidenceState.SUPPORTED
            reason = "continuous_content_crossing_supported"
        object.__setattr__(self, "continuous_content_crossing", crossing)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


@dataclass(frozen=True)
class InternalBoundaryObservation:
    boundary: InterFrameBoundaryReference
    spacing_evidence: InterFrameSpacing
    content_continuity: InternalBoundaryContentContinuityObservation
    state: EvidenceState = field(init=False)
    reason: str = field(init=False)

    def __post_init__(self) -> None:
        if self.spacing_evidence.boundary != self.boundary:
            raise ValueError("internal boundary spacing must preserve boundary identity")
        if self.content_continuity.boundary != self.boundary:
            raise ValueError("content continuity must preserve boundary identity")
        explained = bool(
            self.spacing_evidence.state == EvidenceState.SUPPORTED
            and self.spacing_evidence.kind
            in {
                InterFrameSpacingKind.SEPARATOR,
                InterFrameSpacingKind.CONTACT,
                InterFrameSpacingKind.OVERLAP,
            }
        )
        if explained:
            state = EvidenceState.SUPPORTED
            reason = "internal_boundary_physically_explained"
        elif self.content_continuity.continuous_content_crossing:
            state = EvidenceState.CONTRADICTED
            reason = "internal_boundary_cuts_continuous_content"
        else:
            state = EvidenceState.UNAVAILABLE
            reason = "internal_frame_boundary_preservation_unresolved"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def _boundary_trace(
    observation: FrameContentObservation | None,
    side: BoundarySide,
) -> FrameBoundaryContentTrace | None:
    if observation is None:
        return None
    return next(
        (trace for trace in observation.boundary_traces if trace.side == side),
        None,
    )


def _shared_track_runs(
    left: FrameBoundaryContentTrace | None,
    right: FrameBoundaryContentTrace | None,
) -> tuple[tuple[tuple[int, int], ...], int]:
    if left is None or right is None:
        return (), 1
    shared: list[tuple[int, int]] = []
    left_index = 0
    right_index = 0
    while (
        left_index < len(left.boundary_parallel_runs)
        and right_index < len(right.boundary_parallel_runs)
    ):
        left_start, left_end = left.boundary_parallel_runs[left_index]
        right_start, right_end = right.boundary_parallel_runs[right_index]
        start = max(left_start, right_start)
        end = min(left_end, right_end)
        if end > start:
            shared.append((start, end))
        if left_end <= right_end:
            left_index += 1
        else:
            right_index += 1
    return tuple(shared), max(
        left.minimum_crossing_tracks,
        right.minimum_crossing_tracks,
    )


def _content_spans_boundary(
    coverage: FrameCoverageEvidence,
    left: FrameSlot,
    right: FrameSlot,
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


def _content_bridge_track_count(
    content_evidence_work: np.ndarray,
    content_threshold: float | None,
    shared_track_runs: tuple[tuple[int, int], ...],
    left: FrameSlot,
    right: FrameSlot,
    parameters: ContentEvidenceParameters,
) -> int:
    if content_evidence_work.ndim != 2:
        raise ValueError("internal-boundary continuity requires two-dimensional gray")
    if (
        content_threshold is None
        or not math.isfinite(float(content_threshold))
        or not shared_track_runs
        or content_evidence_work.shape[1] < 3
    ):
        return 0
    track_mask = np.zeros(content_evidence_work.shape[0], dtype=bool)
    for start, end in shared_track_runs:
        lower = max(0, int(start))
        upper = min(content_evidence_work.shape[0], int(end))
        if upper > lower:
            track_mask[lower:upper] = True
    if not bool(track_mask.any()):
        return 0
    boundary_lower = min(
        left.trailing.position.minimum,
        right.leading.position.minimum,
    )
    boundary_upper = max(
        left.trailing.position.maximum,
        right.leading.position.maximum,
    )
    center_start = max(0, int(math.floor(boundary_lower)))
    center_end = min(
        content_evidence_work.shape[1],
        int(math.ceil(boundary_upper)),
    )
    if center_end <= center_start:
        center = max(
            0,
            min(
                content_evidence_work.shape[1] - 1,
                int(
                    round(
                        PixelInterval(
                            boundary_lower,
                            boundary_upper,
                        ).midpoint
                    )
                ),
            ),
        )
        center_start = center
        center_end = min(content_evidence_work.shape[1], center + 1)
    if center_end <= center_start:
        return 0
    active = activation_mask(content_evidence_work, float(content_threshold))
    corridor = active[track_mask, center_start:center_end]
    if not corridor.size:
        return 0
    track_support = np.percentile(
        corridor.astype(np.float32, copy=False),
        float(parameters.content_bridge_column_percentile),
        axis=1,
    )
    return int(np.count_nonzero(track_support > 0.0))


def _gray_discontinuity_track_count(
    gray_work: np.ndarray,
    shared_track_runs: tuple[tuple[int, int], ...],
    left: FrameSlot,
    right: FrameSlot,
    gradient_threshold: float,
    parameters: ContentEvidenceParameters,
) -> int:
    if gray_work.ndim != 2:
        raise ValueError("internal-boundary continuity requires two-dimensional gray")
    if not shared_track_runs or gray_work.shape[1] < 2:
        return 0
    track_mask = np.zeros(gray_work.shape[0], dtype=bool)
    for start, end in shared_track_runs:
        lower = max(0, int(start))
        upper = min(gray_work.shape[0], int(end))
        if upper > lower:
            track_mask[lower:upper] = True
    if not bool(track_mask.any()):
        return 0
    boundary_lower = min(
        left.trailing.position.minimum,
        right.leading.position.minimum,
    )
    boundary_upper = max(
        left.trailing.position.maximum,
        right.leading.position.maximum,
    )
    band = max(
        int(parameters.boundary_band_min_px),
        int(round(min(gray_work.shape) * float(parameters.boundary_band_ratio))),
    )
    start = max(0, int(math.floor(boundary_lower)) - band)
    end = min(gray_work.shape[1] - 1, int(math.ceil(boundary_upper)) + band)
    if end <= start:
        return 0
    data = gray_work.astype(np.float32, copy=False)
    horizontal_gradient = np.abs(data[:, 1:] - data[:, :-1])
    corridor = horizontal_gradient[track_mask, start:end]
    if not corridor.size:
        return 0
    column_support = np.count_nonzero(
        corridor > float(gradient_threshold),
        axis=0,
    )
    return int(column_support.max(initial=0))


def measure_internal_boundary_content_continuity(
    frame_slots: tuple[FrameSlot, ...],
    frame_content: FrameContentEvidence,
    frame_coverage: FrameCoverageEvidence,
    content_evidence_work: np.ndarray,
    gray_work: np.ndarray,
    image_statistics: ImageMeasurementStatistics,
    parameters: ContentEvidenceParameters,
) -> tuple[InternalBoundaryContentContinuityObservation, ...]:
    if tuple(item.index for item in frame_slots) != tuple(
        range(1, len(frame_slots) + 1)
    ):
        raise ValueError("content continuity requires complete ordered frame slots")
    content = {
        observation.frame_index: observation
        for observation in frame_content.observations
    }
    observations: list[InternalBoundaryContentContinuityObservation] = []
    for boundary_index, (left, right) in enumerate(
        zip(frame_slots, frame_slots[1:]),
        start=1,
    ):
        shared_runs, minimum_shared_tracks = _shared_track_runs(
            _boundary_trace(content.get(left.index), BoundarySide.TRAILING),
            _boundary_trace(content.get(right.index), BoundarySide.LEADING),
        )
        shared_track_count = sum(end - start for start, end in shared_runs)
        minimum_content_bridge_tracks = max(
            minimum_shared_tracks,
            int(
                math.ceil(
                    shared_track_count
                    * float(parameters.minimum_content_bridge_ratio)
                )
            ),
        )
        minimum_gray_discontinuity_tracks = max(
            minimum_shared_tracks,
            int(
                math.ceil(
                    shared_track_count
                    * float(parameters.minimum_gray_discontinuity_ratio)
                )
            ),
        )
        boundary = InterFrameBoundaryReference(None, boundary_index)
        anchor_ids = tuple(
            dict.fromkeys(
                item.measurement_provenance.observation_id
                for item in (left.trailing, right.leading)
                if item.independently_observed
            )
        )
        observations.append(
            InternalBoundaryContentContinuityObservation(
                boundary=boundary,
                shared_content_track_count=shared_track_count,
                minimum_shared_content_tracks=minimum_shared_tracks,
                long_axis_content_spans_boundary=_content_spans_boundary(
                    frame_coverage,
                    left,
                    right,
                ),
                content_bridge_track_count=(
                    _content_bridge_track_count(
                        content_evidence_work,
                        frame_content.threshold,
                        shared_runs,
                        left,
                        right,
                        parameters,
                    )
                ),
                minimum_content_bridge_tracks=minimum_content_bridge_tracks,
                gray_discontinuity_track_count=(
                    _gray_discontinuity_track_count(
                        gray_work,
                        shared_runs,
                        left,
                        right,
                        image_statistics.gradient_signal,
                        parameters,
                    )
                ),
                minimum_gray_discontinuity_tracks=(
                    minimum_gray_discontinuity_tracks
                ),
                provenance=MeasurementProvenance(
                    root_measurement=MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
                    observation_id=ObservationId(
                        f"internal_boundary_content_continuity:{boundary_index}:"
                        f"{left.trailing.position.minimum:.6f}:"
                        f"{right.leading.position.maximum:.6f}"
                    ),
                    dependencies=(
                        MeasurementIdentity.GRAY_WORK,
                        MeasurementIdentity.IMAGE_MEASUREMENT_STATISTICS,
                        MeasurementIdentity.FRAME_GEOMETRY,
                    ),
                    description="candidate-local internal-boundary content continuity",
                    boundary_anchors=anchor_ids,
                ),
            )
        )
    return tuple(observations)


def _content_corroborated_spacing(
    spacing: InterFrameSpacing,
    left: FrameSlot,
    right: FrameSlot,
    continuous_content_crossing: bool,
) -> InterFrameSpacing:
    if spacing.supports_output_protection:
        return spacing
    measured_overlap_edges = bool(
        spacing.kind == InterFrameSpacingKind.OVERLAP
        and spacing.basis == InterFrameSpacingBasis.GEOMETRY_HYPOTHESIS
        and continuous_content_crossing
        and boundary_role_is_independent_physical_measurement(left.trailing)
        and boundary_role_is_independent_physical_measurement(right.leading)
        and left.trailing.measurement_provenance.observation_id
        != right.leading.measurement_provenance.observation_id
    )
    if not measured_overlap_edges:
        return spacing
    dependencies = tuple(
        sorted(
            {
                dependency
                for provenance in (
                    spacing.provenance,
                    left.trailing.role_provenance,
                    right.leading.role_provenance,
                )
                for dependency in (
                    provenance.root_measurement,
                    *provenance.dependencies,
                )
                if dependency != MeasurementIdentity.CONTENT_EVIDENCE_IMAGE
            },
            key=lambda item: item.value,
        )
    )
    return replace(
        spacing,
        basis=InterFrameSpacingBasis.CORROBORATED_OVERLAP,
        provenance=MeasurementProvenance(
            root_measurement=MeasurementIdentity.CONTENT_EVIDENCE_IMAGE,
            observation_id=ObservationId(
                f"content_overlap:{spacing.boundary.boundary_index}:"
                f"{left.trailing.measurement_provenance.observation_id}:"
                f"{right.leading.measurement_provenance.observation_id}"
            ),
            dependencies=dependencies,
            description="content-corroborated inter-frame overlap",
            boundary_anchors=(
                left.trailing.measurement_provenance.observation_id,
                right.leading.measurement_provenance.observation_id,
            ),
        ),
    )


@dataclass(frozen=True)
class InternalFrameBoundaryPreservationEvidence:
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
            reason = "internal_frame_boundary_preservation_unresolved"
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "reason", reason)


def internal_frame_boundary_preservation_evidence(
    frame_slots: tuple[FrameSlot, ...],
    spacings: tuple[InterFrameSpacing, ...],
    content_continuity: tuple[
        InternalBoundaryContentContinuityObservation,
        ...,
    ],
) -> InternalFrameBoundaryPreservationEvidence:
    count = len(frame_slots)
    if count <= 0:
        raise ValueError("internal boundary evidence requires frame slots")
    expected = tuple(range(1, count))
    if tuple(item.index for item in frame_slots) != tuple(range(1, count + 1)):
        raise ValueError("internal boundary evidence requires complete frame slots")
    if tuple(spacing.boundary.boundary_index for spacing in spacings) != expected:
        raise ValueError("internal boundary evidence requires complete spacing")
    if tuple(item.boundary.boundary_index for item in content_continuity) != expected:
        raise ValueError("internal boundary evidence requires complete continuity")

    observations: list[InternalBoundaryObservation] = []
    for boundary_index, (spacing, continuity) in enumerate(
        zip(spacings, content_continuity, strict=True),
        start=1,
    ):
        left = frame_slots[boundary_index - 1]
        right = frame_slots[boundary_index]
        observations.append(
            InternalBoundaryObservation(
                boundary=InterFrameBoundaryReference(None, boundary_index),
                spacing_evidence=_content_corroborated_spacing(
                    spacing,
                    left,
                    right,
                    continuity.continuous_content_crossing,
                ),
                content_continuity=continuity,
            )
        )
    return InternalFrameBoundaryPreservationEvidence(tuple(observations))


def internal_frame_boundary_evidence_matches_geometry(
    geometry_slots: tuple[FrameSlot, ...],
    geometry_spacings: tuple[InterFrameSpacing, ...],
    evidence: InternalFrameBoundaryPreservationEvidence,
) -> bool:
    expected = tuple(range(1, len(geometry_slots)))
    return bool(
        tuple(item.index for item in geometry_slots)
        == tuple(range(1, len(geometry_slots) + 1))
        and tuple(item.boundary.boundary_index for item in geometry_spacings)
        == expected
        and tuple(item.boundary.boundary_index for item in evidence.observations)
        == expected
        and all(
            observation.spacing_evidence.boundary
            == geometry_spacing.boundary
            and observation.content_continuity.boundary
            == geometry_spacing.boundary
            for observation, geometry_spacing in zip(
                evidence.observations,
                geometry_spacings,
                strict=True,
            )
        )
    )
