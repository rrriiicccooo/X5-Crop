"""Complete-chain authority predicates."""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import EvidenceState, ObservationId
from .axis_authority import (
    CrossAuthorityVector,
    SequenceAuthorityVector,
    SharedAuthorityVector,
)
from .chains import CompleteFormatChain
from .model import BoundaryRole
from .sequence_models import LocalAdvanceKind


@dataclass(frozen=True)
class PlacementAxisAuthority:
    sequence: SequenceAuthorityVector
    cross: CrossAuthorityVector
    shared: SharedAuthorityVector
    direct_observation_ids: tuple[ObservationId, ...]


def placement_axis_authority(
    placement: CompleteFormatChain,
    *,
    content_veto_passed: bool,
) -> PlacementAxisAuthority:
    """Return independent sequence, cross, and shared authority axes."""

    band_edge_ids = {
        identity
        for band in placement.sequence.separator_bands
        for identity in (
            band.observation.left_edge_observation_id,
            band.observation.right_edge_observation_id,
        )
    }
    outer_ids = {
        observation.observation_id
        for observation in placement.sequence.observations
        if observation.observation_id is not None
        and observation.observation_id not in band_edge_ids
    }
    band_ids = {
        band.observation.observation_id
        for band in placement.sequence.separator_bands
    }
    sequence_ids = tuple(sorted(band_ids | outer_ids, key=str))
    cross_ids = tuple(
        sorted(
            {
                evidence.observation.observation_id
                for evidence in placement.cross.evidence
            },
            key=str,
        )
    )
    has_cross_pair = (
        len({item.role for item in placement.cross.evidence}) == 2
    )
    common_cross_direction = has_cross_pair and max(
        item.observation.fit_angle_interval_degrees.minimum
        for item in placement.cross.evidence
    ) <= min(
        item.observation.fit_angle_interval_degrees.maximum
        for item in placement.cross.evidence
    )
    sequence = SequenceAuthorityVector(
        complete_direct_chain_count=int(
            len(placement.sequence.separator_bands)
            == placement.output_slot_count - 1
        ),
        direct_separator_band_count=len(
            placement.sequence.separator_bands
        ),
        independent_separator_support_region_count=sum(
            band.observation.independent_support_region_count
            for band in placement.sequence.separator_bands
        ),
        direct_outer_boundary_count=len(outer_ids),
        normal_completion_authorized_count=int(
            len(placement.sequence.separator_bands)
            == placement.output_slot_count - 1
            or placement.sequence.lane_gap_model.state
            == EvidenceState.SUPPORTED
        ),
        local_advance_authorized_count=int(
            placement_local_advance_authorized(placement)
        ),
        filled_holder_centering_authorized_count=int(
            placement.sequence.long_axis_fill_authority.state
            == EvidenceState.SUPPORTED
        ),
        observation_ids=sequence_ids,
    )
    cross = CrossAuthorityVector(
        fixed_height_placement_authorized_count=int(
            bool(placement.cross.evidence)
        ),
        complete_top_bottom_pair_count=int(has_cross_pair),
        direct_height_span_validated_count=int(
            placement.cross.direct_height_span_validated
        ),
        common_top_bottom_direction_count=int(common_cross_direction),
        source_spanning_boundary_family_count=sum(
            evidence.observation.source_spanning_continuous
            for evidence in placement.cross.evidence
        ),
        direct_boundary_family_count=len(cross_ids),
        independent_support_region_count=sum(
            evidence.observation.independent_support_region_count
            for evidence in placement.cross.evidence
        ),
        observation_ids=cross_ids,
    )
    return PlacementAxisAuthority(
        sequence=sequence,
        cross=cross,
        shared=SharedAuthorityVector(
            source_scale_compatible=True,
            direction_bound_lane_count=1,
            source_lane_authority_bound_count=1,
            content_veto_passed_lane_count=int(content_veto_passed),
        ),
        direct_observation_ids=tuple(
            sorted(band_ids | outer_ids | set(cross_ids), key=str)
        ),
    )


def placement_local_advance_authorized(
    placement: CompleteFormatChain,
) -> bool:
    """Require every adjacency to be direct or supported by ``G_source``."""

    observed_roles = {
        (item.role.lane_ordinal, item.role.role)
        for item in placement.sequence.observations
    }
    for ordinal, relation in enumerate(
        placement.sequence.local_advance_relations,
        1,
    ):
        if relation.kind != LocalAdvanceKind.NOMINAL:
            if not relation.observation_ids:
                return False
            continue
        if {
            (ordinal, BoundaryRole.END),
            (ordinal + 1, BoundaryRole.START),
        }.issubset(observed_roles):
            continue
        if placement.sequence.lane_gap_model.state == EvidenceState.SUPPORTED:
            continue
        return False
    return True
