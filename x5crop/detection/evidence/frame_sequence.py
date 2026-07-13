from __future__ import annotations

from ..physical.model import SequenceSolution
from ..physical.boundary import (
    visible_sequence_length_interval,
)
from ..physical.spacing import (
    SequenceConservationEvidence,
    sequence_conservation_evidence,
)


def sequence_conservation_for_geometry(
    geometry: SequenceSolution,
) -> SequenceConservationEvidence:
    return sequence_conservation_evidence(
        visible_length_px=visible_sequence_length_interval(
            geometry.visible_sequence_span,
            geometry.boundary_paths,
        ),
        count=geometry.count,
        frame_width_px=geometry.frame_dimension_prior.width_px,
        spacings=geometry.inter_frame_spacings,
        holder_occlusion=geometry.holder_occlusion,
    )
