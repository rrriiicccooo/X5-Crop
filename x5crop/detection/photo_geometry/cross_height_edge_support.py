"""Resolve three-region aggregate edges against the direct edge ledger."""

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
    CrossHeightEdgeResolution,
    CrossHeightEdgeResolutionFailureKind,
    CrossHeightEdgeResolutionKind,
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
        return True
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
    """Resolve each aggregate once without giving correlated pixels two votes."""

    if not registered_trace_lattice:
        raise ValueError("cross-height edge support requires one trace lattice")
    if any(
        edge.measurement_basis
        != BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        for edge in aggregate_edges
    ):
        raise ValueError("cross-height support requires aggregate observations")
    aggregate_support_counts = {
        aggregate.observation_id: independent_spatial_support_count(
            registered_trace_lattice,
            aggregate.trace_coordinates_px,
        )
        for aggregate in aggregate_edges
    }
    matches = {
        aggregate.observation_id: tuple(
            direct
            for direct in direct_edges
            if _physically_compatible(direct, aggregate, transitions)
        )
        for aggregate in aggregate_edges
        if aggregate_support_counts[aggregate.observation_id]
        == SPATIAL_SUPPORT_REGION_COUNT
    }
    supports_by_direct: dict[ObservationId, list[BoundaryEdgeObservation]] = {}
    for aggregate in aggregate_edges:
        if (
            aggregate_support_counts[aggregate.observation_id]
            != SPATIAL_SUPPORT_REGION_COUNT
        ):
            continue
        compatible = matches[aggregate.observation_id]
        if len(compatible) == 1:
            supports_by_direct.setdefault(
                compatible[0].observation_id,
                [],
            ).append(aggregate)

    direct_by_id = {item.observation_id: item for item in direct_edges}
    if len(direct_by_id) != len(direct_edges):
        raise ValueError("direct sequence edges must be unique")
    final_edges = dict(direct_by_id)
    if any(
        aggregate.observation_id in final_edges
        for aggregate in aggregate_edges
    ):
        raise ValueError("cross-height and direct edges must have unique identities")
    resolutions: list[CrossHeightEdgeResolution] = []
    for aggregate in aggregate_edges:
        if (
            aggregate_support_counts[aggregate.observation_id]
            != SPATIAL_SUPPORT_REGION_COUNT
        ):
            resolutions.append(
                CrossHeightEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.UNAVAILABLE,
                    kind=(
                        CrossHeightEdgeResolutionKind
                        .INSUFFICIENT_SPATIAL_SUPPORT
                    ),
                    compatible_direct_edge_ids=(),
                    final_edge_observation_id=None,
                    failure_kind=(
                        CrossHeightEdgeResolutionFailureKind
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
                CrossHeightEdgeResolution(
                    support_observation_id=aggregate.observation_id,
                    state=EvidenceState.SUPPORTED,
                    kind=CrossHeightEdgeResolutionKind.STANDALONE_EDGE,
                    compatible_direct_edge_ids=(),
                    final_edge_observation_id=aggregate.observation_id,
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
        final_edges[direct.observation_id] = replace(
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


def resolve_cross_height_separator_support(
    aggregate_bands: tuple[SeparatorBandObservation, ...],
    edge_resolutions: tuple[CrossHeightEdgeResolution, ...],
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    direct_bands: tuple[SeparatorBandObservation, ...],
) -> tuple[SeparatorBandObservation, ...]:
    """Project verified aggregate material onto one resolved edge identity.

    An aggregate edge enters placement only through a material band whose two
    sides both survived edge resolution.  A direct band for the same physical
    edge pair remains canonical, so correlated aggregate pixels never become a
    second vote.
    """

    if any(
        band.measurement_basis
        != SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        for band in aggregate_bands
    ):
        raise ValueError("cross-height separator support requires aggregate bands")
    if any(
        band.measurement_basis
        != SeparatorBandMeasurementBasis.DIRECT_TRACE
        for band in direct_bands
    ):
        raise ValueError("direct separator bands must keep direct measurement basis")
    resolutions_by_id = {
        item.support_observation_id: item for item in edge_resolutions
    }
    if len(resolutions_by_id) != len(edge_resolutions):
        raise ValueError("cross-height edge resolutions must be unique")
    edges_by_id = {item.observation_id: item for item in sequence_edges}
    if len(edges_by_id) != len(sequence_edges):
        raise ValueError("resolved sequence edges must be unique")
    direct_pairs = {
        frozenset(
            (
                band.left_edge_observation_id,
                band.right_edge_observation_id,
            )
        )
        for band in direct_bands
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
            or pair in direct_pairs
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
                        "cross-height-separator-band",
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


def placement_sequence_edges_with_cross_height_support(
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    aggregate_bands: tuple[SeparatorBandObservation, ...],
) -> tuple[BoundaryEdgeObservation, ...]:
    """Admit aggregate coordinates only through verified separator material."""

    if any(
        band.measurement_basis
        != SeparatorBandMeasurementBasis.CROSS_HEIGHT_AGGREGATE
        for band in aggregate_bands
    ):
        raise ValueError("placement cross-height support requires aggregate bands")
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
            != BoundaryEdgeMeasurementBasis.CROSS_HEIGHT_AGGREGATE
            or edge.observation_id in supported_ids
        )
    )
