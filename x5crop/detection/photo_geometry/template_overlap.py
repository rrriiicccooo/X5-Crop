"""Register candidate-independent reversed-edge observations for overlap.

An overlap proposal is not a placement and carries no adjacency ordinal.  It
joins only two spatially adjacent, independently authoritative long-axis
edges: the next Frame's START lies strictly before the current Frame's END in
template direction.  The bounded phase solver may project that exact pair
onto one adjacency; coverage, continuity, competition and Gate retain final
authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import FiniteInterval, ObservationId
from .measurement_model import PhotoBoundaryMeasurementSet
from .model import BoundaryEvidenceState, BoundaryRole
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .physical_identity import physical_observation_id
from .template_direct_role_authority import (
    DirectRoleAuthorityBasis,
    intrinsic_direct_role_authority_bases,
)


_NUMERIC_EPSILON_PX = 1.0e-7
_INTRINSIC_BASES = frozenset(
    {
        DirectRoleAuthorityBasis.SOURCE_WIDE_EDGE,
        DirectRoleAuthorityBasis.AGGREGATE_UNION,
    }
)

_OrientedEdge = tuple[
    BoundaryEdgeObservation,
    tuple[DirectRoleAuthorityBasis, ...],
    FiniteInterval,
]


@dataclass(frozen=True)
class OverlapEdgePairObservation:
    """One role-aware but ordinal-free reversed physical edge pair."""

    observation_id: ObservationId
    end_edge_observation_id: ObservationId
    next_start_edge_observation_id: ObservationId
    signed_gap_interval_px: FiniteInterval
    canonical_signed_gap_px: float
    end_authority_bases: tuple[DirectRoleAuthorityBasis, ...]
    next_start_authority_bases: tuple[DirectRoleAuthorityBasis, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_id, ObservationId)
            or not isinstance(self.end_edge_observation_id, ObservationId)
            or not isinstance(
                self.next_start_edge_observation_id,
                ObservationId,
            )
            or self.end_edge_observation_id
            == self.next_start_edge_observation_id
            or self.signed_gap_interval_px.maximum
            >= -_NUMERIC_EPSILON_PX
            or not self.signed_gap_interval_px.contains(
                self.canonical_signed_gap_px,
                epsilon=1.0e-9,
            )
            or not self.end_authority_bases
            or not self.next_start_authority_bases
            or any(
                basis not in _INTRINSIC_BASES
                for basis in (
                    *self.end_authority_bases,
                    *self.next_start_authority_bases,
                )
            )
        ):
            raise ValueError("overlap edge-pair observation is invalid")

    @property
    def supporting_observation_ids(self) -> tuple[ObservationId, ObservationId]:
        return (
            self.end_edge_observation_id,
            self.next_start_edge_observation_id,
        )


def _oriented_interval(
    interval: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    if direction > 0:
        return interval
    return FiniteInterval(-interval.maximum, -interval.minimum)


def observe_overlap_edge_pairs(
    observations: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    *,
    direction: int,
    maximum_overlap_px: float,
) -> tuple[OverlapEdgePairObservation, ...]:
    """Return a linear-size set of independent reversed-edge proposals."""

    if direction not in {-1, 1}:
        raise ValueError("overlap direction must be -1 or 1")
    if maximum_overlap_px <= 0.0:
        raise ValueError("maximum overlap must be positive")
    intrinsic = intrinsic_direct_role_authority_bases(
        observations,
        measurement_sets,
    )
    separator_edge_ids = {
        identity
        for band in separator_bands
        if band.evidence_state == BoundaryEvidenceState.SUPPORT
        for identity in (
            band.left_edge_observation_id,
            band.right_edge_observation_id,
        )
    }
    authoritative = tuple(
        (
            edge,
            tuple(
                basis
                for basis in intrinsic.get(edge.observation_id, ())
                if basis in _INTRINSIC_BASES
            ),
            _oriented_interval(edge.full_position_interval_px, direction),
        )
        for edge in observations
        if any(
            basis in _INTRINSIC_BASES
            for basis in intrinsic.get(edge.observation_id, ())
        )
    )
    ordered = tuple(
        sorted(
            authoritative,
            key=lambda item: (
                item[2].center,
                item[2].minimum,
                str(item[0].observation_id),
            ),
        )
    )

    ambiguous_ids: set[ObservationId] = set()
    component: list[_OrientedEdge] = []
    component_maximum = float("-inf")

    def close_component() -> None:
        if len(component) > 1:
            ambiguous_ids.update(item[0].observation_id for item in component)

    for item in ordered:
        interval = item[2]
        if component and interval.minimum > component_maximum:
            close_component()
            component = []
            component_maximum = float("-inf")
        component.append(item)
        component_maximum = max(component_maximum, interval.maximum)
    close_component()

    values: list[OverlapEdgePairObservation] = []
    for lower, upper in zip(ordered, ordered[1:]):
        start, start_bases, start_interval = lower
        end, end_bases, end_interval = upper
        if (
            start.observation_id in ambiguous_ids
            or end.observation_id in ambiguous_ids
            or start.observation_id in separator_edge_ids
            or end.observation_id in separator_edge_ids
            or BoundaryRole.START not in start.qualified_anchor_roles
            or BoundaryRole.END not in end.qualified_anchor_roles
        ):
            continue
        signed_gap = FiniteInterval(
            start_interval.minimum - end_interval.maximum,
            start_interval.maximum - end_interval.minimum,
        )
        if (
            signed_gap.maximum >= -_NUMERIC_EPSILON_PX
            or -signed_gap.minimum > maximum_overlap_px
        ):
            continue
        values.append(
            OverlapEdgePairObservation(
                observation_id=physical_observation_id(
                    "overlap-edge-pair",
                    end.observation_id,
                    start.observation_id,
                    direction,
                    signed_gap,
                ),
                end_edge_observation_id=end.observation_id,
                next_start_edge_observation_id=start.observation_id,
                signed_gap_interval_px=signed_gap,
                canonical_signed_gap_px=signed_gap.center,
                end_authority_bases=end_bases,
                next_start_authority_bases=start_bases,
            )
        )
    return tuple(values)


__all__ = [
    "OverlapEdgePairObservation",
    "observe_overlap_edge_pairs",
]
