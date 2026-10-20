"""Classify candidate-bound adjacency facts without choosing a placement.

The registered measurement and the fixed-template placement already exist
before this module runs.  This owner maps those facts once per adjacency and
classifies positive separator, shared-edge contact, independent reversed-edge
overlap, fully observed normal absence, or an explicit unresolved state.  It
never searches pixels, selects a placement or installs new phase anchors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math

from ...domain import EvidenceState, FiniteInterval, ObservationId
from .model import BoundaryEvidenceState, BoundaryRole, SPATIAL_SUPPORT_REGION_COUNT
from .observation_types import BoundaryEdgeObservation, SeparatorBandObservation, OuterMaterialBoundaryObservation
from .physical_identity import physical_fact_id
from .template_adjacency_coverage import (
    AdjacencyCoverageState,
    AdjacencyObservationCoverage,
    assess_adjacency_observation_coverage,
)
from .template_model import (
    ContactRelation,
    OverlapRelation,
    SeparatorRelation,
    SeparatorRelationKind,
    SequenceFit,
)
from .template_overlap import OverlapEdgePairObservation
from .separator_material import normal_separator_material_bands
from .template_separator_support import SeparatorSupportResolution, resolve_separator_support
from .template_direct_role_authority import (
    DirectRoleBindingAuthority,
    DirectRoleAuthorityBasis,
    assess_direct_role_binding_authority,
)
from .measurement_model import PhotoBoundaryMeasurementSet


_NUMERIC_EPSILON_PX = 1.0e-7


class AdjacencyContinuityKind(str, Enum):
    """Observed material state relevant to an ordinary adjacency."""

    SEPARATOR_MATERIAL = "separator_material"
    CONTACT = "contact"
    OVERLAP = "overlap"
    NO_COUNTEREVIDENCE_OBSERVED = "no_counterevidence_observed"
    SEPARATOR_MATERIAL_UNRESOLVED = "separator_material_unresolved"
    UNRESOLVED = "unresolved"
    COVERAGE_INCOMPLETE = "coverage_incomplete"


class AdjacencyContinuityBasis(str, Enum):
    """Physical fact behind one continuity state."""

    POSITIVE_SEPARATOR_BAND = "positive_separator_band"
    SHARED_PHYSICAL_EDGE = "shared_physical_edge"
    INDEPENDENT_REVERSED_EDGES = "independent_reversed_edges"
    COMPLETE_REGISTERED_CORRIDOR = "complete_registered_corridor"


class AdjacencyContinuityFailureKind(str, Enum):
    """Why an ordinary material interpretation could not be resolved."""

    MULTIPLE_SEPARATOR_BANDS = "multiple_separator_bands"
    SEPARATOR_MATERIAL_UNRESOLVED = "separator_material_unresolved"
    SEPARATOR_ROLE_CONFLICT = "separator_role_conflict"
    SIGNED_GAP_CROSSES_ZERO = "signed_gap_crosses_zero"
    OVERLAP_OBSERVATION_UNAVAILABLE = "overlap_observation_unavailable"
    UNBOUND_REGISTERED_OVERLAP = "unbound_registered_overlap"
    UNBOUND_SEPARATOR_WIDTH_CONFLICT = "unbound_separator_width_conflict"
    REGISTERED_COVERAGE_INCOMPLETE = "registered_coverage_incomplete"


@dataclass(frozen=True)
class AdjacencyContinuityObservation:
    """One selected adjacency mapped to already registered material facts."""

    observation_id: str
    relation_ordinal: int
    state: EvidenceState
    kind: AdjacencyContinuityKind
    basis: AdjacencyContinuityBasis | None
    required_interval_px: FiniteInterval
    covering_query_ids: tuple[str, ...]
    end_observation_id: ObservationId | None
    next_start_observation_id: ObservationId | None
    separator_band_observation_ids: tuple[ObservationId, ...]
    contact_observation_id: ObservationId | None
    overlap_observation_id: ObservationId | None
    signed_gap_interval_px: FiniteInterval | None
    failure_kind: AdjacencyContinuityFailureKind | None
    reason: str | None

    def __post_init__(self) -> None:
        supported = self.kind in {
            AdjacencyContinuityKind.SEPARATOR_MATERIAL,
            AdjacencyContinuityKind.CONTACT,
            AdjacencyContinuityKind.OVERLAP,
            AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED,
        }
        failed = self.kind in {
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED,
            AdjacencyContinuityKind.UNRESOLVED,
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
        }
        direct_pair = (
            self.end_observation_id is not None
            and self.next_start_observation_id is not None
        )
        if (
            not self.observation_id
            or self.relation_ordinal <= 0
            or not isinstance(self.state, EvidenceState)
            or not isinstance(self.kind, AdjacencyContinuityKind)
            or not isinstance(self.required_interval_px, FiniteInterval)
            or tuple(sorted(set(self.covering_query_ids)))
            != self.covering_query_ids
            or tuple(sorted(set(self.separator_band_observation_ids)))
            != self.separator_band_observation_ids
            or supported != (self.state == EvidenceState.SUPPORTED)
            or self.state == EvidenceState.CONTRADICTED
            or failed != (self.state == EvidenceState.UNAVAILABLE)
            or failed
            != (
                isinstance(
                    self.failure_kind,
                    AdjacencyContinuityFailureKind,
                )
                and bool(self.reason)
            )
            or (not failed)
            != (self.failure_kind is None and self.reason is None)
        ):
            raise ValueError("adjacency continuity observation is invalid")
        allowed_failures = {
            AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED: {
                AdjacencyContinuityFailureKind.SEPARATOR_MATERIAL_UNRESOLVED,
            },
            AdjacencyContinuityKind.UNRESOLVED: {
                AdjacencyContinuityFailureKind.MULTIPLE_SEPARATOR_BANDS,
                AdjacencyContinuityFailureKind.SEPARATOR_ROLE_CONFLICT,
                AdjacencyContinuityFailureKind.SIGNED_GAP_CROSSES_ZERO,
                AdjacencyContinuityFailureKind.OVERLAP_OBSERVATION_UNAVAILABLE,
                AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP,
                AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT,
            },
            AdjacencyContinuityKind.COVERAGE_INCOMPLETE: {
                AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE,
            },
        }
        if failed and self.failure_kind not in allowed_failures[self.kind]:
            raise ValueError("adjacency continuity failure kind is invalid")
        if self.kind == AdjacencyContinuityKind.SEPARATOR_MATERIAL:
            if (
                self.basis
                != AdjacencyContinuityBasis.POSITIVE_SEPARATOR_BAND
                or not direct_pair
                or len(self.separator_band_observation_ids) != 1
                or self.signed_gap_interval_px is None
                or self.signed_gap_interval_px.minimum
                <= _NUMERIC_EPSILON_PX
            ):
                raise ValueError("separator continuity fact is incomplete")
        elif self.kind == AdjacencyContinuityKind.CONTACT:
            if (
                self.basis != AdjacencyContinuityBasis.SHARED_PHYSICAL_EDGE
                or not direct_pair
                or self.end_observation_id
                != self.next_start_observation_id
                or self.separator_band_observation_ids
                or self.signed_gap_interval_px != FiniteInterval.exact(0.0)
                or not isinstance(self.contact_observation_id, ObservationId)
            ):
                raise ValueError("contact continuity fact is incomplete")
        elif self.kind == AdjacencyContinuityKind.OVERLAP:
            if (
                self.basis
                != AdjacencyContinuityBasis.INDEPENDENT_REVERSED_EDGES
                or not direct_pair
                or self.end_observation_id
                == self.next_start_observation_id
                or self.separator_band_observation_ids
                or self.signed_gap_interval_px is None
                or self.signed_gap_interval_px.maximum
                >= -_NUMERIC_EPSILON_PX
                or not isinstance(self.overlap_observation_id, ObservationId)
            ):
                raise ValueError("overlap continuity fact is incomplete")
        elif self.kind == (
            AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED
        ):
            if (
                self.basis
                != AdjacencyContinuityBasis.COMPLETE_REGISTERED_CORRIDOR
                or self.separator_band_observation_ids
            ):
                raise ValueError("neutral continuity fact is invalid")
        elif self.basis is not None:
            raise ValueError("unresolved continuity cannot claim a basis")
        if (
            self.kind != AdjacencyContinuityKind.CONTACT
            and self.contact_observation_id is not None
        ):
            raise ValueError("non-contact continuity retained contact evidence")
        if (
            self.kind != AdjacencyContinuityKind.OVERLAP
            and self.failure_kind
            != AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP
            and self.overlap_observation_id is not None
        ):
            raise ValueError("non-overlap continuity retained overlap evidence")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP
        ) and (
            (self.end_observation_id is None)
            == (self.next_start_observation_id is None)
            or self.separator_band_observation_ids
            or self.overlap_observation_id is None
            or self.signed_gap_interval_px is None
            or self.signed_gap_interval_px.maximum >= -_NUMERIC_EPSILON_PX
        ):
            raise ValueError("unbound overlap counterevidence is incomplete")
        if self.failure_kind == AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT and (
            (self.end_observation_id is None) == (self.next_start_observation_id is None)
            or len(self.separator_band_observation_ids) != 1
            or self.signed_gap_interval_px is None
            or self.signed_gap_interval_px.minimum <= _NUMERIC_EPSILON_PX
        ):
            raise ValueError("unbound separator counterevidence is incomplete")
        if (
            self.kind
            == AdjacencyContinuityKind.SEPARATOR_MATERIAL_UNRESOLVED
            and (
                not direct_pair
                or not self.separator_band_observation_ids
                or self.signed_gap_interval_px is None
            )
        ):
            raise ValueError("unresolved material provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.MULTIPLE_SEPARATOR_BANDS
        ) and (not direct_pair or len(self.separator_band_observation_ids) < 2):
            raise ValueError("multiple separator provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.SEPARATOR_ROLE_CONFLICT
        ) and (
            not direct_pair
            or len(self.separator_band_observation_ids) != 1
            or self.signed_gap_interval_px is None
        ):
            raise ValueError("separator role-conflict provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.SIGNED_GAP_CROSSES_ZERO
        ) and (
            not direct_pair
            or self.separator_band_observation_ids
            or self.signed_gap_interval_px is None
            or self.signed_gap_interval_px.minimum > _NUMERIC_EPSILON_PX
            or self.signed_gap_interval_px.maximum <= _NUMERIC_EPSILON_PX
        ):
            raise ValueError("cross-zero gap provenance is invalid")
        if self.failure_kind == AdjacencyContinuityFailureKind.OVERLAP_OBSERVATION_UNAVAILABLE and (
            not direct_pair or self.separator_band_observation_ids
            or self.signed_gap_interval_px is None
            or self.signed_gap_interval_px.maximum >= -_NUMERIC_EPSILON_PX
        ):
            raise ValueError("unregistered overlap provenance is invalid")
        if self.failure_kind == (
            AdjacencyContinuityFailureKind.REGISTERED_COVERAGE_INCOMPLETE
        ) and self.separator_band_observation_ids:
            raise ValueError("incomplete coverage cannot retain a material band")

    @property
    def directly_observed_separator(self) -> bool:
        return self.kind == AdjacencyContinuityKind.SEPARATOR_MATERIAL


def _oriented_position_interval(
    interval: FiniteInterval,
    direction: int,
) -> FiniteInterval:
    if direction > 0:
        return interval
    return FiniteInterval(-interval.maximum, -interval.minimum)


def _signed_gap_interval(
    end: BoundaryEdgeObservation,
    next_start: BoundaryEdgeObservation,
    direction: int,
) -> FiniteInterval:
    oriented_end = _oriented_position_interval(
        end.full_position_interval_px,
        direction,
    )
    oriented_start = _oriented_position_interval(
        next_start.full_position_interval_px,
        direction,
    )
    return FiniteInterval(
        oriented_start.minimum - oriented_end.maximum,
        oriented_start.maximum - oriented_end.minimum,
    )


def _bands_by_pair(
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
    return {
        key: tuple(
            sorted(items, key=lambda item: str(item.observation_id))
        )
        for key, items in values.items()
    }


def unbound_registered_adjacency_counterevidence(
    fit: SequenceFit,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    coverage: tuple[AdjacencyObservationCoverage, ...],
    overlap_edge_pairs: tuple[OverlapEdgePairObservation, ...] = (),
    *,
    separator_bands: tuple[SeparatorBandObservation, ...] = (),
    separator_support: SeparatorSupportResolution | None = None,
    direct_role_authority: DirectRoleBindingAuthority | None = None,
) -> tuple[tuple[int, OverlapEdgePairObservation | SeparatorBandObservation], ...]:
    """Associate a unique registered partner with an already bound endpoint.

    This is validation only: the missing partner is never bound, fitted or
    granted authority. A complete ordinary corridor cannot claim absence of
    counterevidence when it owns a negative gap, or a positive material partner
    makes the native visible Frame wider than the physical upper bound.
    """

    by_id = {item.observation_id: item for item in sequence_edges}
    bound_ids = set(fit.bound_observation_ids)
    pairs_by_endpoint: dict[
        tuple[BoundaryRole, ObservationId], list[tuple[
            OverlapEdgePairObservation | SeparatorBandObservation,
            ObservationId, ObservationId,
        ]]
    ] = {}
    bands = normal_separator_material_bands(
        separator_bands, maximum_material_gap_px=fit.template.gap_prior_px.maximum,
    )
    resolution = separator_support or resolve_separator_support(sequence_edges, bands)
    supported_pairs = {c.role_authority_pair_edge_observation_ids for c in resolution.components
                       if c.role_authority_state == EvidenceState.SUPPORTED}
    pairs = [(p, p.end_edge_observation_id, p.next_start_edge_observation_id)
             for p in overlap_edge_pairs]
    pairs.extend((band, *(
        (band.left_edge_observation_id, band.right_edge_observation_id)
        if fit.template.direction > 0
        else (band.right_edge_observation_id, band.left_edge_observation_id)
    )) for band in bands if band.material_support_region_count == SPATIAL_SUPPORT_REGION_COUNT
        and (band.left_edge_observation_id, band.right_edge_observation_id) in supported_pairs)
    for pair, end_id, start_id in pairs:
        for role, identity in (
            (BoundaryRole.END, end_id),
            (BoundaryRole.START, start_id),
        ):
            pairs_by_endpoint.setdefault((role, identity), []).append((pair, end_id, start_id))
    authority_by_role = {} if direct_role_authority is None else {
        fact.role_index: fact for fact in direct_role_authority.facts
    }
    relations = {
        item.relation_ordinal: item for item in fit.adjacency_relations
    }
    values = []
    for item in coverage:
        ordinal = item.relation_ordinal
        relation = relations.get(ordinal)
        if (
            fit.template.gap_prior_px.minimum <= _NUMERIC_EPSILON_PX
            or item.state != AdjacencyCoverageState.COMPLETE
        ) or (
            relation is not None
            and (
                not isinstance(relation, SeparatorRelation)
                or relation.kind != SeparatorRelationKind.NOMINAL
            )
        ):
            continue
        end_id = fit.binding_observation_ids[2 * ordinal - 1]
        start_id = fit.binding_observation_ids[2 * ordinal]
        if (end_id is None) == (start_id is None):
            continue
        key = (
            (BoundaryRole.END, end_id)
            if end_id is not None
            else (BoundaryRole.START, start_id)
        )
        pairs = pairs_by_endpoint.get(key, ())
        if len(pairs) != 1:
            continue
        pair, pair_end_id, pair_start_id = pairs[0]
        partner = pair_start_id if end_id is not None else pair_end_id
        if partner in bound_ids:
            continue
        end = by_id.get(pair_end_id)
        start = by_id.get(pair_start_id)
        if (
            end is None
            or start is None
            or any(
                edge.full_position_interval_px.minimum
                < item.required_interval_px.minimum
                or edge.full_position_interval_px.maximum
                > item.required_interval_px.maximum
                for edge in (end, start)
            )
        ):
            continue
        if isinstance(pair, OverlapEdgePairObservation):
            if (BoundaryRole.END not in end.qualified_anchor_roles
                    or BoundaryRole.START not in start.qualified_anchor_roles
                    or _signed_gap_interval(end, start, fit.template.direction) != pair.signed_gap_interval_px):
                continue
        else:
            if _signed_gap_interval(end, start, fit.template.direction).minimum <= _NUMERIC_EPSILON_PX:
                continue
            missing_index = 2 * ordinal if end_id is not None else 2 * ordinal - 1
            opposite_index = missing_index + 1 if end_id is not None else missing_index - 1
            bound_index = 2 * ordinal - 1 if end_id is not None else 2 * ordinal
            opposite_binding = fit.role_bindings[opposite_index]
            if opposite_binding is None or any(
                (fact := authority_by_role.get(index)) is None
                or not fact.has_unconditional_coordinate_authority
                or fact.observation_id != fit.binding_observation_ids[index]
                or fact.evidence_group_id != fit.role_bindings[index].evidence_group_id
                for index in (bound_index, opposite_index)
            ):
                continue
            opposite = by_id[opposite_binding.observation_id]
            if not end.reference_trace_px == start.reference_trace_px == opposite.reference_trace_px:
                continue
            visible_width = _signed_gap_interval(
                start if end_id is not None else opposite,
                opposite if end_id is not None else end,
                fit.template.direction,
            )
            # A short visible exposure may be partial. Only an unavoidable
            # excess over the full physical W is contradictory.
            if visible_width.minimum <= fit.template.frame_width_px.maximum + _NUMERIC_EPSILON_PX:
                continue
        values.append((ordinal, pair))
    return tuple(values)


def observe_adjacency_continuity(
    fit: SequenceFit,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    coverage: tuple[AdjacencyObservationCoverage, ...],
    overlap_edge_pairs: tuple[OverlapEdgePairObservation, ...] = (),
    *,
    direct_role_authority: DirectRoleBindingAuthority | None = None,
) -> tuple[AdjacencyContinuityObservation, ...]:
    """Map a selected fit using registered edge, overlap, and coverage indexes."""

    if not isinstance(fit, SequenceFit):
        raise TypeError("adjacency continuity requires a sequence fit")
    if tuple(item.relation_ordinal for item in coverage) != tuple(
        range(1, fit.template.count)
    ):
        raise ValueError("adjacency continuity coverage is incomplete")
    by_id = {item.observation_id: item for item in sequence_edges}
    if len(by_id) != len(sequence_edges):
        raise ValueError("sequence edge identities must be unique")
    bands_by_pair = _bands_by_pair(
        separator_bands,
        set(by_id),
    )
    overlap_pairs_by_edges = {
        (
            item.end_edge_observation_id,
            item.next_start_edge_observation_id,
        ): item
        for item in overlap_edge_pairs
    }
    if len(overlap_pairs_by_edges) != len(overlap_edge_pairs):
        raise ValueError("overlap edge-pair identities must be unique")
    values: list[AdjacencyContinuityObservation] = []
    relations_by_ordinal = {
        item.relation_ordinal: item for item in fit.adjacency_relations
    }
    unbound_partners = dict(
        unbound_registered_adjacency_counterevidence(
            fit, sequence_edges, coverage, overlap_edge_pairs,
            separator_bands=separator_bands, direct_role_authority=direct_role_authority,
        )
    )
    for item in coverage:
        adjacency_index = item.relation_ordinal - 1
        end_id = fit.binding_observation_ids[2 * adjacency_index + 1]
        next_start_id = fit.binding_observation_ids[2 * adjacency_index + 2]
        direct_pair = end_id is not None and next_start_id is not None
        end = None if end_id is None else by_id.get(end_id)
        next_start = None if next_start_id is None else by_id.get(next_start_id)
        if direct_pair and (end is None or next_start is None):
            raise ValueError("bound adjacency observation is not registered")
        direct_signed_gap = (
            None
            if end is None or next_start is None
            else _signed_gap_interval(
                end,
                next_start,
                fit.template.direction,
            )
        )
        exact_bands = (
            ()
            if not direct_pair
            else bands_by_pair.get(frozenset((end_id, next_start_id)), ())
        )
        exact_band_ids = tuple(
            band.observation_id for band in exact_bands
        )
        supported_bands = tuple(
            band
            for band in exact_bands
            if band.evidence_state == BoundaryEvidenceState.SUPPORT
        )
        material_conflicts = tuple(
            band
            for band in exact_bands
            if band.evidence_state == BoundaryEvidenceState.CONTRADICTION
        )
        identity_parts = (
            fit.template.template_id,
            fit.phase_lattice_fit.integer_slot_offset,
            item.relation_ordinal,
            end_id,
            next_start_id,
            exact_band_ids,
            item.state.value,
            item.covering_query_ids,
        )
        if item.relation_ordinal in unbound_partners:
            identity_parts += (
                unbound_partners[item.relation_ordinal].observation_id,
            )
        relation = relations_by_ordinal.get(item.relation_ordinal)
        contact = relation if isinstance(relation, ContactRelation) else None
        overlap = relation if isinstance(relation, OverlapRelation) else None

        def observation(
            *,
            state: EvidenceState,
            kind: AdjacencyContinuityKind,
            basis: AdjacencyContinuityBasis | None = None,
            separator_band_observation_ids: tuple[ObservationId, ...] = (),
            contact_observation_id: ObservationId | None = None,
            overlap_observation_id: ObservationId | None = None,
            signed_gap_interval_px: FiniteInterval | None = None,
            failure_kind: AdjacencyContinuityFailureKind | None = None,
            reason: str | None = None,
        ) -> AdjacencyContinuityObservation:
            return AdjacencyContinuityObservation(
                observation_id=physical_fact_id(
                    "adjacency-continuity",
                    *identity_parts,
                    kind.value,
                    None if basis is None else basis.value,
                    None
                    if failure_kind is None
                    else failure_kind.value,
                ),
                relation_ordinal=item.relation_ordinal,
                state=state,
                kind=kind,
                basis=basis,
                required_interval_px=item.required_interval_px,
                covering_query_ids=item.covering_query_ids,
                end_observation_id=end_id,
                next_start_observation_id=next_start_id,
                separator_band_observation_ids=separator_band_observation_ids,
                contact_observation_id=contact_observation_id,
                overlap_observation_id=overlap_observation_id,
                signed_gap_interval_px=signed_gap_interval_px,
                failure_kind=failure_kind,
                reason=reason,
            )

        unbound_partner = unbound_partners.get(item.relation_ordinal)
        if unbound_partner is not None:
            is_overlap = isinstance(unbound_partner, OverlapEdgePairObservation)
            values.append(
                observation(
                    state=EvidenceState.UNAVAILABLE,
                    kind=AdjacencyContinuityKind.UNRESOLVED,
                    overlap_observation_id=unbound_partner.observation_id if is_overlap else None,
                    separator_band_observation_ids=() if is_overlap else (unbound_partner.observation_id,),
                    signed_gap_interval_px=unbound_partner.signed_gap_interval_px if is_overlap else unbound_partner.gap_interval_px,
                    failure_kind=(
                        AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP
                        if is_overlap else AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT
                    ),
                    reason=(
                        "ordinary adjacency has a unique registered overlap "
                        "partner for its bound endpoint"
                        if is_overlap else "unique registered separator partner and native opposite "
                        "edge exceed the physical Frame-width upper bound"
                    ),
                )
            )
            continue
        if contact is not None:
            if (
                end_id != contact.shared_edge_observation_id
                or next_start_id != contact.shared_edge_observation_id
            ):
                raise ValueError("selected contact lost its shared edge binding")
            if item.state != AdjacencyCoverageState.COMPLETE:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .REGISTERED_COVERAGE_INCOMPLETE
                        ),
                        reason=(
                            "registered queries do not cover the complete "
                            "contact corridor"
                        ),
                    )
                )
                continue
            if exact_bands:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.UNRESOLVED,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .SEPARATOR_ROLE_CONFLICT
                        ),
                        reason=(
                            "positive separator material competes with the "
                            "shared-edge contact interpretation"
                        ),
                        separator_band_observation_ids=exact_band_ids,
                        signed_gap_interval_px=direct_signed_gap,
                    )
                )
                continue
            values.append(
                observation(
                    state=EvidenceState.SUPPORTED,
                    kind=AdjacencyContinuityKind.CONTACT,
                    basis=AdjacencyContinuityBasis.SHARED_PHYSICAL_EDGE,
                    contact_observation_id=contact.contact_observation_id,
                    signed_gap_interval_px=FiniteInterval.exact(0.0),
                )
            )
            continue

        if overlap is not None:
            if (
                end_id != overlap.end_edge_observation_id
                or next_start_id
                != overlap.next_start_edge_observation_id
                or direct_signed_gap is None
                or direct_signed_gap
                != overlap.signed_gap_interval_px
            ):
                raise ValueError(
                    "selected overlap lost its reversed-edge binding"
                )
            if item.state != AdjacencyCoverageState.COMPLETE:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
                        signed_gap_interval_px=direct_signed_gap,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .REGISTERED_COVERAGE_INCOMPLETE
                        ),
                        reason=(
                            "registered queries do not cover the complete "
                            "overlap corridor"
                        ),
                    )
                )
                continue
            if exact_bands:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.UNRESOLVED,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .SEPARATOR_ROLE_CONFLICT
                        ),
                        reason=(
                            "separator material competes with the "
                            "reversed-edge overlap interpretation"
                        ),
                        separator_band_observation_ids=exact_band_ids,
                        signed_gap_interval_px=direct_signed_gap,
                    )
                )
                continue
            values.append(
                observation(
                    state=EvidenceState.SUPPORTED,
                    kind=AdjacencyContinuityKind.OVERLAP,
                    basis=(
                        AdjacencyContinuityBasis
                        .INDEPENDENT_REVERSED_EDGES
                    ),
                    overlap_observation_id=(
                        overlap.overlap_observation_id
                    ),
                    signed_gap_interval_px=direct_signed_gap,
                )
            )
            continue

        if len(supported_bands) > 1 or (
            supported_bands and material_conflicts
        ):
            values.append(
                observation(
                    state=EvidenceState.UNAVAILABLE,
                    kind=AdjacencyContinuityKind.UNRESOLVED,
                    failure_kind=(
                        AdjacencyContinuityFailureKind
                        .MULTIPLE_SEPARATOR_BANDS
                    ),
                    reason=(
                        "multiple or conflicting separator bands bind one "
                        "adjacency"
                    ),
                    separator_band_observation_ids=exact_band_ids,
                    signed_gap_interval_px=direct_signed_gap,
                )
            )
            continue
        if material_conflicts:
            values.append(
                observation(
                    state=EvidenceState.UNAVAILABLE,
                    kind=(
                        AdjacencyContinuityKind
                        .SEPARATOR_MATERIAL_UNRESOLVED
                    ),
                    failure_kind=(
                        AdjacencyContinuityFailureKind
                        .SEPARATOR_MATERIAL_UNRESOLVED
                    ),
                    reason=(
                        "registered separator material does not resolve "
                        "consistently across the measured height regions"
                    ),
                    separator_band_observation_ids=tuple(
                        band.observation_id for band in material_conflicts
                    ),
                    signed_gap_interval_px=direct_signed_gap,
                )
            )
            continue
        if not supported_bands and direct_signed_gap is not None:
            if direct_signed_gap.maximum < -_NUMERIC_EPSILON_PX:
                if item.state != AdjacencyCoverageState.COMPLETE:
                    values.append(
                        observation(
                            state=EvidenceState.UNAVAILABLE,
                            kind=AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
                            signed_gap_interval_px=direct_signed_gap,
                            failure_kind=(
                                AdjacencyContinuityFailureKind
                                .REGISTERED_COVERAGE_INCOMPLETE
                            ),
                            reason=(
                                "registered queries do not cover the complete "
                                "reversed-edge corridor"
                            ),
                        )
                    )
                    continue
                pair = overlap_pairs_by_edges.get((end_id, next_start_id))
                if (
                    pair is None
                    or pair.signed_gap_interval_px != direct_signed_gap
                ):
                    values.append(
                        observation(
                            state=EvidenceState.UNAVAILABLE,
                            kind=AdjacencyContinuityKind.UNRESOLVED,
                            signed_gap_interval_px=direct_signed_gap,
                            failure_kind=(
                                AdjacencyContinuityFailureKind
                                .OVERLAP_OBSERVATION_UNAVAILABLE
                            ),
                            reason=(
                                "reversed direct edges lack one registered "
                                "candidate-independent overlap observation"
                            ),
                        )
                    )
                    continue
                values.append(
                    observation(
                        state=EvidenceState.SUPPORTED,
                        kind=AdjacencyContinuityKind.OVERLAP,
                        basis=(
                            AdjacencyContinuityBasis
                            .INDEPENDENT_REVERSED_EDGES
                        ),
                        overlap_observation_id=pair.observation_id,
                        signed_gap_interval_px=direct_signed_gap,
                    )
                )
                continue
            if direct_signed_gap.minimum <= _NUMERIC_EPSILON_PX:
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.UNRESOLVED,
                        signed_gap_interval_px=direct_signed_gap,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .SIGNED_GAP_CROSSES_ZERO
                        ),
                        reason=(
                            "direct adjacency gap spans both ordinary and "
                            "non-ordinary topology"
                        ),
                    )
                )
                continue
        if supported_bands:
            assert end_id is not None and next_start_id is not None
            band = supported_bands[0]
            expected_left_id, expected_right_id = (
                (end_id, next_start_id)
                if fit.template.direction > 0
                else (next_start_id, end_id)
            )
            if (
                band.left_edge_observation_id != expected_left_id
                or band.right_edge_observation_id != expected_right_id
                or band.gap_interval_px.minimum <= _NUMERIC_EPSILON_PX
            ):
                values.append(
                    observation(
                        state=EvidenceState.UNAVAILABLE,
                        kind=AdjacencyContinuityKind.UNRESOLVED,
                        failure_kind=(
                            AdjacencyContinuityFailureKind
                            .SEPARATOR_ROLE_CONFLICT
                        ),
                        reason=(
                            "separator material contradicts bound "
                            "END-then-START roles"
                        ),
                        separator_band_observation_ids=(
                            band.observation_id,
                        ),
                        signed_gap_interval_px=direct_signed_gap,
                    )
                )
                continue
            values.append(
                observation(
                    state=EvidenceState.SUPPORTED,
                    kind=AdjacencyContinuityKind.SEPARATOR_MATERIAL,
                    basis=(
                        AdjacencyContinuityBasis.POSITIVE_SEPARATOR_BAND
                    ),
                    separator_band_observation_ids=(band.observation_id,),
                    signed_gap_interval_px=band.gap_interval_px,
                )
            )
            continue
        if item.state != AdjacencyCoverageState.COMPLETE:
            values.append(
                observation(
                    state=EvidenceState.UNAVAILABLE,
                    kind=AdjacencyContinuityKind.COVERAGE_INCOMPLETE,
                    signed_gap_interval_px=direct_signed_gap,
                    failure_kind=(
                        AdjacencyContinuityFailureKind
                        .REGISTERED_COVERAGE_INCOMPLETE
                    ),
                    reason=(
                        "registered queries do not cover the complete "
                        "adjacency corridor"
                    ),
                )
            )
            continue
        values.append(
            observation(
                state=EvidenceState.SUPPORTED,
                kind=(
                    AdjacencyContinuityKind.NO_COUNTEREVIDENCE_OBSERVED
                ),
                basis=(
                    AdjacencyContinuityBasis.COMPLETE_REGISTERED_CORRIDOR
                ),
                signed_gap_interval_px=direct_signed_gap,
            )
        )
    return tuple(values)


@dataclass(frozen=True)
class RegisteredAdjacencyRoleAssociation:
    """A unique physical partner mapped conditionally from one native role.

    This validates the candidate's ordinal mapping. It does not install the
    missing binding or supply a new phase anchor.
    """

    relation_ordinal: int
    bound_role_index: int
    bound_observation_id: ObservationId
    partner_role_index: int
    partner_observation_id: ObservationId
    pair_observation_id: ObservationId
    failure_kind: AdjacencyContinuityFailureKind
    native_frame_width_px: FiniteInterval | None
    physical_frame_width_upper_px: float | None
    scope: str = field(default="validation_only", init=False)

    def __post_init__(self) -> None:
        roles = (2 * self.relation_ordinal - 1, 2 * self.relation_ordinal)
        width_conflict = self.failure_kind == AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT
        if (
            type(self.relation_ordinal) is not int or self.relation_ordinal <= 0
            or type(self.bound_role_index) is not int
            or type(self.partner_role_index) is not int
            or {self.bound_role_index, self.partner_role_index} != set(roles)
            or any(not isinstance(value, ObservationId) for value in (
                self.bound_observation_id, self.partner_observation_id, self.pair_observation_id,
            ))
            or self.bound_observation_id == self.partner_observation_id
            or not isinstance(self.failure_kind, AdjacencyContinuityFailureKind)
            or self.failure_kind not in {
                AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP,
                AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT,
            }
            or width_conflict != (self.native_frame_width_px is not None)
            or width_conflict != (self.physical_frame_width_upper_px is not None)
        ):
            raise ValueError("registered adjacency role association is invalid")
        if width_conflict and (
            not isinstance(self.native_frame_width_px, FiniteInterval)
            or isinstance(self.physical_frame_width_upper_px, bool)
            or not isinstance(self.physical_frame_width_upper_px, (int, float))
            or not math.isfinite(self.physical_frame_width_upper_px)
            or self.physical_frame_width_upper_px <= 0
            or not self.native_frame_width_px.minimum
            > self.physical_frame_width_upper_px + _NUMERIC_EPSILON_PX
        ):
            raise ValueError("registered native Frame-width counterevidence is invalid")


@dataclass(frozen=True)
class PhaseCandidateAdjacencyAssessment:
    """Fresh, candidate-owned role and adjacency facts after native completion."""

    fit: SequenceFit
    direct_role_authority: DirectRoleBindingAuthority
    coverage: tuple[AdjacencyObservationCoverage, ...]
    continuity: tuple[AdjacencyContinuityObservation, ...]
    registered_role_associations: tuple[RegisteredAdjacencyRoleAssociation, ...]
    registered_edge_count: int
    state: EvidenceState = field(init=False)
    scope: str = field(default="candidate_bound_validation", init=False)
    role_check_count: int = field(init=False)
    adjacency_check_count: int = field(init=False)
    coverage_trace_check_count: int = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.fit, SequenceFit) or not isinstance(self.direct_role_authority, DirectRoleBindingAuthority):
            raise TypeError("candidate adjacency assessment is invalid")
        if type(self.registered_edge_count) is not int or self.registered_edge_count < len(self.fit.bound_observation_ids):
            raise ValueError("candidate adjacency assessment work is invalid")
        expected = tuple(range(1, self.fit.template.count))
        if (
            not isinstance(self.coverage, tuple)
            or any(not isinstance(item, AdjacencyObservationCoverage) for item in self.coverage)
            or not isinstance(self.continuity, tuple)
            or any(not isinstance(item, AdjacencyContinuityObservation) for item in self.continuity)
            or tuple(item.relation_ordinal for item in self.coverage) != expected
            or tuple(item.relation_ordinal for item in self.continuity) != expected
            or not isinstance(self.registered_role_associations, tuple)
            or any(not isinstance(item, RegisteredAdjacencyRoleAssociation) for item in self.registered_role_associations)
        ):
            raise ValueError("candidate adjacency assessment lost its complete ordinal ledger")
        identities = tuple((index, binding.observation_id)
                           for index, binding in enumerate(self.fit.role_bindings) if binding is not None)
        facts = tuple((fact.role_index, fact.observation_id)
                      for fact in self.direct_role_authority.facts)
        if identities != facts:
            raise ValueError("candidate adjacency assessment borrowed a role ledger")
        for fact in self.direct_role_authority.facts:
            binding = self.fit.role_bindings[fact.role_index]
            # The direct-role owner intentionally transfers outer-only facts
            # to their unique material evidence group. This is not native
            # coordinate authority and cannot support the width rejection.
            outer_only = (
                fact.bases == (DirectRoleAuthorityBasis.OUTER_MATERIAL_BOUNDARY,)
                and len(fact.supporting_outer_material_observation_ids) == 1
            )
            if fact.evidence_group_id != binding.evidence_group_id and not outer_only:
                raise ValueError("candidate adjacency assessment borrowed an evidence group")
        failures = tuple(item for item in self.continuity if item.failure_kind in {
            AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP,
            AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT,
        })
        if tuple(item.relation_ordinal for item in failures) != tuple(
            item.relation_ordinal for item in self.registered_role_associations
        ):
            raise ValueError("candidate adjacency assessment lost a registered partner")
        for association, continuity in zip(self.registered_role_associations, failures, strict=True):
            bound = self.fit.role_bindings[association.bound_role_index]
            pair_id = continuity.overlap_observation_id or continuity.separator_band_observation_ids[0]
            if (
                bound is None or bound.observation_id != association.bound_observation_id
                or self.fit.role_bindings[association.partner_role_index] is not None
                or association.partner_observation_id in self.fit.bound_observation_ids
                or pair_id != association.pair_observation_id
                or continuity.failure_kind != association.failure_kind
            ):
                raise ValueError("candidate adjacency partner changed its native role identity")
        object.__setattr__(self, "state", (
            EvidenceState.CONTRADICTED
            if failures or self.direct_role_authority.state == EvidenceState.CONTRADICTED
            else EvidenceState.UNAVAILABLE
            if self.direct_role_authority.state != EvidenceState.SUPPORTED
            or any(item.state != AdjacencyCoverageState.COMPLETE for item in self.coverage)
            or any(item.state != EvidenceState.SUPPORTED for item in self.continuity)
            else EvidenceState.SUPPORTED
        ))
        object.__setattr__(self, "role_check_count", len(facts))
        object.__setattr__(self, "adjacency_check_count", len(self.coverage))
        object.__setattr__(self, "coverage_trace_check_count", sum(len(item.trace_coverage) for item in self.coverage))


def assess_phase_candidate_adjacency(
    fit: SequenceFit,
    sequence_edges: tuple[BoundaryEdgeObservation, ...],
    separator_bands: tuple[SeparatorBandObservation, ...],
    measurement_sets: tuple[PhotoBoundaryMeasurementSet, ...],
    overlap_edge_pairs: tuple[OverlapEdgePairObservation, ...] = (),
    *,
    outer_material_boundaries: tuple[OuterMaterialBoundaryObservation, ...] = (),
    authorized_source_frame_width_px: FiniteInterval | None = None,
    direct_role_input_preparation=None,
    adjacency_coverage_preparation=None,
) -> PhaseCandidateAdjacencyAssessment:
    """Replay only registered facts; no fit, pixel query or candidate selection."""

    direct = assess_direct_role_binding_authority(
        fit, sequence_edges, separator_bands, measurement_sets,
        outer_material_boundaries=outer_material_boundaries,
        authorized_source_frame_width_px=authorized_source_frame_width_px,
        input_preparation=direct_role_input_preparation,
    )
    coverage = assess_adjacency_observation_coverage(
        fit, measurement_sets,
        directly_observed_ordinals=tuple(item.relation_ordinal for item in fit.adjacency_relations),
        input_preparation=adjacency_coverage_preparation,
    )
    continuity = observe_adjacency_continuity(
        fit, sequence_edges, separator_bands, coverage, overlap_edge_pairs,
        direct_role_authority=direct,
    )
    by_id = {edge.observation_id: edge for edge in sequence_edges}
    overlaps = {pair.observation_id: pair for pair in overlap_edge_pairs}
    bands = {band.observation_id: band for band in separator_bands}
    associations = []
    for item in continuity:
        if item.failure_kind not in {
            AdjacencyContinuityFailureKind.UNBOUND_REGISTERED_OVERLAP,
            AdjacencyContinuityFailureKind.UNBOUND_SEPARATOR_WIDTH_CONFLICT,
        }:
            continue
        end_index, start_index = 2 * item.relation_ordinal - 1, 2 * item.relation_ordinal
        bound_index = end_index if item.end_observation_id is not None else start_index
        partner_index = start_index if bound_index == end_index else end_index
        native_width = upper = None
        if item.overlap_observation_id is not None:
            pair = overlaps[item.overlap_observation_id]
            end_id, start_id = pair.end_edge_observation_id, pair.next_start_edge_observation_id
        else:
            pair = bands[item.separator_band_observation_ids[0]]
            end_id, start_id = ((pair.left_edge_observation_id, pair.right_edge_observation_id)
                                if fit.template.direction > 0 else
                                (pair.right_edge_observation_id, pair.left_edge_observation_id))
            opposite_index = partner_index + 1 if bound_index == end_index else partner_index - 1
            opposite = by_id[fit.binding_observation_ids[opposite_index]]
            native_width = _signed_gap_interval(
                by_id[start_id] if bound_index == end_index else opposite,
                opposite if bound_index == end_index else by_id[end_id],
                fit.template.direction,
            )
            upper = fit.template.frame_width_px.maximum
        associations.append(RegisteredAdjacencyRoleAssociation(
            relation_ordinal=item.relation_ordinal,
            bound_role_index=bound_index,
            bound_observation_id=fit.binding_observation_ids[bound_index],
            partner_role_index=partner_index,
            partner_observation_id=start_id if bound_index == end_index else end_id,
            pair_observation_id=pair.observation_id,
            failure_kind=item.failure_kind,
            native_frame_width_px=native_width,
            physical_frame_width_upper_px=upper,
        ))
    return PhaseCandidateAdjacencyAssessment(fit, direct, coverage, continuity, tuple(associations), len(sequence_edges))


__all__ = [
    "AdjacencyContinuityBasis",
    "AdjacencyContinuityFailureKind",
    "AdjacencyContinuityKind",
    "AdjacencyContinuityObservation",
    "observe_adjacency_continuity",
    "PhaseCandidateAdjacencyAssessment",
    "RegisteredAdjacencyRoleAssociation",
    "assess_phase_candidate_adjacency",
]
