from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box, MeasurementProvenance, SeparatorBandObservation
from .physical.boundary import BoundaryObservation
from .physical.spans import CropEnvelope, HolderSpan, VisibleSequenceSpan


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
    separators: tuple[SeparatorBandObservation, ...]
    origin: float
    pitch: float
    offset_fraction: float
    source: str
    automatic_processing_supported: bool
    contract: str | None
    sequence_hypothesis_name: str
    sequence_hypothesis_strategy: str
    sequence_provenance: MeasurementProvenance
    boundary_observations: tuple[BoundaryObservation, ...]
    lane_boxes: tuple[Box, ...] = ()
