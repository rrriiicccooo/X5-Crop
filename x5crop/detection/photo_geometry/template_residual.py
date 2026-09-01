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

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .template_adjacency_topology import (
    AdjacencyContinuityKind,
    AdjacencyContinuityObservation,
)
from .template_direct_role_authority import DirectRoleBindingAuthority
from .template_model import (
    AdjacencyRelation,
    ContactRelation,
    OverlapRelation,
    SeparatorRelationKind,
    SeparatorRelation,
    SequenceBindingUse,
    SequenceFit,
    measured_separator_relation_kind,
)
from .observation_types import SeparatorBandObservation
from .separator_material import normal_separator_material_bands


class ResidualPattern(str, Enum):
    """The physical shape left after fitting the normal global template."""

    NORMAL = "normal"
    MEASURED_RELATIONS = "measured_relations"
    UNRESOLVED = "unresolved"


class AdjacencyRelationFailureKind(str, Enum):
    """Typed reason why no bounded adjacency relation can be authorized."""

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
class AdjacencyRelationAnalysis:
    """Result of one bounded adjacency scan over an existing sequence fit."""

    pattern: ResidualPattern
    relations: tuple[AdjacencyRelation, ...]
    adjacency_facts: tuple[AdjacencyGapFact, ...]
    evaluated_adjacency_count: int
    anomaly_ordinals: tuple[int, ...] = ()
    failure_kind: AdjacencyRelationFailureKind | None = None
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
        if self.pattern == ResidualPattern.MEASURED_RELATIONS and not self.relations:
            raise ValueError("measured-relation pattern requires direct relations")
        if self.pattern == ResidualPattern.NORMAL and (
            self.relations or self.anomaly_ordinals
        ):
            raise ValueError("normal residual topology cannot carry an anomaly")


def _nominal_relation(ordinal: int) -> SeparatorRelation:
    return SeparatorRelation(
        relation_ordinal=ordinal,
        kind=SeparatorRelationKind.NOMINAL,
        delta_interval_px=FiniteInterval.exact(0.0),
        canonical_delta_px=0.0,
    )


def _measured_separator_relation(
    fact: AdjacencyGapFact,
    *,
    width_interval_px: FiniteInterval,
    canonical_width_px: float,
    pitch_interval_px: FiniteInterval,
    canonical_pitch_px: float,
) -> SeparatorRelation:
    if fact.separator_band_id is None or len(fact.observation_ids) != 2:
        raise ValueError("measured separator relation lacks direct atoms")
    delta = FiniteInterval(
        fact.gap_interval_px.minimum
        + width_interval_px.minimum
        - pitch_interval_px.maximum,
        fact.gap_interval_px.maximum
        + width_interval_px.maximum
        - pitch_interval_px.minimum,
    )
    canonical_delta = (
        fact.canonical_gap_px
        + canonical_width_px
        - canonical_pitch_px
    )
    return SeparatorRelation(
        relation_ordinal=fact.relation_ordinal,
        kind=measured_separator_relation_kind(canonical_delta),
        delta_interval_px=delta,
        canonical_delta_px=canonical_delta,
        separator_band_observation_id=fact.separator_band_id,
        end_edge_observation_id=fact.observation_ids[0],
        next_start_edge_observation_id=fact.observation_ids[1],
        signed_gap_interval_px=fact.gap_interval_px,
        canonical_signed_gap_px=fact.canonical_gap_px,
    )


def _relation_changes_unobserved_suffix(
    fit: SequenceFit,
    relation: SeparatorRelation,
) -> bool:
    """Keep a normal direct gap only when it constrains inferred roles."""

    return relation.is_anomaly or any(
        binding is None
        for binding in fit.role_bindings[2 * relation.relation_ordinal :]
    )


def derive_candidate_separator_relations(
    fit: SequenceFit,
    authority: DirectRoleBindingAuthority,
    separator_bands: tuple[SeparatorBandObservation, ...],
    pitch_authority_px: FiniteInterval,
) -> tuple[AdjacencyRelation, ...]:
    """Attach unique authorized separator gaps before a Grid refit.

    The input fit supplies only a fixed ordinal mapping.  Each relation still
    comes from one already-registered material band and two directly
    authorized native edges.  Missing or competing bands add no relation and
    therefore cannot make a candidate prove its own mapping.
    """

    if (
        fit.adjacency_relations
        or authority.state == EvidenceState.CONTRADICTED
    ):
        return fit.adjacency_relations
    supported = {
        (item.role_index, item.observation_id)
        for item in authority.facts
        if item.state == EvidenceState.SUPPORTED
    }
    bands_by_pair: dict[
        tuple[ObservationId, ObservationId],
        list[SeparatorBandObservation],
    ] = {}
    for band in normal_separator_material_bands(
        separator_bands,
        maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    ):
        bands_by_pair.setdefault(
            (
                band.left_edge_observation_id,
                band.right_edge_observation_id,
            ),
            [],
        ).append(band)

    measured: dict[int, SeparatorRelation] = {}
    for ordinal in range(1, fit.template.count):
        end_index = 2 * ordinal - 1
        start_index = 2 * ordinal
        end = fit.role_bindings[end_index]
        start = fit.role_bindings[start_index]
        if (
            end is None
            or start is None
            or end.use != SequenceBindingUse.PHASE_ANCHOR
            or start.use != SequenceBindingUse.PHASE_ANCHOR
            or (end_index, end.observation_id) not in supported
            or (start_index, start.observation_id) not in supported
        ):
            continue
        matches = bands_by_pair.get(
            (end.observation_id, start.observation_id),
            (),
        )
        if len(matches) != 1:
            continue
        band = matches[0]
        relation = _measured_separator_relation(
            AdjacencyGapFact(
                relation_ordinal=ordinal,
                gap_interval_px=band.gap_interval_px,
                canonical_gap_px=band.gap_interval_px.center,
                observation_ids=(end.observation_id, start.observation_id),
                separator_band_id=band.observation_id,
            ),
            width_interval_px=fit.template.frame_width_px,
            canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
            pitch_interval_px=pitch_authority_px,
            canonical_pitch_px=fit.pitch_fit.canonical_pitch_px,
        )
        if _relation_changes_unobserved_suffix(fit, relation):
            measured[ordinal] = relation
    if not measured:
        return ()
    return tuple(
        measured.get(ordinal, _nominal_relation(ordinal))
        for ordinal in range(1, max(measured) + 1)
    )


def derive_adjacency_relations(
    fit: SequenceFit,
    continuity_observations: tuple[AdjacencyContinuityObservation, ...],
) -> AdjacencyRelationAnalysis:
    """Classify normal versus directly measured adjacency advances in O(count)."""

    evaluated = max(0, fit.template.count - 1)
    if evaluated == 0:
        return AdjacencyRelationAnalysis(ResidualPattern.NORMAL, (), (), 0)
    if tuple(item.relation_ordinal for item in continuity_observations) != tuple(
        range(1, fit.template.count)
    ):
        raise ValueError("adjacency continuity ledger is incomplete")
    facts: list[AdjacencyGapFact] = []
    topologies_by_ordinal = {
        item.relation_ordinal: item
        for item in fit.adjacency_relations
        if isinstance(item, (ContactRelation, OverlapRelation))
    }
    overlap_observations_by_ordinal = {
        item.relation_ordinal: item
        for item in continuity_observations
        if item.kind == AdjacencyContinuityKind.OVERLAP
    }
    for observation in continuity_observations:
        if observation.kind == AdjacencyContinuityKind.UNRESOLVED:
            return AdjacencyRelationAnalysis(
                ResidualPattern.UNRESOLVED,
                (),
                tuple(facts),
                evaluated,
                failure_kind=(
                    AdjacencyRelationFailureKind.ADJACENCY_CONTINUITY_UNRESOLVED
                ),
                unresolved_reason=(
                    observation.reason
                    or "adjacency continuity is unresolved"
                ),
            )
        if observation.kind == AdjacencyContinuityKind.CONTACT:
            contact = topologies_by_ordinal.get(observation.relation_ordinal)
            if (
                not isinstance(contact, ContactRelation)
                or observation.contact_observation_id
                != contact.contact_observation_id
                or observation.end_observation_id
                != contact.shared_edge_observation_id
                or observation.next_start_observation_id
                != contact.shared_edge_observation_id
            ):
                raise ValueError("contact continuity lost its selected relation")
            facts.append(
                AdjacencyGapFact(
                    relation_ordinal=observation.relation_ordinal,
                    gap_interval_px=FiniteInterval.exact(0.0),
                    canonical_gap_px=0.0,
                    observation_ids=(contact.shared_edge_observation_id,),
                    separator_band_id=None,
                )
            )
            continue
        if observation.kind == AdjacencyContinuityKind.OVERLAP:
            gap = observation.signed_gap_interval_px
            end_id = observation.end_observation_id
            next_start_id = observation.next_start_observation_id
            overlap_id = observation.overlap_observation_id
            if (
                gap is None
                or gap.maximum >= 0.0
                or end_id is None
                or next_start_id is None
                or end_id == next_start_id
                or overlap_id is None
            ):
                raise ValueError("overlap continuity fact is incomplete")
            selected = topologies_by_ordinal.get(
                observation.relation_ordinal
            )
            if selected is not None and (
                not isinstance(selected, OverlapRelation)
                or selected.overlap_observation_id != overlap_id
                or selected.end_edge_observation_id != end_id
                or selected.next_start_edge_observation_id != next_start_id
                or selected.signed_gap_interval_px != gap
            ):
                raise ValueError("overlap continuity changed selected topology")
            facts.append(
                AdjacencyGapFact(
                    relation_ordinal=observation.relation_ordinal,
                    gap_interval_px=gap,
                    canonical_gap_px=gap.center,
                    observation_ids=(end_id, next_start_id),
                    separator_band_id=None,
                )
            )
            continue
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
    measured_separators = tuple(
        (fact, relation)
        for fact in ordered_facts
        if fact.relation_ordinal not in topologies_by_ordinal
        if fact.separator_band_id is not None
        for relation in (
            _measured_separator_relation(
                fact,
                width_interval_px=fit.pitch_fit.frame_width_px,
                canonical_width_px=fit.pitch_fit.canonical_frame_width_px,
                pitch_interval_px=fit.pitch_fit.pitch_interval_px,
                canonical_pitch_px=fit.pitch_fit.canonical_pitch_px,
            ),
        )
        if _relation_changes_unobserved_suffix(fit, relation)
    )
    measured_overlaps = tuple(
        fact
        for fact in ordered_facts
        if fact.relation_ordinal not in topologies_by_ordinal
        if fact.separator_band_id is None
        if fact.gap_interval_px.maximum < 0.0
    )
    relation_ordinals = tuple(
        sorted(
            {
                *topologies_by_ordinal,
                *(fact.relation_ordinal for fact, _relation in measured_separators),
                *(item.relation_ordinal for item in measured_overlaps),
            }
        )
    )
    if not relation_ordinals:
        return AdjacencyRelationAnalysis(
            ResidualPattern.NORMAL,
            (),
            ordered_facts,
            evaluated,
        )

    measured_by_ordinal = {
        fact.relation_ordinal: relation
        for fact, relation in measured_separators
    }
    overlaps_by_ordinal = {
        item.relation_ordinal: item for item in measured_overlaps
    }
    relations: list[AdjacencyRelation] = []
    for ordinal in range(1, max(relation_ordinals) + 1):
        topology = topologies_by_ordinal.get(ordinal)
        if topology is not None:
            relations.append(topology)
            continue
        overlap = overlaps_by_ordinal.get(ordinal)
        if overlap is not None:
            width = fit.pitch_fit.frame_width_px
            pitch = fit.pitch_fit.pitch_interval_px
            delta = FiniteInterval(
                overlap.gap_interval_px.minimum
                + width.minimum
                - pitch.maximum,
                overlap.gap_interval_px.maximum
                + width.maximum
                - pitch.minimum,
            )
            relations.append(
                OverlapRelation(
                    relation_ordinal=ordinal,
                    overlap_observation_id=(
                        overlap_observations_by_ordinal[
                            ordinal
                        ].overlap_observation_id
                    ),
                    end_edge_observation_id=overlap.observation_ids[0],
                    next_start_edge_observation_id=overlap.observation_ids[1],
                    signed_gap_interval_px=overlap.gap_interval_px,
                    canonical_signed_gap_px=overlap.canonical_gap_px,
                    delta_interval_px=delta,
                    canonical_delta_px=(
                        fit.pitch_fit.canonical_frame_width_px
                        - fit.pitch_fit.canonical_pitch_px
                        + overlap.canonical_gap_px
                    ),
                    supporting_observation_ids=overlap.observation_ids,
                )
            )
            continue
        measured_relation = measured_by_ordinal.get(ordinal)
        if measured_relation is None:
            relations.append(_nominal_relation(ordinal))
            continue
        relations.append(measured_relation)
    resolved_relations = tuple(relations)
    return AdjacencyRelationAnalysis(
        ResidualPattern.MEASURED_RELATIONS,
        resolved_relations,
        ordered_facts,
        evaluated,
        anomaly_ordinals=tuple(
            relation.relation_ordinal
            for relation in resolved_relations
            if relation.is_anomaly
        ),
    )
