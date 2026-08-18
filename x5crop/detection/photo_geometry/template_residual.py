"""Classify bounded residual topology after one normal template fit.

The normal fit is the default answer. This module never searches pixels,
ordinals, or placements. It walks the already-bound roles once and asks one
physical question: does a directly observed END -> material band -> START
adjacency depart from the format gap authority?  Only that exact material
relation can authorize one suffix shift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import FiniteInterval, ObservationId
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation
from .template_model import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    MAX_LOCAL_ADVANCE_ANOMALIES,
    SequenceFit,
)


_NUMERIC_EPSILON_PX = 1.0e-7


class ResidualPattern(str, Enum):
    """The physical shape left after fitting the normal global template."""

    NORMAL = "normal"
    LOCAL_STEP = "local_step"
    UNRESOLVED = "unresolved"


class LocalAdvanceFailureKind(str, Enum):
    """Typed reason why no bounded local relation can be authorized."""

    MULTIPLE_BANDS = "multiple_bands"
    TOPOLOGY_CONTRADICTION = "topology_contradiction"
    TOO_MANY_ANOMALIES = "too_many_anomalies"


@dataclass(frozen=True)
class AdjacencyGapFact:
    """One ordinal's directly measured END -> material -> START gap."""

    relation_ordinal: int
    gap_interval_px: FiniteInterval
    canonical_gap_px: float
    observation_ids: tuple[ObservationId, ...]
    separator_band_id: ObservationId | None

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or not self.gap_interval_px.contains(
                self.canonical_gap_px,
                epsilon=1.0e-9,
            )
            or not self.observation_ids
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise ValueError("adjacency gap fact is invalid")


@dataclass(frozen=True)
class LocalAdvanceAnalysis:
    """Result of one bounded adjacency scan over an existing sequence fit."""

    pattern: ResidualPattern
    relations: tuple[LocalAdvanceRelation, ...]
    adjacency_facts: tuple[AdjacencyGapFact, ...]
    evaluated_adjacency_count: int
    anomaly_ordinals: tuple[int, ...] = ()
    failure_kind: LocalAdvanceFailureKind | None = None
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
        if tuple(item.relation_ordinal for item in self.adjacency_facts) != tuple(
            sorted(item.relation_ordinal for item in self.adjacency_facts)
        ):
            raise ValueError("adjacency facts must retain template order")
        unresolved = self.pattern == ResidualPattern.UNRESOLVED
        if unresolved != (self.unresolved_reason is not None) or unresolved != (
            self.failure_kind is not None
        ):
            raise ValueError("residual failure reason disagrees with its pattern")
        if unresolved and self.relations:
            raise ValueError("unresolved residual topology cannot authorize relations")
        if self.pattern == ResidualPattern.LOCAL_STEP and not self.relations:
            raise ValueError("local-step pattern requires one direct relation")
        if self.pattern == ResidualPattern.NORMAL and (
            self.relations or self.anomaly_ordinals
        ):
            raise ValueError("normal residual topology cannot carry an anomaly")


def _difference(left: FiniteInterval, right: FiniteInterval) -> FiniteInterval:
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _nominal_relation(ordinal: int) -> LocalAdvanceRelation:
    return LocalAdvanceRelation(
        relation_ordinal=ordinal,
        kind=LocalAdvanceKind.NOMINAL,
        delta_interval_px=FiniteInterval.exact(0.0),
        canonical_delta_px=0.0,
    )


def _bands_by_bound_pair(
    bands: tuple[SeparatorBandObservation, ...],
    edge_ids: set[ObservationId],
) -> dict[frozenset[ObservationId], tuple[SeparatorBandObservation, ...]]:
    values: dict[frozenset[ObservationId], list[SeparatorBandObservation]] = {}
    for band in bands:
        pair = frozenset(
            (band.left_edge_observation_id, band.right_edge_observation_id)
        )
        if len(pair) != 2:
            raise ValueError("separator band must bind two distinct edges")
        if not pair.issubset(edge_ids):
            raise ValueError("separator band references an unknown edge")
        values.setdefault(pair, []).append(band)
    return {key: tuple(items) for key, items in values.items()}


def derive_bounded_local_advances(
    fit: SequenceFit,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
) -> LocalAdvanceAnalysis:
    """Classify normal versus one directly proved suffix shift in O(count)."""

    evaluated = max(0, fit.template.count - 1)
    if evaluated == 0:
        return LocalAdvanceAnalysis(ResidualPattern.NORMAL, (), (), 0)
    by_id = {item.observation_id: item for item in sequence_edges}
    if len(by_id) != len(sequence_edges):
        raise ValueError("sequence edge identities must be unique")
    bands_by_pair = _bands_by_bound_pair(separator_bands, set(by_id))
    facts: list[AdjacencyGapFact] = []
    for adjacency_index in range(evaluated):
        end_id = fit.role_observation_ids[2 * adjacency_index + 1]
        next_start_id = fit.role_observation_ids[2 * adjacency_index + 2]
        if end_id is None or next_start_id is None:
            continue
        end = by_id.get(end_id)
        next_start = by_id.get(next_start_id)
        if end is None or next_start is None:
            raise ValueError("bound adjacency observation is not registered")
        exact_bands = bands_by_pair.get(
            frozenset((end_id, next_start_id)),
            (),
        )
        if len(exact_bands) > 1:
            return LocalAdvanceAnalysis(
                ResidualPattern.UNRESOLVED,
                (),
                tuple(facts),
                evaluated,
                failure_kind=LocalAdvanceFailureKind.MULTIPLE_BANDS,
                unresolved_reason=(
                    "multiple separator observations bind one adjacency"
                ),
            )
        if not exact_bands:
            canonical_gap = fit.template.direction * (
                next_start.canonical_position_px - end.canonical_position_px
            )
            if canonical_gap <= _NUMERIC_EPSILON_PX:
                # End-before-next-start is the normal physical topology.  A
                # directly reversed/equal pair without separator material is
                # contact or overlap evidence, but the current product has no
                # user-confirmed overlap golden authority.  Preserve the
                # observation and stop at review; never hide it inside a
                # generic negative local advance.
                return LocalAdvanceAnalysis(
                    ResidualPattern.UNRESOLVED,
                    (),
                    tuple(facts),
                    evaluated,
                    failure_kind=LocalAdvanceFailureKind.TOPOLOGY_CONTRADICTION,
                    unresolved_reason=(
                        "direct adjacency does not preserve end-then-start "
                        "order and has no separator material"
                    ),
                )
            # A missing band cannot authorize an exceptional gap.  The normal
            # template may still infer this adjacency from other direct phase
            # evidence, but no local degree of freedom is opened here.
            continue
        band = exact_bands[0]
        if (
            band.left_edge_observation_id != end_id
            or band.right_edge_observation_id != next_start_id
        ):
            return LocalAdvanceAnalysis(
                ResidualPattern.UNRESOLVED,
                (),
                tuple(facts),
                evaluated,
                failure_kind=LocalAdvanceFailureKind.TOPOLOGY_CONTRADICTION,
                unresolved_reason=(
                    "separator material contradicts bound END-then-START roles"
                ),
            )
        facts.append(
            AdjacencyGapFact(
                relation_ordinal=adjacency_index + 1,
                gap_interval_px=band.gap_interval_px,
                canonical_gap_px=band.gap_interval_px.center,
                observation_ids=(end_id, next_start_id),
                separator_band_id=band.observation_id,
            )
        )

    ordered_facts = tuple(facts)
    gap_prior = fit.template.gap_prior_px
    anomalies = tuple(
        fact
        for fact in ordered_facts
        if (
            fact.gap_interval_px.maximum < gap_prior.minimum
            or gap_prior.maximum < fact.gap_interval_px.minimum
        )
    )
    if not anomalies:
        return LocalAdvanceAnalysis(
            ResidualPattern.NORMAL,
            (),
            ordered_facts,
            evaluated,
        )

    if len(anomalies) > MAX_LOCAL_ADVANCE_ANOMALIES:
        return LocalAdvanceAnalysis(
            ResidualPattern.UNRESOLVED,
            (),
            ordered_facts,
            evaluated,
            failure_kind=LocalAdvanceFailureKind.TOO_MANY_ANOMALIES,
            unresolved_reason=(
                "direct local gap anomalies exceed bounded model"
            ),
        )

    anomaly = anomalies[0]
    delta = _difference(anomaly.gap_interval_px, gap_prior)
    canonical_delta = anomaly.canonical_gap_px - gap_prior.center
    if delta.contains(0.0):
        return LocalAdvanceAnalysis(
            ResidualPattern.NORMAL,
            (),
            ordered_facts,
            evaluated,
        )
    kind = (
        LocalAdvanceKind.WIDE
        if canonical_delta > 0.0
        else LocalAdvanceKind.NARROW
    )
    relations = [
        _nominal_relation(ordinal)
        for ordinal in range(1, anomaly.relation_ordinal)
    ]
    relation_ids = (
        anomaly.separator_band_id,
        *anomaly.observation_ids,
    )
    relations.append(
        LocalAdvanceRelation(
            relation_ordinal=anomaly.relation_ordinal,
            kind=kind,
            delta_interval_px=delta,
            canonical_delta_px=canonical_delta,
            observation_ids=tuple(
                identity for identity in relation_ids if identity is not None
            ),
        )
    )
    return LocalAdvanceAnalysis(
        ResidualPattern.LOCAL_STEP,
        tuple(relations),
        ordered_facts,
        evaluated,
        anomaly_ordinals=(anomaly.relation_ordinal,),
    )


__all__ = [
    "AdjacencyGapFact",
    "LocalAdvanceFailureKind",
    "LocalAdvanceAnalysis",
    "ResidualPattern",
    "derive_bounded_local_advances",
]
