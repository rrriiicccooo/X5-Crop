from __future__ import annotations

from dataclasses import dataclass

from ..domain import Box, MeasurementProvenance, SeparatorBandObservation
from .physical.spans import FilmSpan, HolderSpan


@dataclass(frozen=True)
class CandidateGeometry:
    format_id: str
    layout: str
    strip_mode: str
    count: int
    holder_span: HolderSpan
    film_span: FilmSpan
    work_frames: tuple[Box, ...]
    image_outer: Box
    image_frames: tuple[Box, ...]
    separators: tuple[SeparatorBandObservation, ...]
    origin: float
    pitch: float
    offset_fraction: float
    source: str
    automatic_processing_supported: bool
    contract: str | None
    outer_proposal_name: str
    outer_proposal_strategy: str
    outer_provenance: MeasurementProvenance
    lane_boxes: tuple[Box, ...] = ()
