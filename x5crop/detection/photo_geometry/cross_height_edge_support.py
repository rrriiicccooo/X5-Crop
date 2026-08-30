"""Resolve three-region aggregate edges against the direct edge ledger."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState, ObservationId
from .interval_math import intersect
from .measurement_model import SequenceTransitionObservation
from .model import (
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    CrossHeightEdgeResolution,
    CrossHeightEdgeResolutionFailureKind,
    CrossHeightEdgeResolutionKind,
)


def _query_ids(
    edge: BoundaryEdgeObservation,
    transitions: dict[str, SequenceTransitionObservation],
) -> frozenset[str]:
    return frozenset(
        transitions[str(identity)].query_id
        for identity in edge.transition_ids
    )


def _physically_compatible(
    direct: BoundaryEdgeObservation,
    aggregate: BoundaryEdgeObservation,
    transitions: dict[str, SequenceTransitionObservation],
) -> bool:
    if (
        direct.measurement_basis
        != BoundaryEdgeMeasurementBasis.DIRECT_TRACE
        or aggregate.measurement_basis
        != BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        or direct.polarity != aggregate.polarity
        or direct.polarity == 0
        or not set(direct.qualified_anchor_roles).intersection(
            aggregate.qualified_anchor_roles
        )
        or not _query_ids(direct, transitions).intersection(
            _query_ids(aggregate, transitions)
        )
        or intersect(
            direct.full_position_interval_px,
            aggregate.full_position_interval_px,
        )
        is None
    ):
        return False
    if (
        direct.full_direction_interval_degrees is None
        or aggregate.full_direction_interval_degrees is None
    ):
        return False
    return (
        intersect(
            direct.full_direction_interval_degrees,
            aggregate.full_direction_interval_degrees,
        )
        is not None
    )


def resolve_cross_height_edge_support(
    direct_edges: tuple[BoundaryEdgeObservation, ...],
    aggregate_edges: tuple[BoundaryEdgeObservation, ...],
    transitions: dict[str, SequenceTransitionObservation],
    *,
    registered_trace_lattice: tuple[int, ...],
) -> tuple[
    tuple[BoundaryEdgeObservation, ...],
    tuple[CrossHeightEdgeResolution, ...],
]:
    """Add one aggregate once, without giving correlated pixels two votes."""

    if not registered_trace_lattice:
        raise ValueError("cross-height edge support requires one trace lattice")
    matches = {
        aggregate.observation_id: tuple(
            direct
            for direct in direct_edges
            if _physically_compatible(direct, aggregate, transitions)
        )
        for aggregate in aggregate_edges
    }
    supports_by_direct: dict[ObservationId, list[BoundaryEdgeObservation]] = {}
    for aggregate in aggregate_edges:
        compatible = matches[aggregate.observation_id]
        if len(compatible) == 1:
            supports_by_direct.setdefault(
                compatible[0].observation_id,
                [],
            ).append(aggregate)

    direct_by_id = {item.observation_id: item for item in direct_edges}
    if len(direct_by_id) != len(direct_edges):
        raise ValueError("direct sequence edges must be unique")
    final_direct = dict(direct_by_id)
    resolutions: list[CrossHeightEdgeResolution] = []
    for aggregate in aggregate_edges:
        compatible = matches[aggregate.observation_id]
        compatible_ids = tuple(
            sorted(item.observation_id for item in compatible)
        )
        if not compatible:
            resolutions.append(
                CrossHeightEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.SUPPORTED,
                    kind=(
                        CrossHeightEdgeResolutionKind.STANDALONE_CANDIDATE
                    ),
                    compatible_direct_edge_ids=(),
                    final_edge_observation_id=None,
                    failure_kind=None,
                )
            )
            continue
        if len(compatible) > 1:
            resolutions.append(
                CrossHeightEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.CONTRADICTED,
                    kind=(
                        CrossHeightEdgeResolutionKind.AMBIGUOUS_DIRECT_MATCH
                    ),
                    compatible_direct_edge_ids=compatible_ids,
                    final_edge_observation_id=None,
                    failure_kind=(
                        CrossHeightEdgeResolutionFailureKind
                        .MULTIPLE_COMPATIBLE_DIRECT_EDGES
                    ),
                )
            )
            continue
        direct = compatible[0]
        direct_source_wide = (
            independent_spatial_support_count(
                registered_trace_lattice,
                direct.trace_coordinates_px,
            )
            == SPATIAL_SUPPORT_REGION_COUNT
        )
        if direct_source_wide:
            resolutions.append(
                CrossHeightEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.SUPPORTED,
                    kind=(
                        CrossHeightEdgeResolutionKind.REDUNDANT_DIRECT_EDGE
                    ),
                    compatible_direct_edge_ids=compatible_ids,
                    final_edge_observation_id=direct.observation_id,
                    failure_kind=None,
                )
            )
            continue
        if len(supports_by_direct[direct.observation_id]) > 1:
            resolutions.append(
                CrossHeightEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.CONTRADICTED,
                    kind=(
                        CrossHeightEdgeResolutionKind.AMBIGUOUS_DIRECT_MATCH
                    ),
                    compatible_direct_edge_ids=compatible_ids,
                    final_edge_observation_id=None,
                    failure_kind=(
                        CrossHeightEdgeResolutionFailureKind
                        .MULTIPLE_SUPPORTS_FOR_ONE_DIRECT_EDGE
                    ),
                )
            )
            continue
        final_direct[direct.observation_id] = replace(
            direct,
            measurement_basis=(
                BoundaryEdgeMeasurementBasis.DIRECT_WITH_CROSS_HEIGHT
            ),
            cross_height_support_id=aggregate.observation_id,
        )
        resolutions.append(
            CrossHeightEdgeResolution(
                support_observation_id=aggregate.observation_id,
                state=EvidenceState.SUPPORTED,
                kind=CrossHeightEdgeResolutionKind.BOUND_DIRECT_EDGE,
                compatible_direct_edge_ids=compatible_ids,
                final_edge_observation_id=direct.observation_id,
                failure_kind=None,
            )
        )

    final_edges = tuple(
        sorted(
            final_direct.values(),
            key=lambda item: (
                item.fit_position_interval_px.center,
                str(item.observation_id),
            ),
        )
    )
    return (
        final_edges,
        tuple(
            sorted(
                resolutions,
                key=lambda item: str(item.support_observation_id),
            )
        ),
    )
