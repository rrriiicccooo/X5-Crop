"""Resolve correlated separator bands and their direct role authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import EvidenceState, ObservationId
from .model import (
    BoundaryEvidenceState,
    BoundaryRole,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .observation_types import (
    BoundaryEdgeObservation,
    SeparatorBandObservation,
)


class SeparatorRoleAuthorityFailureKind(str, Enum):
    """Why one material component cannot assign boundary roles by itself."""

    INSUFFICIENT_SPATIAL_SUPPORT = "insufficient_spatial_support"
    ALTERNATIVE_PAIR_INTERPRETATIONS = "alternative_pair_interpretations"
    ENDPOINT_ROLE_CONFLICT = "endpoint_role_conflict"


@dataclass(frozen=True)
class SeparatorSupportComponent:
    """One correlated separator family and its role-authority boundary.

    Bands that share an edge are one physical evidence component. The
    component remains one rank group even when it contains several possible
    edge pairs. Separator material may assign END/START roles only when there
    is exactly one source-wide pair. An intrinsic endpoint-role conflict only
    defeats that pair when the conflicting endpoint also belongs to another
    pair in the same component: that is a topological fork asking one physical
    edge to serve opposite separator roles. A leaf endpoint's direction hint
    is weaker than source-wide material. Partial-height alternatives remain
    correlated evidence, but do not defeat a unique compatible source-wide
    pair.
    """

    component_id: ObservationId
    edge_observation_ids: tuple[ObservationId, ...]
    band_observation_ids: tuple[ObservationId, ...]
    pair_edge_observation_ids: tuple[
        tuple[ObservationId, ObservationId], ...
    ]
    source_wide_pair_edge_observation_ids: tuple[
        tuple[ObservationId, ObservationId], ...
    ]
    role_authority_state: EvidenceState
    role_authority_pair_edge_observation_ids: (
        tuple[ObservationId, ObservationId] | None
    )
    conflicting_edge_observation_ids: tuple[ObservationId, ...]
    failure_kind: SeparatorRoleAuthorityFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        pairs = self.pair_edge_observation_ids
        source_wide_pairs = self.source_wide_pair_edge_observation_ids
        supported = (
            len(source_wide_pairs) == 1
            and self.role_authority_pair_edge_observation_ids
            == source_wide_pairs[0]
            and not self.conflicting_edge_observation_ids
        )
        unavailable = (
            not source_wide_pairs
            and self.role_authority_pair_edge_observation_ids is None
            and not self.conflicting_edge_observation_ids
        )
        contradicted = (
            bool(source_wide_pairs)
            and self.role_authority_pair_edge_observation_ids is None
        )
        if (
            not isinstance(self.component_id, ObservationId)
            or tuple(sorted(set(self.edge_observation_ids)))
            != self.edge_observation_ids
            or len(self.edge_observation_ids) < 2
            or tuple(sorted(set(self.band_observation_ids)))
            != self.band_observation_ids
            or not self.band_observation_ids
            or tuple(sorted(set(pairs))) != pairs
            or not pairs
            or any(
                len(pair) != 2
                or pair[0] == pair[1]
                or not set(pair).issubset(self.edge_observation_ids)
                for pair in pairs
            )
            or tuple(sorted(set(source_wide_pairs))) != source_wide_pairs
            or not set(source_wide_pairs).issubset(pairs)
            or tuple(sorted(set(self.conflicting_edge_observation_ids)))
            != self.conflicting_edge_observation_ids
            or not set(self.conflicting_edge_observation_ids).issubset(
                self.edge_observation_ids
            )
            or self.role_authority_state
            not in {
                EvidenceState.SUPPORTED,
                EvidenceState.UNAVAILABLE,
                EvidenceState.CONTRADICTED,
            }
            or (self.role_authority_state == EvidenceState.SUPPORTED)
            != supported
            or (self.role_authority_state == EvidenceState.UNAVAILABLE)
            != unavailable
            or (self.role_authority_state == EvidenceState.CONTRADICTED)
            != contradicted
            or (
                self.failure_kind
                == SeparatorRoleAuthorityFailureKind.INSUFFICIENT_SPATIAL_SUPPORT
            )
            != unavailable
            or (
                self.failure_kind
                == SeparatorRoleAuthorityFailureKind.ALTERNATIVE_PAIR_INTERPRETATIONS
            )
            != (contradicted and len(source_wide_pairs) > 1)
            or (
                self.failure_kind
                == SeparatorRoleAuthorityFailureKind.ENDPOINT_ROLE_CONFLICT
            )
            != (contradicted and bool(self.conflicting_edge_observation_ids))
            or (self.failure_kind is None) != supported
            or (self.reason is None) != supported
        ):
            raise ValueError("separator support component is invalid")


@dataclass(frozen=True)
class SeparatorSupportResolution:
    """Canonical connected-component resolution for supported bands."""

    components: tuple[SeparatorSupportComponent, ...]

    def __post_init__(self) -> None:
        if (
            tuple(item.component_id for item in self.components)
            != tuple(sorted({item.component_id for item in self.components}))
            or len(
                {
                    identity
                    for component in self.components
                    for identity in component.edge_observation_ids
                }
            )
            != sum(
                len(component.edge_observation_ids)
                for component in self.components
            )
        ):
            raise ValueError("separator support resolution is invalid")

    @property
    def edge_component_ids(self) -> dict[ObservationId, ObservationId]:
        return {
            identity: component.component_id
            for component in self.components
            for identity in component.edge_observation_ids
        }


def resolve_separator_support(
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
) -> SeparatorSupportResolution:
    """Resolve correlated band pairs without choosing among alternatives."""

    parent: dict[ObservationId, ObservationId] = {}

    def find(identity: ObservationId) -> ObservationId:
        parent.setdefault(identity, identity)
        while parent[identity] != identity:
            parent[identity] = parent[parent[identity]]
            identity = parent[identity]
        return identity

    def union(left: ObservationId, right: ObservationId) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    by_id = {item.observation_id: item for item in observations}
    if len(by_id) != len(observations):
        raise ValueError("separator support observations must be unique")
    supported_bands = tuple(
        band
        for band in separator_bands
        if band.evidence_state == BoundaryEvidenceState.SUPPORT
    )
    if any(
        band.left_edge_observation_id not in by_id
        or band.right_edge_observation_id not in by_id
        for band in supported_bands
    ):
        raise ValueError("separator band references an unregistered edge")
    for band in supported_bands:
        union(band.left_edge_observation_id, band.right_edge_observation_id)
    bands_by_root: dict[ObservationId, list[SeparatorBandObservation]] = {}
    for band in supported_bands:
        bands_by_root.setdefault(
            find(band.left_edge_observation_id),
            [],
        ).append(band)
    components: list[SeparatorSupportComponent] = []
    for bands in bands_by_root.values():
        band_ids = tuple(sorted({band.observation_id for band in bands}))
        component_id = min(band_ids)
        edge_ids = tuple(
            sorted(
                {
                    identity
                    for band in bands
                    for identity in (
                        band.left_edge_observation_id,
                        band.right_edge_observation_id,
                    )
                }
            )
        )
        pairs = tuple(
            sorted(
                {
                    (
                        band.left_edge_observation_id,
                        band.right_edge_observation_id,
                    )
                    for band in bands
                }
            )
        )
        source_wide_pairs = tuple(
            sorted(
                {
                    (
                        band.left_edge_observation_id,
                        band.right_edge_observation_id,
                    )
                    for band in bands
                    if band.material_support_region_count
                    >= SPATIAL_SUPPORT_REGION_COUNT
                }
            )
        )
        conflicting_edges: tuple[ObservationId, ...] = ()
        if len(source_wide_pairs) > 1:
            state = EvidenceState.CONTRADICTED
            role_pair = None
            failure = (
                SeparatorRoleAuthorityFailureKind.ALTERNATIVE_PAIR_INTERPRETATIONS
            )
            reason = (
                "connected separator material has alternative edge-pair "
                "interpretations"
            )
        elif source_wide_pairs:
            left_id, right_id = source_wide_pairs[0]
            pair_degree = {
                identity: sum(identity in pair for pair in pairs)
                for identity in edge_ids
            }
            conflicts = (
                tuple(
                    identity
                    for identity, expected_role in (
                        (left_id, BoundaryRole.END),
                        (right_id, BoundaryRole.START),
                    )
                    if by_id[identity].qualified_anchor_roles
                    and expected_role
                    not in by_id[identity].qualified_anchor_roles
                    and pair_degree[identity] > 1
                )
                if len(pairs) > 1
                else ()
            )
            if conflicts:
                state = EvidenceState.CONTRADICTED
                role_pair = None
                conflicting_edges = tuple(sorted(conflicts))
                failure = SeparatorRoleAuthorityFailureKind.ENDPOINT_ROLE_CONFLICT
                reason = (
                    "source-wide separator endpoints conflict with directly "
                    "observed boundary roles"
                )
            else:
                state = EvidenceState.SUPPORTED
                role_pair = source_wide_pairs[0]
                failure = None
                reason = None
        else:
            state = EvidenceState.UNAVAILABLE
            role_pair = None
            failure = (
                SeparatorRoleAuthorityFailureKind.INSUFFICIENT_SPATIAL_SUPPORT
            )
            reason = (
                "unique separator pair does not span every independent "
                "height region"
            )
        components.append(
            SeparatorSupportComponent(
                component_id=component_id,
                edge_observation_ids=edge_ids,
                band_observation_ids=band_ids,
                pair_edge_observation_ids=pairs,
                source_wide_pair_edge_observation_ids=source_wide_pairs,
                role_authority_state=state,
                role_authority_pair_edge_observation_ids=role_pair,
                conflicting_edge_observation_ids=conflicting_edges,
                failure_kind=failure,
                reason=reason,
            )
        )
    return SeparatorSupportResolution(
        components=tuple(sorted(components, key=lambda item: item.component_id))
    )


__all__ = [
    "SeparatorRoleAuthorityFailureKind",
    "SeparatorSupportComponent",
    "SeparatorSupportResolution",
    "resolve_separator_support",
]
