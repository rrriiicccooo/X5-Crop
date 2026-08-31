"""Resolve typed three-region aggregate edges into one edge ledger."""

from __future__ import annotations

from dataclasses import replace

from ...domain import EvidenceState, FiniteInterval, ObservationId
from ...run_local_identity import run_local_id
from .interval_math import intersect
from .measurement_model import SequenceTransitionObservation
from .model import (
    BoundaryEvidenceState,
    BoundaryRole,
    SPATIAL_SUPPORT_REGION_COUNT,
    independent_spatial_support_count,
)
from .observation_types import (
    BoundaryEdgeMeasurementBasis,
    BoundaryEdgeObservation,
    AggregateEdgeResolution,
    AggregateEdgeResolutionFailureKind,
    AggregateEdgeResolutionKind,
    SeparatorBandMeasurementBasis,
    SeparatorBandObservation,
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
    existing: BoundaryEdgeObservation,
    aggregate: BoundaryEdgeObservation,
    transitions: dict[str, SequenceTransitionObservation],
) -> bool:
    if (
        existing.measurement_basis == aggregate.measurement_basis
        or existing.polarity != aggregate.polarity
        or existing.polarity == 0
        or not set(existing.qualified_anchor_roles).intersection(
            aggregate.qualified_anchor_roles
        )
        or not _query_ids(existing, transitions).intersection(
            _query_ids(aggregate, transitions)
        )
        or intersect(
            existing.full_position_interval_px,
            aggregate.full_position_interval_px,
        )
        is None
    ):
        return False
    if (
        existing.full_direction_interval_degrees is None
        or aggregate.full_direction_interval_degrees is None
    ):
        return True
    return (
        intersect(
            existing.full_direction_interval_degrees,
            aggregate.full_direction_interval_degrees,
        )
        is not None
    )


def resolve_aggregate_edge_support(
    existing_edges: tuple[BoundaryEdgeObservation, ...],
    aggregate_edges: tuple[BoundaryEdgeObservation, ...],
    transitions: dict[str, SequenceTransitionObservation],
    *,
    registered_trace_lattice: tuple[int, ...],
    aggregate_basis: BoundaryEdgeMeasurementBasis,
    bind_direct_edge: bool,
) -> tuple[
    tuple[BoundaryEdgeObservation, ...],
    tuple[AggregateEdgeResolution, ...],
]:
    """Resolve each aggregate once without giving correlated pixels two votes."""

    if not registered_trace_lattice:
        raise ValueError("aggregate edge support requires one trace lattice")
    if aggregate_basis not in {
        BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
    }:
        raise ValueError("aggregate edge support basis is invalid")
    if not isinstance(bind_direct_edge, bool):
        raise TypeError("aggregate direct-edge binding policy must be boolean")
    if any(
        edge.measurement_basis != aggregate_basis
        for edge in aggregate_edges
    ):
        raise ValueError("aggregate support changed measurement basis")
    aggregate_support_counts = {
        aggregate.observation_id: independent_spatial_support_count(
            registered_trace_lattice,
            aggregate.trace_coordinates_px,
        )
        for aggregate in aggregate_edges
    }
    matches = {
        aggregate.observation_id: tuple(
            existing
            for existing in existing_edges
            if _physically_compatible(existing, aggregate, transitions)
        )
        for aggregate in aggregate_edges
        if aggregate_support_counts[aggregate.observation_id]
        == SPATIAL_SUPPORT_REGION_COUNT
    }
    supports_by_existing: dict[
        ObservationId,
        list[BoundaryEdgeObservation],
    ] = {}
    for aggregate in aggregate_edges:
        if (
            aggregate_support_counts[aggregate.observation_id]
            != SPATIAL_SUPPORT_REGION_COUNT
        ):
            continue
        compatible = matches[aggregate.observation_id]
        if len(compatible) == 1:
            supports_by_existing.setdefault(
                compatible[0].observation_id,
                [],
            ).append(aggregate)

    existing_by_id = {item.observation_id: item for item in existing_edges}
    if len(existing_by_id) != len(existing_edges):
        raise ValueError("existing sequence edges must be unique")
    final_edges = dict(existing_by_id)
    if any(
        aggregate.observation_id in final_edges
        for aggregate in aggregate_edges
    ):
        raise ValueError("aggregate and existing edges must have unique identities")
    resolutions: list[AggregateEdgeResolution] = []
    for aggregate in aggregate_edges:
        if (
            aggregate_support_counts[aggregate.observation_id]
            != SPATIAL_SUPPORT_REGION_COUNT
        ):
            resolutions.append(
                AggregateEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.UNAVAILABLE,
                    kind=(
                        AggregateEdgeResolutionKind
                        .INSUFFICIENT_SPATIAL_SUPPORT
                    ),
                    compatible_existing_edge_ids=(),
                    final_edge_observation_id=None,
                    failure_kind=(
                        AggregateEdgeResolutionFailureKind
                        .INSUFFICIENT_INDEPENDENT_SPATIAL_SUPPORT
                    ),
                )
            )
            continue
        compatible = matches[aggregate.observation_id]
        compatible_ids = tuple(
            sorted(item.observation_id for item in compatible)
        )
        if not compatible:
            final_edges[aggregate.observation_id] = aggregate
            resolutions.append(
                AggregateEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.SUPPORTED,
                    kind=AggregateEdgeResolutionKind.STANDALONE_EDGE,
                    compatible_existing_edge_ids=(),
                    final_edge_observation_id=aggregate.observation_id,
                    failure_kind=None,
                )
            )
            continue
        if len(compatible) > 1:
            resolutions.append(
                AggregateEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.CONTRADICTED,
                    kind=(
                        AggregateEdgeResolutionKind.AMBIGUOUS_EXISTING_MATCH
                    ),
                    compatible_existing_edge_ids=compatible_ids,
                    final_edge_observation_id=None,
                    failure_kind=(
                        AggregateEdgeResolutionFailureKind
                        .MULTIPLE_COMPATIBLE_EXISTING_EDGES
                    ),
                )
            )
            continue
        existing = compatible[0]
        existing_source_wide = (
            independent_spatial_support_count(
                registered_trace_lattice,
                existing.trace_coordinates_px,
            )
            == SPATIAL_SUPPORT_REGION_COUNT
        )
        if (
            existing_source_wide
            or existing.measurement_basis
            != BoundaryEdgeMeasurementBasis.DIRECT_TRACE
        ):
            resolutions.append(
                AggregateEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.SUPPORTED,
                    kind=(
                        AggregateEdgeResolutionKind.REDUNDANT_EXISTING_EDGE
                    ),
                    compatible_existing_edge_ids=compatible_ids,
                    final_edge_observation_id=existing.observation_id,
                    failure_kind=None,
                )
            )
            continue
        if not bind_direct_edge:
            resolutions.append(
                AggregateEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.SUPPORTED,
                    kind=(
                        AggregateEdgeResolutionKind.MATCHED_EXISTING_EDGE
                    ),
                    compatible_existing_edge_ids=compatible_ids,
                    final_edge_observation_id=existing.observation_id,
                    failure_kind=None,
                )
            )
            continue
        if len(supports_by_existing[existing.observation_id]) > 1:
            resolutions.append(
                AggregateEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.CONTRADICTED,
                    kind=(
                        AggregateEdgeResolutionKind.AMBIGUOUS_EXISTING_MATCH
                    ),
                    compatible_existing_edge_ids=compatible_ids,
                    final_edge_observation_id=None,
                    failure_kind=(
                        AggregateEdgeResolutionFailureKind
                        .MULTIPLE_AGGREGATES_FOR_ONE_EXISTING_EDGE
                    ),
                )
            )
            continue
        final_edges[existing.observation_id] = replace(
            existing,
            measurement_basis=(
                BoundaryEdgeMeasurementBasis.DIRECT_WITH_AGGREGATE
            ),
            aggregate_support_id=aggregate.observation_id,
        )
        resolutions.append(
            AggregateEdgeResolution(
                support_observation_id=aggregate.observation_id,
                state=EvidenceState.SUPPORTED,
                kind=AggregateEdgeResolutionKind.BOUND_DIRECT_EDGE,
                compatible_existing_edge_ids=compatible_ids,
                final_edge_observation_id=existing.observation_id,
                failure_kind=None,
            )
        )

    final_edges = tuple(
        sorted(
            final_edges.values(),
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


def resolve_aggregate_separator_support(
    aggregate_bands: tuple[SeparatorBandObservation, ...],
    edge_resolutions: tuple[AggregateEdgeResolution, ...],
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    canonical_bands: tuple[SeparatorBandObservation, ...],
    *,
    aggregate_basis: SeparatorBandMeasurementBasis,
) -> tuple[SeparatorBandObservation, ...]:
    """Project verified aggregate material onto one resolved edge identity.

    An aggregate edge enters placement only through a material band whose two
    sides both survived edge resolution.  A direct band for the same physical
    edge pair remains canonical, so correlated aggregate pixels never become a
    second vote.
    """

    if aggregate_basis not in {
        SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
    }:
        raise ValueError("aggregate separator basis is invalid")
    if any(band.measurement_basis != aggregate_basis for band in aggregate_bands):
        raise ValueError("aggregate separator support changed measurement basis")
    if any(
        band.measurement_basis == aggregate_basis
        for band in canonical_bands
    ):
        raise ValueError("canonical separator ledger repeats aggregate basis")
    resolutions_by_id = {
        item.support_observation_id: item for item in edge_resolutions
    }
    if len(resolutions_by_id) != len(edge_resolutions):
        raise ValueError("aggregate edge resolutions must be unique")
    edges_by_id = {item.observation_id: item for item in sequence_edges}
    if len(edges_by_id) != len(sequence_edges):
        raise ValueError("resolved sequence edges must be unique")
    canonical_separator_edge_ids = {
        identity
        for band in canonical_bands
        if band.evidence_state == BoundaryEvidenceState.SUPPORT
        for identity in (
            band.left_edge_observation_id,
            band.right_edge_observation_id,
        )
    }
    values: list[SeparatorBandObservation] = []
    for band in aggregate_bands:
        if (
            band.evidence_state != BoundaryEvidenceState.SUPPORT
            or band.material_support_region_count
            != SPATIAL_SUPPORT_REGION_COUNT
        ):
            continue
        left_resolution = resolutions_by_id.get(
            band.left_edge_observation_id
        )
        right_resolution = resolutions_by_id.get(
            band.right_edge_observation_id
        )
        if left_resolution is None or right_resolution is None:
            raise ValueError(
                "aggregate separator band references an unresolved edge"
            )
        if (
            left_resolution.state != EvidenceState.SUPPORTED
            or right_resolution.state != EvidenceState.SUPPORTED
            or left_resolution.final_edge_observation_id is None
            or right_resolution.final_edge_observation_id is None
        ):
            continue
        left = edges_by_id.get(
            left_resolution.final_edge_observation_id
        )
        right = edges_by_id.get(
            right_resolution.final_edge_observation_id
        )
        if left is None or right is None:
            raise ValueError(
                "aggregate separator band resolved outside the edge ledger"
            )
        if (
            BoundaryRole.END not in left.qualified_anchor_roles
            or BoundaryRole.START not in right.qualified_anchor_roles
        ):
            continue
        pair = frozenset((left.observation_id, right.observation_id))
        if (
            len(pair) != 2
            or bool(pair.intersection(canonical_separator_edge_ids))
            or left.fit_position_interval_px.center
            >= right.fit_position_interval_px.center
        ):
            continue
        gap = FiniteInterval(
            max(
                0.0,
                right.fit_position_interval_px.minimum
                - left.fit_position_interval_px.maximum,
            ),
            max(
                0.0,
                right.fit_position_interval_px.maximum
                - left.fit_position_interval_px.minimum,
            ),
        )
        values.append(
            replace(
                band,
                observation_id=ObservationId(
                    run_local_id(
                        "aggregate-separator-band",
                        aggregate_basis.value,
                        band.material_polarity.value,
                        left.observation_id,
                        right.observation_id,
                        gap.minimum.hex(),
                        gap.maximum.hex(),
                    )
                ),
                left_edge_observation_id=left.observation_id,
                right_edge_observation_id=right.observation_id,
                left_run_id=left.run_id,
                right_run_id=right.run_id,
                gap_interval_px=gap,
            )
        )
    return tuple(
        sorted(values, key=lambda item: str(item.observation_id))
    )


def placement_sequence_edges_with_aggregate_support(
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    aggregate_bands: tuple[SeparatorBandObservation, ...],
) -> tuple[BoundaryEdgeObservation, ...]:
    """Admit aggregate coordinates only through verified separator material."""

    aggregate_bases = {
        SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
        SeparatorBandMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
    }
    if any(
        band.measurement_basis not in aggregate_bases
        for band in aggregate_bands
    ):
        raise ValueError("placement aggregate support requires aggregate bands")
    supported_ids = {
        identity
        for band in aggregate_bands
        if band.evidence_state == BoundaryEvidenceState.SUPPORT
        for identity in (
            band.left_edge_observation_id,
            band.right_edge_observation_id,
        )
    }
    return tuple(
        edge
        for edge in sequence_edges
        if (
            edge.measurement_basis
            not in {
                BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE,
                BoundaryEdgeMeasurementBasis.BROAD_MATERIAL_AGGREGATE,
            }
            or edge.observation_id in supported_ids
        )
    )
