"""Classify bounded residual topology after one normal template fit.

The normal fit is the default answer. This module never searches pixels,
ordinals, placements, or material. It consumes the canonical adjacency
continuity ledger once and asks whether a directly observed positive
separator departs from the format gap authority. Only that exact material
relation can authorize its own measured suffix advance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...domain import FiniteInterval, ObservationId
from .template_adjacency_topology import (
    AdjacencyContinuityKind,
    AdjacencyContinuityObservation,
)
from .template_model import (
    LocalAdvanceKind,
    LocalAdvanceRelation,
    SequenceFit,
)


class ResidualPattern(str, Enum):
    """The physical shape left after fitting the normal global template."""

    NORMAL = "normal"
    MEASURED_ADVANCES = "measured_advances"
    UNRESOLVED = "unresolved"


class LocalAdvanceFailureKind(str, Enum):
    """Typed reason why no bounded local relation can be authorized."""

    ADJACENCY_CONTINUITY_UNRESOLVED = (
        "adjacency_continuity_unresolved"
    )
    ADJACENCY_TOPOLOGY_UNRESOLVED = "adjacency_topology_unresolved"


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
        if self.pattern == ResidualPattern.MEASURED_ADVANCES and not self.relations:
            raise ValueError("measured-advance pattern requires direct relations")
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


def derive_bounded_local_advances(
    fit: SequenceFit,
    continuity_observations: tuple[AdjacencyContinuityObservation, ...],
) -> LocalAdvanceAnalysis:
    """Classify normal versus directly measured adjacency advances in O(count)."""

    evaluated = max(0, fit.template.count - 1)
    if evaluated == 0:
        return LocalAdvanceAnalysis(ResidualPattern.NORMAL, (), (), 0)
    if tuple(item.relation_ordinal for item in continuity_observations) != tuple(
        range(1, fit.template.count)
    ):
        raise ValueError("adjacency continuity ledger is incomplete")
    facts: list[AdjacencyGapFact] = []
    for observation in continuity_observations:
        if observation.kind == AdjacencyContinuityKind.UNRESOLVED:
            return LocalAdvanceAnalysis(
                ResidualPattern.UNRESOLVED,
                (),
                tuple(facts),
                evaluated,
                failure_kind=(
                    LocalAdvanceFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
                ),
                unresolved_reason=(
                    observation.reason
                    or "adjacency continuity is unresolved"
                ),
            )
        if observation.kind == (
            AdjacencyContinuityKind.NORMAL_SEPARATOR_COUNTEREVIDENCE
        ):
            return LocalAdvanceAnalysis(
                ResidualPattern.UNRESOLVED,
                (),
                tuple(facts),
                evaluated,
                failure_kind=(
                    LocalAdvanceFailureKind.ADJACENCY_TOPOLOGY_UNRESOLVED
                ),
                unresolved_reason=(
                    "direct adjacency contradicts an ordinary positive "
                    "separator; contact or overlap is not yet authorized"
                ),
            )
        if observation.kind != AdjacencyContinuityKind.SEPARATOR_MATERIAL:
            continue
        gap = observation.signed_gap_interval_px
        end_id = observation.end_observation_id
        next_start_id = observation.next_start_observation_id
        band_ids = observation.separator_band_observation_ids
        if (
            gap is None
            or end_id is None
            or next_start_id is None
            or len(band_ids) != 1
        ):
            raise ValueError("separator continuity fact is incomplete")
        band_id = band_ids[0]
        facts.append(
            AdjacencyGapFact(
                relation_ordinal=observation.relation_ordinal,
                gap_interval_px=gap,
                canonical_gap_px=gap.center,
                observation_ids=(end_id, next_start_id),
                separator_band_id=band_id,
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

    anomalies_by_ordinal = {
        item.relation_ordinal: item for item in anomalies
    }
    relations: list[LocalAdvanceRelation] = []
    for ordinal in range(1, max(anomalies_by_ordinal) + 1):
        anomaly = anomalies_by_ordinal.get(ordinal)
        if anomaly is None:
            relations.append(_nominal_relation(ordinal))
            continue
        delta = _difference(anomaly.gap_interval_px, gap_prior)
        canonical_delta = anomaly.canonical_gap_px - gap_prior.center
        if delta.contains(0.0):
            relations.append(_nominal_relation(ordinal))
            continue
        kind = (
            LocalAdvanceKind.WIDE
            if canonical_delta > 0.0
            else LocalAdvanceKind.NARROW
        )
        relation_ids = (
            anomaly.separator_band_id,
            *anomaly.observation_ids,
        )
        relations.append(
            LocalAdvanceRelation(
                relation_ordinal=ordinal,
                kind=kind,
                delta_interval_px=delta,
                canonical_delta_px=canonical_delta,
                observation_ids=tuple(
                    identity
                    for identity in relation_ids
                    if identity is not None
                ),
            )
        )
    return LocalAdvanceAnalysis(
        ResidualPattern.MEASURED_ADVANCES,
        tuple(relations),
        ordered_facts,
        evaluated,
        anomaly_ordinals=tuple(item.relation_ordinal for item in anomalies),
    )
