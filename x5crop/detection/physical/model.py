from __future__ import annotations

from dataclasses import dataclass

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
)
from .boundary import HolderOcclusionEvidence
from .spacing import InterFrameRelation


@dataclass(frozen=True)
class PhotoInterval:
    index: int
    start: PixelInterval
    end: PixelInterval
    provenance: MeasurementProvenance

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("photo interval index must be positive")
        if self.end.maximum <= self.start.minimum:
            raise ValueError("photo interval must have positive possible width")

    @property
    def width_px(self) -> PixelInterval:
        return self.end.minus(self.start)


@dataclass(frozen=True)
class SequenceResiduals:
    dimension: float | None
    conservation: float | None
    boundary_uncertainty: float


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
    inter_frame_relations: tuple[InterFrameRelation, ...]
    holder_occlusion: HolderOcclusionEvidence
    frame_dimension_prior: FrameDimensionPrior
    residuals: SequenceResiduals
    search_exhausted: bool
    source: str
    automatic_processing_supported: bool
    sequence_hypothesis_name: str
    sequence_hypothesis_strategy: str
    sequence_provenance: MeasurementProvenance
    boundary_observations: tuple[BoundaryObservation, ...]
    lane_boxes: tuple[Box, ...] = ()
    lane_crop_envelopes: tuple[CropEnvelope, ...] = ()
