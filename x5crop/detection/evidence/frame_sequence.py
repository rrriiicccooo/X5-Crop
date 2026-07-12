from __future__ import annotations

from dataclasses import dataclass

from ..physical.model import SequenceSolution
from ..physical.boundary import HolderOcclusionEvidence
from ..physical.spacing import (
    InterFrameRelation,
    SequenceConservationEvidence,
    sequence_conservation_evidence,
)
from x5crop.domain import PixelInterval


@dataclass(frozen=True)
class FrameSequenceEvidence:
    holder_occlusion: HolderOcclusionEvidence
    spacings: tuple[InterFrameRelation, ...]
    conservation: SequenceConservationEvidence


def frame_sequence_evidence(
    geometry: SequenceSolution,
) -> FrameSequenceEvidence:
    conservation = sequence_conservation_evidence(
        visible_length_px=PixelInterval.exact(
            float(geometry.visible_sequence_span.box.width)
        ),
        count=geometry.count,
        frame_width_px=geometry.frame_dimension_prior.width_px,
        spacings=geometry.inter_frame_relations,
        holder_occlusion=geometry.holder_occlusion,
    )
    return FrameSequenceEvidence(
        geometry.holder_occlusion,
        geometry.inter_frame_relations,
        conservation,
    )
