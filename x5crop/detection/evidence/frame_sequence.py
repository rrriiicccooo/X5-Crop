from __future__ import annotations

from dataclasses import dataclass

from ..geometry import CandidateGeometry
from x5crop.domain import EvidenceState, PixelInterval
from ..physical.boundary import (
    HolderOcclusionEvidence,
    holder_occlusion_for_sequence,
)
from ..physical.spacing import (
    InterFrameSpacingEvidence,
    SequenceConservationEvidence,
    inter_frame_spacing_evidence,
    sequence_conservation_evidence,
)


@dataclass(frozen=True)
class FrameSequenceEvidence:
    holder_occlusion: HolderOcclusionEvidence
    spacings: tuple[InterFrameSpacingEvidence, ...]
    conservation: SequenceConservationEvidence


def _holder_occlusion(geometry: CandidateGeometry) -> HolderOcclusionEvidence:
    return holder_occlusion_for_sequence(
        geometry.boundary_observations,
        geometry.visible_sequence_span,
        geometry.frame_boundaries,
        frame_width_px=geometry.frame_dimension_estimate.width_px,
    )


def _spacing_evidence(
    geometry: CandidateGeometry,
    holder_occlusion: HolderOcclusionEvidence,
) -> tuple[InterFrameSpacingEvidence, ...]:
    span = geometry.visible_sequence_span.box
    boundaries = tuple(
        sorted(
            geometry.frame_boundaries,
            key=lambda boundary: boundary.boundary_index,
        )
    )
    if not boundaries:
        return ()
    frame_width = geometry.frame_dimension_estimate.width_px
    spacings: list[InterFrameSpacingEvidence] = []
    previous_position = PixelInterval.exact(float(span.left))
    previous_spacing = PixelInterval.zero()
    for boundary in boundaries:
        if boundary.boundary_index == 1:
            inferred = (
                boundary.position.minus(previous_position)
                .plus(holder_occlusion.leading.hidden_width_px)
                .minus(frame_width)
                .scaled(2.0)
            )
        else:
            inferred = (
                boundary.position.minus(previous_position)
                .minus(frame_width)
                .scaled(2.0)
                .minus(previous_spacing)
            )
        assignment = boundary.assignment
        if assignment is not None and assignment.independent:
            measured = PixelInterval.exact(assignment.observation.width)
            matches = measured.intersects(inferred)
            evidence = InterFrameSpacingEvidence(
                index=boundary.boundary_index,
                state=(
                    EvidenceState.SUPPORTED
                    if matches
                    else EvidenceState.CONTRADICTED
                ),
                kind="separator",
                signed_width_px=measured,
                reason=(
                    "observed_separator_matches_cut_equation"
                    if matches
                    else "observed_separator_contradicts_cut_equation"
                ),
            )
        else:
            modeled = inter_frame_spacing_evidence(
                boundary.boundary_index,
                inferred,
            )
            evidence = InterFrameSpacingEvidence(
                modeled.index,
                modeled.state,
                modeled.kind,
                modeled.signed_width_px,
                f"{modeled.kind}_spacing_from_cut_equation",
            )
        spacings.append(evidence)
        previous_position = boundary.position
        previous_spacing = evidence.signed_width_px

    trailing_constraint = (
        PixelInterval.exact(float(span.right))
        .minus(boundaries[-1].position)
        .plus(holder_occlusion.trailing.hidden_width_px)
        .minus(frame_width)
        .scaled(2.0)
    )
    if not spacings[-1].signed_width_px.intersects(trailing_constraint):
        last = spacings[-1]
        spacings[-1] = InterFrameSpacingEvidence(
            last.index,
            EvidenceState.CONTRADICTED,
            last.kind,
            last.signed_width_px,
            "spacing_contradicts_trailing_cut_equation",
        )
    return tuple(spacings)


def frame_sequence_evidence(
    geometry: CandidateGeometry,
) -> FrameSequenceEvidence:
    occlusion = _holder_occlusion(geometry)
    spacings = _spacing_evidence(geometry, occlusion)
    conservation = sequence_conservation_evidence(
        visible_length_px=PixelInterval.exact(
            float(geometry.visible_sequence_span.box.width)
        ),
        count=geometry.count,
        frame_width_px=geometry.frame_dimension_estimate.width_px,
        spacings=spacings,
        holder_occlusion=occlusion,
    )
    return FrameSequenceEvidence(occlusion, spacings, conservation)
