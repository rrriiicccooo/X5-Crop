from __future__ import annotations

from dataclasses import dataclass

from ..domain import (
    BoundaryObservation,
    Box,
    CropEnvelope,
    FrameDimensionEstimate,
    FrameBoundary,
    HolderSpan,
    MeasurementProvenance,
    SeparatorAssignment,
    SeparatorBandObservation,
    VisibleSequenceSpan,
)


@dataclass(frozen=True)
class CandidateGeometry:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    frames: tuple[Box, ...]
    separator_observations: tuple[SeparatorBandObservation, ...]
    separator_assignments: tuple[SeparatorAssignment, ...]
    frame_boundaries: tuple[FrameBoundary, ...]
    frame_dimension_estimate: FrameDimensionEstimate
    source: str
    automatic_processing_supported: bool
    sequence_hypothesis_name: str
    sequence_hypothesis_strategy: str
    sequence_provenance: MeasurementProvenance
    boundary_observations: tuple[BoundaryObservation, ...]
    lane_boxes: tuple[Box, ...] = ()
    lane_crop_envelopes: tuple[CropEnvelope, ...] = ()
