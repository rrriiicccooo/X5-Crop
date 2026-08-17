"""Classify bounded residual topology after one normal template fit.

The normal fit is the default answer. This module never searches pixels,
ordinals, or placements. It walks the already-bound roles once and asks one
physical question: do adjacent same-role advances form one continuous base
pitch family, or is exactly one directly observed adjacency a discrete step?
Separator width alone cannot authorize an anomaly.
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


@dataclass(frozen=True)
class AdjacencyAdvanceFact:
    """One ordinal's directly measured START/END-to-START/END advance."""

    relation_ordinal: int
    advance_interval_px: FiniteInterval
    canonical_advance_px: float
    observation_ids: tuple[ObservationId, ...]
    separator_band_id: ObservationId | None

    def __post_init__(self) -> None:
        if (
            self.relation_ordinal <= 0
            or not self.advance_interval_px.contains(
                self.canonical_advance_px,
                epsilon=1.0e-9,
            )
            or not self.observation_ids
            or len(set(self.observation_ids)) != len(self.observation_ids)
        ):
            raise ValueError("adjacency advance fact is invalid")


@dataclass(frozen=True)
class LocalAdvanceAnalysis:
    """Result of one bounded adjacency scan over an existing sequence fit."""

    pattern: ResidualPattern
    relations: tuple[LocalAdvanceRelation, ...]
    adjacency_facts: tuple[AdjacencyAdvanceFact, ...]
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
        if tuple(item.relation_ordinal for item in self.adjacency_facts) != tuple(
            sorted(item.relation_ordinal for item in self.adjacency_facts)
        ):
            raise ValueError("adjacency facts must retain template order")
        unresolved = self.pattern == ResidualPattern.UNRESOLVED
        if unresolved != (self.unresolved_reason is not None):
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


def _advance(
    left: FiniteInterval,
    right: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    if direction > 0:
        return FiniteInterval(
            right.minimum - left.maximum,
            right.maximum - left.minimum,
        )
    return FiniteInterval(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
    )


def _connected(values: tuple[AdjacencyAdvanceFact, ...]) -> bool:
    """Return whether interval union is one continuous pitch family."""

    if not values:
        return True
    ordered = sorted(
        (item.advance_interval_px for item in values),
        key=lambda item: (item.minimum, item.maximum),
    )
    maximum = ordered[0].maximum
    for interval in ordered[1:]:
        if interval.minimum > maximum + _NUMERIC_EPSILON_PX:
            return False
        maximum = max(maximum, interval.maximum)
    return True


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
    facts: list[AdjacencyAdvanceFact] = []
    for adjacency_index in range(evaluated):
        advances: list[FiniteInterval] = []
        provenance: list[ObservationId] = []
        for role_offset in (0, 1):
            left_id = fit.role_observation_ids[2 * adjacency_index + role_offset]
            right_id = fit.role_observation_ids[
                2 * (adjacency_index + 1) + role_offset
            ]
            if left_id is None or right_id is None:
                continue
            left = by_id.get(left_id)
            right = by_id.get(right_id)
            if left is None or right is None:
                raise ValueError("bound advance observation is not registered")
            advances.append(
                _advance(
                    left.full_position_interval_px,
                    right.full_position_interval_px,
                    fit.template.direction,
                )
            )
            provenance.extend((left_id, right_id))
        if not advances:
            continue
        observed = advances[0]
        for other in advances[1:]:
            # START-to-START and END-to-END describe the same physical
            # advance through two different frame-edge families.  Their hull
            # is one conservative adjacency fact; intersecting the two would
            # mistake small fixed-frame residuals for another discrete gap.
            observed = FiniteInterval(
                min(observed.minimum, other.minimum),
                max(observed.maximum, other.maximum),
            )
        end_id = fit.role_observation_ids[2 * adjacency_index + 1]
        next_start_id = fit.role_observation_ids[2 * adjacency_index + 2]
        exact_bands = ()
        if end_id is not None and next_start_id is not None:
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
                unresolved_reason=(
                    "multiple separator observations bind one adjacency"
                ),
            )
        if end_id is not None and next_start_id is not None and not exact_bands:
            end = by_id[end_id]
            next_start = by_id[next_start_id]
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
                    unresolved_reason=(
                        "direct adjacency does not preserve end-then-start "
                        "order and has no separator material"
                    ),
                )
        band_id = None if not exact_bands else exact_bands[0].observation_id
        identities = tuple(dict.fromkeys(provenance))
        facts.append(
            AdjacencyAdvanceFact(
                relation_ordinal=adjacency_index + 1,
                advance_interval_px=observed,
                canonical_advance_px=observed.center,
                observation_ids=identities,
                separator_band_id=band_id,
            )
        )

    ordered_facts = tuple(facts)
    if len(ordered_facts) < 2 or _connected(ordered_facts):
        return LocalAdvanceAnalysis(
            ResidualPattern.NORMAL,
            (),
            ordered_facts,
            evaluated,
        )

    candidates: list[
        tuple[AdjacencyAdvanceFact, tuple[AdjacencyAdvanceFact, ...]]
    ] = []
    for fact in ordered_facts:
        remainder = tuple(item for item in ordered_facts if item != fact)
        if fact.separator_band_id is not None and _connected(remainder):
            candidates.append((fact, remainder))
    if len(ordered_facts) == 2 and len(candidates) == 2:
        # Two directly observed advances describe the same geometry whichever
        # one is called the base. Canonicalize from the first physical
        # adjacency so the later departure is the one-time suffix shift.
        candidates = [max(candidates, key=lambda item: item[0].relation_ordinal)]
    if len(candidates) != 1:
        return LocalAdvanceAnalysis(
            ResidualPattern.UNRESOLVED,
            (),
            ordered_facts,
            evaluated,
            unresolved_reason=(
                "residual advances do not identify one direct local step"
            ),
        )

    anomaly, base_facts = candidates[0]
    base = FiniteInterval(
        min(item.advance_interval_px.minimum for item in base_facts),
        max(item.advance_interval_px.maximum for item in base_facts),
    )
    delta = _difference(anomaly.advance_interval_px, base)
    canonical_delta = anomaly.canonical_advance_px - (
        sum(item.canonical_advance_px for item in base_facts) / len(base_facts)
    )
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
    relation_ids = tuple(
        dict.fromkeys(
            (
                anomaly.separator_band_id,
                *anomaly.observation_ids,
                *(
                    identity
                    for item in base_facts
                    for identity in item.observation_ids
                ),
            )
        )
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
    "AdjacencyAdvanceFact",
    "LocalAdvanceAnalysis",
    "ResidualPattern",
    "derive_bounded_local_advances",
]
