from __future__ import annotations

from dataclasses import dataclass

from ..physical.model import SequenceSolution
from ..physical.boundary import (
    HolderOcclusionEvidence,
    visible_sequence_length_interval,
)
from ..physical.spacing import (
    InterFrameSpacing,
    SequenceConservationEvidence,
    sequence_conservation_evidence,
)


@dataclass(frozen=True)
class FrameSequenceEvidence:
    holder_occlusion: HolderOcclusionEvidence
    spacings: tuple[InterFrameSpacing, ...]
    conservation: SequenceConservationEvidence


def frame_sequence_evidence(
    geometry: SequenceSolution,
) -> FrameSequenceEvidence:
    conservation = sequence_conservation_evidence(
        visible_length_px=visible_sequence_length_interval(
            geometry.visible_sequence_span,
            geometry.boundary_observations,
        ),
        count=geometry.count,
        frame_width_px=geometry.frame_dimension_prior.width_px,
        spacings=geometry.inter_frame_spacings,
        holder_occlusion=geometry.holder_occlusion,
    )
    return FrameSequenceEvidence(
        geometry.holder_occlusion,
        geometry.inter_frame_spacings,
        conservation,
    )
