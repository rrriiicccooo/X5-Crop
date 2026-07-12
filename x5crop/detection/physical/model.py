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


def combined_sequence_residuals(
    lane_solutions: tuple[SequenceSolution, ...],
) -> SequenceResiduals:
    if not lane_solutions:
        raise ValueError("combined residuals require lane solutions")

    def maximum(name: str) -> float | None:
        values = tuple(
            value
            for lane in lane_solutions
            if (value := getattr(lane.residuals, name)) is not None
        )
        return max(values) if values else None

    return SequenceResiduals(
        dimension=maximum("dimension"),
        conservation=maximum("conservation"),
        boundary_uncertainty=max(
            lane.residuals.boundary_uncertainty for lane in lane_solutions
        ),
    )


def combined_assignment_consensus(
    lane_solutions: tuple[SequenceSolution, ...],
) -> BoundaryAssignmentConsensus:
    if not lane_solutions:
        raise ValueError("combined assignment consensus requires lane solutions")
    resolved = all(
        lane.assignment_consensus.state == EvidenceState.SUPPORTED
        for lane in lane_solutions
    )
    return BoundaryAssignmentConsensus(
        EvidenceState.SUPPORTED if resolved else EvidenceState.UNAVAILABLE,
        (
            "dual_lane_separator_assignments_agree"
            if resolved
            else "dual_lane_separator_assignments_unresolved"
        ),
        math.prod(
            lane.assignment_consensus.solution_count for lane in lane_solutions
        ),
        (),
    )


@dataclass(frozen=True)
class DualLaneSolution:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    frames: tuple[Box, ...]
    residuals: SequenceResiduals
    assignment_consensus: BoundaryAssignmentConsensus
    search_budget_exhausted: bool
    automatic_processing_supported: bool
    sequence_hypothesis_name: str
    sequence_hypothesis_strategy: str
    sequence_provenance: MeasurementProvenance
    lane_solutions: tuple[SequenceSolution, ...]
    lane_boxes: tuple[Box, ...]
    lane_crop_envelopes: tuple[CropEnvelope, ...]

    def __post_init__(self) -> None:
        def translated(box: Box, lane_box: Box) -> Box:
            return Box(
                box.left + lane_box.left,
                box.top + lane_box.top,
                box.right + lane_box.left,
                box.bottom + lane_box.top,
            )

        def enclosing(boxes: tuple[Box, ...]) -> Box:
            return Box(
                min(box.left for box in boxes),
                min(box.top for box in boxes),
                max(box.right for box in boxes),
                max(box.bottom for box in boxes),
            )

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
        if any(
            lane.holder_span.box
            != Box(0, 0, lane_box.width, lane_box.height)
            for lane_box, lane in zip(
                self.lane_boxes,
                self.lane_solutions,
                strict=True,
            )
        ):
            raise ValueError("dual-lane component holder spans must match lane boxes")
        if self.holder_span != HolderSpan(enclosing(self.lane_boxes)):
            raise ValueError("dual-lane holder span must enclose the lane boxes")
        if self.count != sum(lane.count for lane in self.lane_solutions):
            raise ValueError("dual-lane count must equal component sequence counts")
        if (
            len(self.frames) != self.count
            or any(not frame.valid() for frame in self.frames)
        ):
            raise ValueError("dual-lane solution requires one valid frame per count")
        if any(lane.layout != "horizontal" for lane in self.lane_solutions):
            raise ValueError("dual-lane components must use horizontal lane workspace")
        expected_frames = tuple(
            translated(frame, lane_box)
            for lane_box, lane in zip(
                self.lane_boxes,
                self.lane_solutions,
                strict=True,
            )
            for frame in lane.frames
        )
        if self.frames != expected_frames:
            raise ValueError("dual-lane frames must be the exact lane projections")
        expected_lane_envelopes = tuple(
            CropEnvelope(translated(lane.crop_envelope.box, lane_box))
            for lane_box, lane in zip(
                self.lane_boxes,
                self.lane_solutions,
                strict=True,
            )
        )
        if self.lane_crop_envelopes != expected_lane_envelopes:
            raise ValueError(
                "dual-lane crop envelopes must be the exact lane projections"
            )
        expected_visible_span = VisibleSequenceSpan(
            enclosing(
                tuple(
                    translated(lane.visible_sequence_span.box, lane_box)
                    for lane_box, lane in zip(
                        self.lane_boxes,
                        self.lane_solutions,
                        strict=True,
                    )
                )
            )
        )
        if self.visible_sequence_span != expected_visible_span:
            raise ValueError(
                "dual-lane visible span must be the exact lane projection"
            )
        if self.crop_envelope != CropEnvelope(
            enclosing(tuple(item.box for item in expected_lane_envelopes))
        ):
            raise ValueError(
                "dual-lane crop envelope must enclose the exact lane projections"
            )
        if self.residuals != combined_sequence_residuals(self.lane_solutions):
            raise ValueError("dual-lane residuals must be derived from lane solutions")
        if self.assignment_consensus != combined_assignment_consensus(
            self.lane_solutions
        ):
            raise ValueError(
                "dual-lane assignment consensus must be derived from lane solutions"
            )


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
