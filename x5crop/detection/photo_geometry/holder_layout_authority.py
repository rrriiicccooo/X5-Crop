"""Conditional long-axis authority from a user-confirmed filled holder."""

from __future__ import annotations

from ...domain import EvidenceState, FiniteInterval
from ...configuration.model import HolderLayoutAuthority
from .chain_proposals import LaneObservationInput
from .sequence_models import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    LongAxisFillAuthority,
)
from .interval_math import add, multiply
from .lane_gap_model import LaneGapModel
from .source_geometry import SourceScanGeometry


def long_axis_fill_authority(
    lane: LaneObservationInput,
    geometry: SourceScanGeometry,
    gap_model: LaneGapModel,
    relations: tuple[LocalAdvanceRelation, ...],
) -> LongAxisFillAuthority:
    """Return centred-layout authority without inventing a missing gap.

    ``full`` supplies the factual claim that the physical strip uses the
    holder's complete filled layout. A placement can consume that claim only
    after the source has established its normal pitch, every adjacency remains
    normal, and the resulting fixed-format chain fits the visible holder.
    The frame span need not equal the scan-canvas span because holders retain
    physical margins beyond the first and last exposure.
    """

    if (
        lane.holder_layout_authority
        != HolderLayoutAuthority.USER_CONFIRMED_FILLED_HOLDER_LAYOUT
        or lane.output_slot_count != lane.measurement_slot_count
        or len(relations) != max(0, lane.output_slot_count - 1)
    ):
        return LongAxisFillAuthority.unavailable()

    width = geometry.width_state.extent_projection_px()
    if (
        gap_model.state == EvidenceState.SUPPORTED
        and gap_model.placement_pitch_interval_px is not None
        and all(
            relation.kind == LocalAdvanceKind.NOMINAL
            for relation in relations
        )
    ):
        span = add(
            width,
            multiply(
                gap_model.placement_pitch_interval_px,
                lane.output_slot_count - 1,
            ),
        )
        observation_ids = gap_model.supporting_observation_ids
    elif (
        gap_model.state == EvidenceState.UNAVAILABLE
        and all(
            relation.kind == LocalAdvanceKind.OBSERVED_NORMAL
            and relation.observation_ids
            for relation in relations
        )
    ):
        span = multiply(width, lane.output_slot_count)
        for relation in relations:
            span = add(span, relation.delta_interval_px)
        observation_ids = tuple(
            sorted(
                {
                    identity
                    for relation in relations
                    for identity in relation.observation_ids
                },
                key=str,
            )
        )
    else:
        return LongAxisFillAuthority.unavailable()
    visible_extent = lane.width_authority_px.width
    maximum_visible_extent = visible_extent * (
        1.0 + lane.holder_extent_tolerance_ratio
    )
    if span.maximum > maximum_visible_extent:
        return LongAxisFillAuthority.unavailable()

    midpoint_uncertainty = (
        visible_extent * lane.holder_extent_tolerance_ratio / 2.0
    )
    midpoint_authority = FiniteInterval(
        lane.width_authority_px.center - midpoint_uncertainty,
        lane.width_authority_px.center + midpoint_uncertainty,
    )
    return LongAxisFillAuthority(
        state=EvidenceState.SUPPORTED,
        chain_span_interval_px=span,
        centered_midpoint_authority_px=midpoint_authority,
        observation_ids=observation_ids,
    )
