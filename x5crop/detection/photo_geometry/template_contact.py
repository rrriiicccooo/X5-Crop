"""Register candidate-independent shared-edge observations for contact.

A contact candidate is not a placement and does not know an adjacency
ordinal.  It is one already registered long-axis edge whose coordinate is
independently authoritative and which is not owned by positive separator
material.  The bounded phase solver may project that same physical edge onto
adjacent END/START roles; continuity and Gate remain responsible for proving
the selected topology.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import ObservationId
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import BoundaryEvidenceState, BoundaryRole
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .physical_identity import physical_observation_id
from .template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    intrinsic_direct_role_authority_bases,
)


class ContactEdgeAuthorityBasis(str, Enum):
    """Independent coordinate authority retained by one shared edge."""

    SOURCE_WIDE_EDGE = "source_wide_edge"
    AGGREGATE_UNION = "aggregate_union"


@dataclass(frozen=True)
class ContactEdgeObservation:
    """One role-free physical edge eligible for bounded contact hypotheses."""

    observation_id: ObservationId
    physical_edge_id: ObservationId
    shared_edge_observation_id: ObservationId
    authority_bases: tuple[ContactEdgeAuthorityBasis, ...]
    qualified_anchor_roles: tuple[BoundaryRole, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.physical_edge_id, ObservationId)
            or not isinstance(self.shared_edge_observation_id, ObservationId)
            or self.physical_edge_id != self.shared_edge_observation_id
            or not self.authority_bases
            or tuple(dict.fromkeys(self.authority_bases)) != self.authority_bases
            or any(
                not isinstance(item, ContactEdgeAuthorityBasis)
                for item in self.authority_bases
            )
            or not self.qualified_anchor_roles
            or tuple(dict.fromkeys(self.qualified_anchor_roles))
            != self.qualified_anchor_roles
            or any(
                role not in {BoundaryRole.START, BoundaryRole.END}
                for role in self.qualified_anchor_roles
            )
        ):
            raise ValueError("contact edge observation is invalid")


def observe_contact_edges(
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
) -> tuple[ContactEdgeObservation, ...]:
    """Return every unique authoritative non-separator physical edge."""

    intrinsic = intrinsic_direct_role_authority_bases(
        observations,
        measurement_sets,
    )
    # Any positively observed material band is direct counterevidence to a
    # shared edge, even when that band is wider or narrower than the nominal
    # format gap.  Gap compatibility belongs to SeparatorRelation; contact
    # eligibility only asks whether material exists at all.
    separator_edge_ids = {
        identity
        for band in separator_bands
        if band.evidence_state == BoundaryEvidenceState.SUPPORT
        for identity in (
            band.left_edge_observation_id,
            band.right_edge_observation_id,
        )
    }
    authoritative_edges: list[BoundaryEdgeObservation] = []
    eligible: list[
        tuple[
            BoundaryEdgeObservation,
            tuple[ContactEdgeAuthorityBasis, ...],
        ]
    ] = []
    for edge in observations:
        bases = intrinsic.get(edge.observation_id, ())
        if not bases or not edge.qualified_anchor_roles:
            continue
        authoritative_edges.append(edge)
        if edge.observation_id in separator_edge_ids:
            continue
        contact_bases = tuple(
            ContactEdgeAuthorityBasis.SOURCE_WIDE_EDGE
            if basis == DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE
            else ContactEdgeAuthorityBasis.AGGREGATE_UNION
            for basis in bases
            if basis
            in {
                DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
                DirectRoleAuthorityBasis.AGGREGATE_UNION,
            }
        )
        if not contact_bases:
            continue
        eligible.append((edge, contact_bases))

    # Distinct registered identities whose full coordinate intervals touch do
    # not prove one shared physical edge.  Positive separator ownership keeps
    # an edge from becoming a contact candidate, but it does not erase that
    # edge as a competing physical identity.  Mark the whole overlapping
    # authoritative component ambiguous in O(E log E), rather than joining
    # nearby lines or allowing either identity to impersonate a contact.
    ambiguous_ids: set[ObservationId] = set()
    component: list[BoundaryEdgeObservation] = []
    component_maximum = float("-inf")

    def close_component() -> None:
        if len(component) > 1:
            ambiguous_ids.update(item.observation_id for item in component)

    for edge in sorted(
        authoritative_edges,
        key=lambda item: (
            item.full_position_interval_px.minimum,
            item.full_position_interval_px.maximum,
            str(item.observation_id),
        ),
    ):
        interval = edge.full_position_interval_px
        if component and interval.minimum > component_maximum:
            close_component()
            component = []
            component_maximum = float("-inf")
        component.append(edge)
        component_maximum = max(component_maximum, interval.maximum)
    close_component()

    values: list[ContactEdgeObservation] = []
    for edge, contact_bases in eligible:
        if edge.observation_id in ambiguous_ids:
            continue
        values.append(
            ContactEdgeObservation(
                observation_id=physical_observation_id(
                    "contact-edge",
                    edge.observation_id,
                    tuple(item.value for item in contact_bases),
                ),
                physical_edge_id=edge.observation_id,
                shared_edge_observation_id=edge.observation_id,
                authority_bases=contact_bases,
                qualified_anchor_roles=edge.qualified_anchor_roles,
            )
        )
    return tuple(
        sorted(values, key=lambda item: str(item.observation_id))
    )


__all__ = [
    "ContactEdgeAuthorityBasis",
    "ContactEdgeObservation",
    "observe_contact_edges",
]
