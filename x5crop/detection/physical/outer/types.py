from __future__ import annotations

from dataclasses import dataclass

from ....domain import Box, MeasurementProvenance
from ..boundary import BoundaryObservation
from ..spans import CropEnvelope, VisibleSequenceSpan


@dataclass(frozen=True)
class SequenceHypothesis:
    name: str
    visible_sequence_span: VisibleSequenceSpan
    crop_envelope: CropEnvelope
    strategy: str
    provenance: MeasurementProvenance
    boundary_observations: tuple[BoundaryObservation, ...]

    @classmethod
    def from_box_hypothesis(
        cls,
        name: str,
        box: Box,
        strategy: str,
        provenance: MeasurementProvenance,
        *,
        boundary_observations: tuple[BoundaryObservation, ...] = (),
    ) -> "SequenceHypothesis":
        return cls(
            name=name,
            visible_sequence_span=VisibleSequenceSpan(box),
            crop_envelope=CropEnvelope(box),
            strategy=strategy,
            provenance=provenance,
            boundary_observations=boundary_observations,
        )
