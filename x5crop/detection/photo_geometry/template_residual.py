"""Explain bounded direct departures from the nominal template gap.

This module does not search pixels or placements.  It inspects the already
selected sequence-role bindings and registered separator bands once.  A local
advance is authorized only when one physical separator directly binds one
known adjacency and its measured gap is disjoint from the nominal gap.  The
product model permits one such observed adjacency; its suffix adjustment is
applied once without searching its position.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain import FiniteInterval, ObservationId
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    MAX_LOCAL_ADVANCE_ANOMALIES,
    SequenceFit,
)


@dataclass(frozen=True)
class LocalAdvanceAnalysis:
    """Result of one bounded adjacency scan over an existing sequence fit."""

    relations: tuple[LocalAdvanceRelation, ...]
    evaluated_adjacency_count: int
    anomaly_ordinals: tuple[int, ...] = ()
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        if self.evaluated_adjacency_count < 0:
            raise ValueError("local adjacency count cannot be negative")
        if tuple(sorted(set(self.anomaly_ordinals))) != self.anomaly_ordinals:
            raise ValueError("local anomaly ordinals must be unique and ordered")
        if len(self.anomaly_ordinals) > MAX_LOCAL_ADVANCE_ANOMALIES:
            raise ValueError("local anomaly count exceeds the bounded model")
        relation_anomalies = tuple(
            item.relation_ordinal for item in self.relations if item.is_anomaly
        )
        if relation_anomalies != self.anomaly_ordinals:
            raise ValueError("local anomaly ordinals disagree with relations")
        if self.unresolved_reason is not None and (
            not self.unresolved_reason or self.relations
        ):
            raise ValueError("unresolved local advance cannot authorize relations")


def _difference(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _overlaps(left: FiniteInterval, right: FiniteInterval) -> bool:
    return max(left.minimum, right.minimum) <= min(left.maximum, right.maximum)


def _nominal_relation(ordinal: int) -> LocalAdvanceRelation:
    return LocalAdvanceRelation(
        relation_ordinal=ordinal,
        kind=LocalAdvanceKind.NOMINAL,
        delta_interval_px=FiniteInterval.exact(0.0),
        canonical_delta_px=0.0,
    )


def derive_bounded_local_advances(
    fit: SequenceFit,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
) -> LocalAdvanceAnalysis:
    """Return at most one directly proved, one-time suffix adjustment.

    Each adjacency is evaluated once.  Missing separator evidence means that
    the nominal template remains in force; it does not create an anomaly.
    More than the declared bound is an explicit unresolved model, never a
    Cartesian set of possible anomaly positions.
    """

    if fit.template.count <= 1:
        return LocalAdvanceAnalysis((), 0)
    edge_ids = {item.observation_id for item in sequence_edges}
    if len(edge_ids) != len(sequence_edges):
        raise ValueError("sequence edge identities must be unique")
    bands_by_edge_pair: dict[
        frozenset[ObservationId], list[SeparatorBandObservation]
    ] = {}
    for band in separator_bands:
        pair = frozenset(
            (band.left_edge_observation_id, band.right_edge_observation_id)
        )
        if len(pair) != 2:
            raise ValueError("separator band must bind two distinct edges")
        if not pair.issubset(edge_ids):
            raise ValueError("separator band references an unknown edge")
        bands_by_edge_pair.setdefault(pair, []).append(band)

    anomalies: list[
        tuple[int, LocalAdvanceKind, FiniteInterval, float, tuple[ObservationId, ...]]
    ] = []
    evaluated = fit.template.count - 1
    nominal = fit.template.gap_prior_px
    for adjacency_index in range(evaluated):
        end_id = fit.role_observation_ids[2 * adjacency_index + 1]
        next_start_id = fit.role_observation_ids[2 * adjacency_index + 2]
        if end_id is None or next_start_id is None:
            continue
        bands = bands_by_edge_pair.get(frozenset((end_id, next_start_id)), ())
        if len(bands) > 1:
            return LocalAdvanceAnalysis(
                (),
                evaluated,
                unresolved_reason="multiple separator observations bind one adjacency",
            )
        if not bands:
            continue
        band = bands[0]
        observed = band.gap_interval_px
        if _overlaps(observed, nominal):
            continue
        kind = (
            LocalAdvanceKind.WIDE
            if observed.minimum > nominal.maximum
            else LocalAdvanceKind.NARROW
        )
        delta = _difference(observed, nominal)
        canonical = observed.center - nominal.center
        anomalies.append(
            (
                adjacency_index + 1,
                kind,
                delta,
                canonical,
                (band.observation_id, end_id, next_start_id),
            )
        )

    if len(anomalies) > MAX_LOCAL_ADVANCE_ANOMALIES:
        return LocalAdvanceAnalysis(
            (),
            evaluated,
            unresolved_reason=(
                "direct local gap anomalies exceed the bounded template model"
            ),
        )
    if not anomalies:
        return LocalAdvanceAnalysis((), evaluated)
    by_ordinal = {item[0]: item[1:] for item in anomalies}
    last_ordinal = anomalies[-1][0]
    relations: list[LocalAdvanceRelation] = []
    for ordinal in range(1, last_ordinal + 1):
        anomaly = by_ordinal.get(ordinal)
        if anomaly is None:
            relations.append(_nominal_relation(ordinal))
            continue
        kind, delta, canonical, observation_ids = anomaly
        relations.append(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=kind,
                delta_interval_px=delta,
                canonical_delta_px=canonical,
                observation_ids=observation_ids,
            )
        )
    return LocalAdvanceAnalysis(
        tuple(relations),
        evaluated,
        anomaly_ordinals=tuple(item[0] for item in anomalies),
    )


__all__ = ["LocalAdvanceAnalysis", "derive_bounded_local_advances"]
