from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import (
    BoundaryObservation,
    Box,
    CropEnvelope,
    FrameBoundary,
    FrameDimensionPrior,
    HolderSpan,
    MeasurementProvenance,
    PixelInterval,
    SeparatorAssignment,
    SeparatorBandObservation,
    VisibleSequenceSpan,
    EvidenceState,
)
from .boundary import HolderOcclusionEvidence
from .spacing import InterFrameSpacing


@dataclass(frozen=True)
class PhotoInterval:
    index: int
    start: PixelInterval
    end: PixelInterval
    start_provenance: MeasurementProvenance
    end_provenance: MeasurementProvenance
    start_independently_observed: bool
    end_independently_observed: bool

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("photo interval index must be positive")
        if self.end.maximum <= self.start.minimum:
            raise ValueError("photo interval must have positive possible width")

    @property
    def width_px(self) -> PixelInterval:
        return self.end.minus(self.start)

    @property
    def independently_observed(self) -> bool:
        return bool(
            self.start_independently_observed
            and self.end_independently_observed
        )


@dataclass(frozen=True)
class SequenceResiduals:
    dimension: float | None
    conservation: float | None
    boundary_uncertainty: float

    def __post_init__(self) -> None:
        values = tuple(
            value
            for value in (
                self.dimension,
                self.conservation,
                self.boundary_uncertainty,
            )
            if value is not None
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("sequence residuals must be finite and non-negative")


@dataclass(frozen=True)
class BoundaryAssignmentConsensus:
    state: EvidenceState
    reason: str
    solution_count: int
    conflicting_boundary_indexes: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.solution_count < 0:
            raise ValueError("boundary assignment solution count cannot be negative")
        if (
            self.state == EvidenceState.NOT_APPLICABLE
            and self.solution_count != 0
        ):
            raise ValueError("not-applicable assignment consensus has no solution")
        if (
            self.state != EvidenceState.NOT_APPLICABLE
            and self.solution_count == 0
        ):
            raise ValueError("assignment consensus requires a solution")
        if any(index <= 0 for index in self.conflicting_boundary_indexes):
            raise ValueError("conflicting boundary indexes must be positive")
        if not self.reason:
            raise ValueError("boundary assignment consensus requires a reason")


@dataclass(frozen=True)
class SequenceSolution:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    photo_intervals: tuple[PhotoInterval, ...]
    frames: tuple[Box, ...]
    separator_observations: tuple[SeparatorBandObservation, ...]
    separator_assignments: tuple[SeparatorAssignment, ...]
    frame_boundaries: tuple[FrameBoundary, ...]
    inter_frame_spacings: tuple[InterFrameSpacing, ...]
    holder_occlusion: HolderOcclusionEvidence
    frame_dimension_prior: FrameDimensionPrior
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    search_budget_exhausted: bool
    source: str
    automatic_processing_supported: bool
    sequence_hypothesis_name: str
    sequence_hypothesis_strategy: str
    sequence_provenance: MeasurementProvenance
    boundary_observations: tuple[BoundaryObservation, ...]

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("sequence solution count must be positive")
        if len(self.frames) != self.count:
            raise ValueError("sequence solution requires one frame per count")
        if len(self.photo_intervals) != self.count:
            raise ValueError("sequence solution requires one photo interval per frame")
        if len(self.frame_boundaries) != max(0, self.count - 1):
            raise ValueError("sequence solution has incomplete frame boundaries")
        if len(self.inter_frame_spacings) != max(0, self.count - 1):
            raise ValueError("sequence solution has incomplete inter-frame spacing")
        if any(not frame.valid() for frame in self.frames):
            raise ValueError("sequence solution frames must have positive extent")
        if any(
            left.right > right.left
            for left, right in zip(self.frames, self.frames[1:])
        ):
            raise ValueError("sequence solution frames must be monotonic")
        expected_boundaries = tuple(range(1, self.count))
        if (
            tuple(
                boundary.boundary_index
                for boundary in self.frame_boundaries
            )
            != expected_boundaries
        ):
            raise ValueError("sequence solution boundary indexes must be complete and ordered")


@dataclass(frozen=True)
class DualLaneSolution:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    photo_intervals: tuple[PhotoInterval, ...]
    frames: tuple[Box, ...]
    separator_observations: tuple[SeparatorBandObservation, ...]
    separator_assignments: tuple[SeparatorAssignment, ...]
    frame_boundaries: tuple[FrameBoundary, ...]
    inter_frame_spacings: tuple[InterFrameSpacing, ...]
    holder_occlusion: HolderOcclusionEvidence
    frame_dimension_prior: FrameDimensionPrior
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    search_budget_exhausted: bool
    source: str
    automatic_processing_supported: bool
    sequence_hypothesis_name: str
    sequence_hypothesis_strategy: str
    sequence_provenance: MeasurementProvenance
    boundary_observations: tuple[BoundaryObservation, ...]
    lane_solutions: tuple[SequenceSolution, ...]
    lane_boxes: tuple[Box, ...]
    lane_crop_envelopes: tuple[CropEnvelope, ...]

    def __post_init__(self) -> None:
        lane_count = len(self.lane_solutions)
        if lane_count <= 1:
            raise ValueError("dual-lane solution requires multiple lane sequences")
        if (
            len(self.lane_boxes) != lane_count
            or len(self.lane_crop_envelopes) != lane_count
        ):
            raise ValueError("dual-lane solution requires one box and envelope per lane")
        if any(not lane.valid() for lane in self.lane_boxes):
            raise ValueError("dual-lane solution requires valid lane boxes")
        if self.count != sum(lane.count for lane in self.lane_solutions):
            raise ValueError("dual-lane count must equal component sequence counts")
        if (
            len(self.frames) != self.count
            or any(not frame.valid() for frame in self.frames)
        ):
            raise ValueError("dual-lane solution requires one valid frame per count")
        if len(self.photo_intervals) != self.count:
            raise ValueError("dual-lane solution requires one photo interval per frame")
        expected_internal_boundaries = sum(
            max(0, lane.count - 1) for lane in self.lane_solutions
        )
        if len(self.frame_boundaries) != expected_internal_boundaries:
            raise ValueError("dual-lane solution has incomplete frame boundaries")
        if len(self.inter_frame_spacings) != expected_internal_boundaries:
            raise ValueError("dual-lane solution has incomplete inter-frame spacing")


@dataclass(frozen=True)
class ReviewOnlyGeometry:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    frame_dimension_prior: FrameDimensionPrior
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    source: str
    sequence_hypothesis_name: str
    sequence_hypothesis_strategy: str
    sequence_provenance: MeasurementProvenance
    boundary_observations: tuple[BoundaryObservation, ...]
    photo_intervals: tuple[PhotoInterval, ...] = ()
    frames: tuple[Box, ...] = ()
    separator_observations: tuple[SeparatorBandObservation, ...] = ()
    separator_assignments: tuple[SeparatorAssignment, ...] = ()
    frame_boundaries: tuple[FrameBoundary, ...] = ()
    inter_frame_spacings: tuple[InterFrameSpacing, ...] = ()
    holder_occlusion: HolderOcclusionEvidence = HolderOcclusionEvidence.unavailable()
    search_budget_exhausted: bool = False
    automatic_processing_supported: bool = False

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("review-only geometry count must be positive")
        if any(
            (
                self.frames,
                self.photo_intervals,
                self.separator_observations,
                self.separator_assignments,
                self.frame_boundaries,
                self.inter_frame_spacings,
            )
        ):
            raise ValueError("review-only geometry cannot contain solved geometry")
        if self.automatic_processing_supported:
            raise ValueError("review-only geometry cannot support automatic processing")


CandidateGeometry = SequenceSolution | DualLaneSolution | ReviewOnlyGeometry
