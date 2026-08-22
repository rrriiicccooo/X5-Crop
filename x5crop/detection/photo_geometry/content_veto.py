"""Interpret content topology against one final post-bleed footprint set."""

from __future__ import annotations

from ...geometry.convex import ConvexPolygon
from ...run_local_identity import run_local_id
from .content_boundary_queries import (
    StripFootprint,
    content_cross_boundary_ids,
    content_sequence_boundary_ids,
    content_occupies_sequence_core,
)
from .content_topology import ContentTopologyIndex
from .content_veto_model import (
    ContentVetoAssessment,
    ContentVetoFact,
    ContentVetoReason,
)
from .model import BoundaryAxis, BoundaryRole
from .template_placement import FormatPlacement


def _strip_footprint(
    placement: FormatPlacement,
    footprint: ConvexPolygon,
) -> StripFootprint:
    """Normalize one source-coordinate footprint to strip axes."""

    return StripFootprint(
        points=(
            footprint
            if placement.width_axis == BoundaryAxis.X
            else tuple((y, x) for x, y in footprint)
        )
    )


def content_veto_assessment(
    placement: FormatPlacement,
    required_source_footprints: tuple[ConvexPolygon, ...],
    content_index: ContentTopologyIndex,
) -> ContentVetoAssessment:
    """Veto only when content crosses the crop after residual and bleed.

    The polygons are already fixed by the unique placement.  Content cannot
    move an edge, select a runner, or create geometry; it can only contradict
    the complete final footprint set.
    """

    if len(required_source_footprints) != placement.output_slot_count:
        raise ValueError("content veto requires one final footprint per slot")
    facts: list[ContentVetoFact] = []
    footprints = tuple(
        _strip_footprint(placement, footprint)
        for footprint in required_source_footprints
    )
    for ordinal, footprint in enumerate(footprints, 1):
        for role in (BoundaryRole.TOP, BoundaryRole.BOTTOM):
            veto_ids = content_cross_boundary_ids(
                content_index,
                footprint=footprint,
                role=role,
            )
            if veto_ids:
                facts.append(
                    ContentVetoFact(
                        reason=ContentVetoReason.SLOT_CONTENT_CROPPED_IN,
                        slot_ordinal=ordinal,
                        boundary_role=role,
                        observation_ids=veto_ids,
                    )
                )

    for role, ordinal, footprint in (
        (BoundaryRole.START, 1, footprints[0]),
        (BoundaryRole.END, len(footprints), footprints[-1]),
    ):
        crossing_ids = content_sequence_boundary_ids(
            content_index,
            footprint=footprint,
            role=role,
        )
        if crossing_ids:
            facts.append(
                ContentVetoFact(
                    reason=ContentVetoReason.OUTER_SLOT_CONTENT_OMITTED,
                    slot_ordinal=ordinal,
                    boundary_role=role,
                    observation_ids=crossing_ids,
                )
            )

    for ordinal, (left, right) in enumerate(
        zip(footprints, footprints[1:]),
        1,
    ):
        crossing_ids = content_occupies_sequence_core(
            content_index,
            left=left,
            right=right,
        )
        if crossing_ids:
            facts.append(
                ContentVetoFact(
                    reason=ContentVetoReason.SEPARATOR_CORE_CONTENT_CROSSING,
                    slot_ordinal=ordinal,
                    boundary_role=None,
                    observation_ids=crossing_ids,
                )
            )

    ordered = tuple(
        sorted(
            {
                (
                    item.reason,
                    item.slot_ordinal,
                    item.boundary_role,
                    item.observation_ids,
                ): item
                for item in facts
            }.values(),
            key=lambda item: (
                item.reason.value,
                item.slot_ordinal,
                "" if item.boundary_role is None else item.boundary_role.value,
                tuple(map(str, item.observation_ids)),
            ),
        )
    )
    assessment_id = run_local_id(
        "content-veto",
        placement.placement_id,
        *(
            value
            for item in ordered
            for value in (
                item.reason.value,
                str(item.slot_ordinal),
                "none" if item.boundary_role is None else item.boundary_role.value,
                *(str(identity) for identity in item.observation_ids),
            )
        ),
    )
    return ContentVetoAssessment(
        assessment_id=assessment_id,
        placement_id=placement.placement_id,
        facts=ordered,
    )
