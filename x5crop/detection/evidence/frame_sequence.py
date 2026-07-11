from __future__ import annotations

from dataclasses import dataclass

from ...formats import FormatPhysicalSpec
from ...gap_methods import is_hard_gap_method
from ..geometry import CandidateGeometry
from ..physical.boundary import HolderOcclusionEvidence
from ..physical.intervals import PixelInterval
from ..physical.spacing import (
    InterFrameSpacingEvidence,
    SequenceConservationEvidence,
    inter_frame_spacing_evidence,
    sequence_conservation_evidence,
)
from .state import EvidenceState


@dataclass(frozen=True)
class FrameSequenceEvidence:
    holder_occlusion: HolderOcclusionEvidence
    spacings: tuple[InterFrameSpacingEvidence, ...]
    conservation: SequenceConservationEvidence


def _unresolved_spacing(index: int) -> InterFrameSpacingEvidence:
    return InterFrameSpacingEvidence(
        index=index,
        state=EvidenceState.UNAVAILABLE,
        kind="unresolved",
        signed_width_px=PixelInterval.zero(),
        reason="separator_or_overlap_measurement_unavailable",
    )


def frame_sequence_evidence(
    geometry: CandidateGeometry,
    physical_spec: FormatPhysicalSpec,
) -> FrameSequenceEvidence:
    by_index = {int(item.index): item for item in geometry.separators}
    spacings: list[InterFrameSpacingEvidence] = []
    for index in range(1, geometry.count):
        observation = by_index.get(index)
        if (
            observation is None
            or not is_hard_gap_method(observation.method)
            or observation.start is None
            or observation.end is None
        ):
            spacings.append(_unresolved_spacing(index))
            continue
        spacings.append(
            inter_frame_spacing_evidence(
                index,
                PixelInterval.exact(float(observation.end) - float(observation.start)),
            )
        )
    holder_occlusion = HolderOcclusionEvidence.unavailable()
    frame_width = PixelInterval.exact(
        float(geometry.visible_sequence_span.box.height)
        * float(physical_spec.horizontal_content_aspect)
    )
    conservation = sequence_conservation_evidence(
        visible_length_px=PixelInterval.exact(float(geometry.visible_sequence_span.box.width)),
        count=geometry.count,
        frame_width_px=frame_width,
        spacings=tuple(spacings),
        holder_occlusion=holder_occlusion,
    )
    return FrameSequenceEvidence(
        holder_occlusion=holder_occlusion,
        spacings=tuple(spacings),
        conservation=conservation,
    )
