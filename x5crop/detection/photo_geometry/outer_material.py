"""Resolve aperture-versus-exterior material without creating a separator."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
from ...run_local_identity import run_local_id
from .model import (
    BoundaryEvidenceState,
    BoundaryRole,
    SPATIAL_SUPPORT_REGION_COUNT,
)
from .observation_types import (
    AggregateEdgeResolution,
    BoundaryEdgeObservation,
    OuterMaterialBoundaryObservation,
    SeparatorBandMeasurementBasis,
    SeparatorBandObservation,
    SeparatorMaterialPolarity,
)


@dataclass(frozen=True)
class _ResolvedMaterialBand:
    band: SeparatorBandObservation
    left_edge: BoundaryEdgeObservation
    right_edge: BoundaryEdgeObservation


def _resolve_material_band(
    band: SeparatorBandObservation,
    *,
    edge_resolutions: dict[ObservationId, AggregateEdgeResolution],
    edges_by_id: dict[ObservationId, BoundaryEdgeObservation],
) -> _ResolvedMaterialBand | None:
    edge_ids = (
        band.left_edge_observation_id,
        band.right_edge_observation_id,
    )
    if band.measurement_basis != SeparatorBandMeasurementBasis.DIRECT_TRACE:
        resolved: list[ObservationId] = []
        for identity in edge_ids:
            resolution = edge_resolutions.get(identity)
            if (
                resolution is None
                or resolution.state != EvidenceState.SUPPORTED
                or resolution.final_edge_observation_id is None
            ):
                return None
            resolved.append(resolution.final_edge_observation_id)
        edge_ids = (resolved[0], resolved[1])
    left = edges_by_id.get(edge_ids[0])
    right = edges_by_id.get(edge_ids[1])
    if (
        left is None
        or right is None
        or left.observation_id == right.observation_id
        or left.fit_position_interval_px.center
        >= right.fit_position_interval_px.center
    ):
        return None
    return _ResolvedMaterialBand(band, left, right)


def observe_outer_material_boundaries(
    material_bands: tuple[SeparatorBandObservation, ...],
    aggregate_edge_resolutions: tuple[AggregateEdgeResolution, ...],
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    *,
    direction: int,
    intrinsic_authority_edge_ids: frozenset[ObservationId],
    maximum_material_width_px: float,
) -> tuple[OuterMaterialBoundaryObservation, ...]:
    """Collapse correlated same-role material bands into outer-boundary facts.

    A full three-region band is self-supporting.  A two-region band may transfer
    authority exactly once, from an independently authoritative exterior edge
    to the inner aperture boundary.  Only the unique spatially outermost pair
    within the calibrated local-gap width is retained.  The fact remains
    candidate-local: it can affect only the first START or the last END, never
    an internal role.
    """

    if direction not in {-1, 1}:
        raise ValueError("outer material direction must be -1 or 1")
    if (
        not math.isfinite(maximum_material_width_px)
        or maximum_material_width_px <= 0.0
    ):
        raise ValueError("outer material width ceiling must be positive")
    if any(
        not isinstance(identity, ObservationId)
        for identity in intrinsic_authority_edge_ids
    ):
        raise TypeError("outer material intrinsic authority ids are invalid")
    edges_by_id = {item.observation_id: item for item in sequence_edges}
    if len(edges_by_id) != len(sequence_edges):
        raise ValueError("outer material edge ledger must be unique")
    resolutions_by_id = {
        item.support_observation_id: item
        for item in aggregate_edge_resolutions
    }
    if len(resolutions_by_id) != len(aggregate_edge_resolutions):
        raise ValueError("outer material aggregate resolutions must be unique")

    grouped: dict[
        tuple[BoundaryRole, ObservationId, ObservationId],
        list[_ResolvedMaterialBand],
    ] = {}
    for band in material_bands:
        if (
            band.evidence_state != BoundaryEvidenceState.SUPPORT
            or band.gap_interval_px.maximum
            > maximum_material_width_px
        ):
            continue
        resolved = _resolve_material_band(
            band,
            edge_resolutions=resolutions_by_id,
            edges_by_id=edges_by_id,
        )
        if resolved is None:
            continue
        resolved_material_maximum = max(
            0.0,
            resolved.right_edge.fit_position_interval_px.maximum
            - resolved.left_edge.fit_position_interval_px.minimum,
        )
        if resolved_material_maximum > maximum_material_width_px:
            continue
        physical_pair = (
            (resolved.left_edge, resolved.right_edge)
            if direction > 0
            else (resolved.right_edge, resolved.left_edge)
        )
        first_roles = frozenset(physical_pair[0].qualified_anchor_roles)
        second_roles = frozenset(physical_pair[1].qualified_anchor_roles)
        if first_roles == second_roles == frozenset((BoundaryRole.START,)):
            role = BoundaryRole.START
            exterior, boundary = physical_pair
        elif first_roles == second_roles == frozenset((BoundaryRole.END,)):
            role = BoundaryRole.END
            boundary, exterior = physical_pair
        else:
            continue
        exterior_is_intrinsic = (
            exterior.observation_id in intrinsic_authority_edge_ids
        )
        if (
            band.material_support_region_count
            < SPATIAL_SUPPORT_REGION_COUNT
            and not exterior_is_intrinsic
        ):
            continue
        grouped.setdefault(
            (
                role,
                boundary.observation_id,
                exterior.observation_id,
            ),
            [],
        ).append(resolved)

    outermost_keys: set[
        tuple[BoundaryRole, ObservationId, ObservationId]
    ] = set()
    for role in (BoundaryRole.START, BoundaryRole.END):
        role_keys = tuple(key for key in grouped if key[0] == role)
        if not role_keys:
            continue
        choose_minimum = (
            role == BoundaryRole.START and direction > 0
        ) or (role == BoundaryRole.END and direction < 0)
        ordered = tuple(
            sorted(
                role_keys,
                key=lambda key: (
                    edges_by_id[key[2]].fit_position_interval_px.center
                    * (1.0 if choose_minimum else -1.0),
                    str(key[2]),
                    str(key[1]),
                ),
            )
        )
        selected = ordered[0]
        selected_exterior = edges_by_id[selected[2]].fit_position_interval_px
        if any(
            not (
                selected_exterior.maximum < other.minimum
                if choose_minimum
                else other.maximum < selected_exterior.minimum
            )
            for other in (
                edges_by_id[key[2]].fit_position_interval_px
                for key in ordered[1:]
            )
        ):
            continue
        outermost_keys.add(selected)

    observations: list[OuterMaterialBoundaryObservation] = []
    for role, boundary_id, exterior_id in sorted(
        outermost_keys,
        key=lambda item: (item[0].value, str(item[1]), str(item[2])),
    ):
        supports = grouped[(role, boundary_id, exterior_id)]
        boundary = edges_by_id[boundary_id]
        exterior = edges_by_id[exterior_id]
        low, high = sorted(
            (boundary, exterior),
            key=lambda item: item.fit_position_interval_px.center,
        )
        material_interval = FiniteInterval(
            max(
                0.0,
                high.fit_position_interval_px.minimum
                - low.fit_position_interval_px.maximum,
            ),
            max(
                0.0,
                high.fit_position_interval_px.maximum
                - low.fit_position_interval_px.minimum,
            ),
        )
        identity = ObservationId(
            run_local_id(
                "outer-material-boundary",
                role.value,
                boundary_id,
                exterior_id,
            )
        )
        observations.append(
            OuterMaterialBoundaryObservation(
                observation_id=identity,
                evidence_group_id=identity,
                role=role,
                boundary_edge_observation_id=boundary_id,
                exterior_edge_observation_id=exterior_id,
                supporting_band_observation_ids=tuple(
                    sorted(
                        {
                            support.band.observation_id
                            for support in supports
                        }
                    )
                ),
                measurement_bases=tuple(
                    item
                    for item in SeparatorBandMeasurementBasis
                    if item
                    in {
                        support.band.measurement_basis
                        for support in supports
                    }
                ),
                material_polarities=tuple(
                    item
                    for item in SeparatorMaterialPolarity
                    if item
                    in {
                        support.band.material_polarity
                        for support in supports
                    }
                ),
                material_interval_px=material_interval,
                independent_support_region_count=max(
                    support.band.material_support_region_count
                    for support in supports
                ),
                exterior_edge_has_intrinsic_authority=(
                    exterior_id in intrinsic_authority_edge_ids
                ),
            )
        )
    return tuple(
        sorted(observations, key=lambda item: str(item.observation_id))
    )


__all__ = [
    "observe_outer_material_boundaries",
]
