"""Interpret candidate-independent content topology as negative evidence."""

from __future__ import annotations

from ...domain import FiniteInterval
from ...run_local_identity import run_local_id
from .content_boundary_queries import (
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
from .model import BoundaryRole
from .template_placement import FormatPlacement


def content_veto_assessment(
    placement: FormatPlacement,
    content_index: ContentTopologyIndex,
) -> ContentVetoAssessment:
    facts: list[ContentVetoFact] = []
    frames = placement.frames
    for ordinal, frame in enumerate(frames, 1):
        slot_core_minimum = frame.start.full_position_interval_px.maximum
        slot_core_maximum = frame.end.full_position_interval_px.minimum
        if slot_core_maximum < slot_core_minimum:
            continue
        slot_core = FiniteInterval(slot_core_minimum, slot_core_maximum)
        for role, boundary in (
            (BoundaryRole.TOP, frame.top),
            (BoundaryRole.BOTTOM, frame.bottom),
        ):
            veto_ids = content_cross_boundary_ids(
                content_index,
                slot_core=slot_core,
                boundary=boundary,
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

    first = frames[0]
    last = frames[-1]
    for role, ordinal, boundary in (
        (BoundaryRole.START, 1, first.start),
        (BoundaryRole.END, len(frames), last.end),
    ):
        adjacent = first if role == BoundaryRole.START else last
        cross_core_minimum = adjacent.top.full_position_interval_px.maximum
        cross_core_maximum = adjacent.bottom.full_position_interval_px.minimum
        if cross_core_maximum < cross_core_minimum:
            continue
        cross_core = FiniteInterval(cross_core_minimum, cross_core_maximum)
        crossing_ids = content_sequence_boundary_ids(
            content_index,
            boundary=boundary,
            cross_core=cross_core,
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

    for ordinal, (left, right) in enumerate(zip(frames, frames[1:]), 1):
        core_minimum = left.end.full_position_interval_px.maximum
        core_maximum = right.start.full_position_interval_px.minimum
        cross_core_minimum = max(
            left.top.full_position_interval_px.maximum,
            right.top.full_position_interval_px.maximum,
        )
        cross_core_maximum = min(
            left.bottom.full_position_interval_px.minimum,
            right.bottom.full_position_interval_px.minimum,
        )
        if core_minimum >= core_maximum or cross_core_minimum >= cross_core_maximum:
            continue
        crossing_ids = content_occupies_sequence_core(
            content_index,
            sequence_core=FiniteInterval(core_minimum, core_maximum),
            cross_core=FiniteInterval(cross_core_minimum, cross_core_maximum),
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


__all__ = ["content_veto_assessment"]
